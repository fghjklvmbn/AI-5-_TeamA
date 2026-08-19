import os
import re
import warnings
import torch
import uuid
import soundfile as sf

from collections import OrderedDict
from threading import Lock

from pathlib import Path
from services.config.tts_config import(
    TTS_HOST
)


SERVICE_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_REFERENCE_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
MAX_REFERENCE_AUDIO_BYTES = 20 * 1024 * 1024
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def reference_upload_root():
    configured = os.getenv("MEMORYPAL_TTS_REFERENCE_UPLOAD_DIR", "").strip()
    path = Path(configured) if configured else SERVICE_ROOT / "reference_cache" / "uploads"
    if not path.is_absolute():
        path = SERVICE_ROOT / path
    return path.resolve()


def _reference_audio_roots():
    configured = os.getenv("MEMORYPAL_TTS_REFERENCE_AUDIO_ROOTS", "").strip()
    if configured:
        values = [value.strip() for value in configured.split(os.pathsep) if value.strip()]
    else:
        archive_root = SERVICE_ROOT.parent / "archive_service"
        values = [
            str(archive_root / "private_voice_uploads"),
            str(archive_root / "voice_uploads"),
            str(SERVICE_ROOT / "reference_audio"),
        ]
    values.append(str(reference_upload_root()))
    roots = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            path = SERVICE_ROOT / path
        roots.append(path.resolve())
    return tuple(roots)


class TTSService:

    def __init__(self):

        self.model = None
        requested_device = os.getenv(
            "MEMORYPAL_TTS_DEVICE",
            os.getenv("MEMORYPAL_DEVICE", "auto"),
        ).strip().lower()
        if requested_device not in {"auto", "cpu", "cuda", "rocm"}:
            raise RuntimeError("MEMORYPAL_TTS_DEVICE must be auto, cpu, cuda, or rocm")
        cuda = getattr(torch, "cuda", None)
        cuda_available = bool(cuda and cuda.is_available())
        rocm_available = bool(
            cuda_available and getattr(getattr(torch, "version", None), "hip", None)
        )
        if requested_device in {"cuda", "rocm"} and not cuda_available:
            warnings.warn(
                f"{requested_device.upper()} was requested for TTS but is unavailable; "
                "falling back to CPU.",
                RuntimeWarning,
            )
            self.accelerator = "cpu"
        elif requested_device == "rocm" and not rocm_available:
            warnings.warn(
                "ROCm was requested for TTS but this PyTorch build has no HIP runtime; "
                "falling back to CPU.",
                RuntimeWarning,
            )
            self.accelerator = "cpu"
        elif requested_device == "auto":
            self.accelerator = (
                "rocm" if rocm_available else "cuda" if cuda_available else "cpu"
            )
        elif requested_device == "cuda" and rocm_available:
            self.accelerator = "rocm"
        else:
            self.accelerator = requested_device
        # ROCm PyTorch deliberately uses the CUDA device namespace for API
        # compatibility. The accelerator field keeps the actual backend clear.
        self.device = "cuda" if self.accelerator in {"cuda", "rocm"} else "cpu"

        requested_engine = os.getenv(
            "MEMORYPAL_TTS_ENGINE",
            "auto",
        ).strip().lower()
        if requested_engine not in {"auto", "faster", "upstream"}:
            raise RuntimeError("MEMORYPAL_TTS_ENGINE must be auto, faster, or upstream")
        if self.accelerator != "cuda":
            if requested_engine == "faster":
                warnings.warn(
                    "The faster TTS engine requires NVIDIA CUDA; using upstream.",
                    RuntimeWarning,
                )
            self.engine = "upstream"
        else:
            self.engine = "faster" if requested_engine == "auto" else requested_engine
        self._prompt_cache = OrderedDict()
        self._prompt_cache_size = 8
        self._inference_lock = Lock()

    def _localize_ref_audio(self, ref_audio):
        value = str(ref_audio or "").strip()
        if not value or "\x00" in value:
            raise ValueError("Reference audio path is invalid.")

        # Voice samples are provisioned by the Archive service on a shared,
        # explicitly allowlisted volume. Fetching caller-controlled URLs here
        # would turn the GPU service into an SSRF proxy.
        scheme_separator = value.find("://")
        is_windows_path = WINDOWS_ABSOLUTE_PATH_RE.match(value) is not None
        if scheme_separator > 0 and not is_windows_path:
            raise ValueError("Remote reference audio URLs are not allowed.")
        if value.startswith(("//", "\\\\")):
            raise ValueError("Network reference audio paths are not allowed.")

        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = SERVICE_ROOT / candidate
        try:
            target = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("Reference audio file does not exist.") from exc
        if target.suffix.casefold() not in ALLOWED_REFERENCE_SUFFIXES:
            raise ValueError("Unsupported reference audio format.")
        if not any(target.is_relative_to(root) for root in _reference_audio_roots()):
            raise ValueError("Reference audio path is outside the allowed directories.")
        try:
            if not target.is_file():
                raise ValueError("Reference audio path is not a file.")
            size = target.stat().st_size
        except OSError as exc:
            raise ValueError("Reference audio file cannot be inspected.") from exc
        if size <= 0 or size > MAX_REFERENCE_AUDIO_BYTES:
            raise ValueError("Reference audio must be between 1 byte and 20MB.")
        return str(target)

    @staticmethod
    def _max_new_tokens(text):
        # Qwen3-TTS emits roughly 12 codec tokens per second. Four tokens per
        # input character leaves ample room for Korean speech while preventing
        # rare sampling runs from continuing for several minutes.
        return min(
            1024,
            max(48, len(str(text).strip()) * 4)
        )

    def load_model(self):

        print(
            "Qwen3-TTS 로딩중..."
        )

        requested_dtype = os.getenv("MEMORYPAL_TTS_DTYPE", "auto").strip().lower()
        dtype_names = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        if requested_dtype == "auto":
            dtype = (
                torch.bfloat16
                if self.accelerator == "cuda"
                else torch.float16
                if self.accelerator == "rocm"
                else torch.float32
            )
        elif requested_dtype in dtype_names:
            dtype = dtype_names[requested_dtype]
        else:
            raise RuntimeError(
                "MEMORYPAL_TTS_DTYPE must be auto, float32, float16, or bfloat16"
            )

        if self.engine == "faster":
            from faster_qwen3_tts import FasterQwen3TTS

            self.model = (
                FasterQwen3TTS
                .from_pretrained(
                    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                    device=self.device,
                    dtype=dtype,
                    attn_implementation="sdpa"
                )
            )
            # Capture the position-independent CUDA graphs during startup so
            # the first user request does not pay the one-time warmup cost.
            self.model._warmup(prefill_len=128)
        else:
            from qwen_tts import Qwen3TTSModel

            self.engine = "upstream"
            self.model = (
                Qwen3TTSModel
                .from_pretrained(
                    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                    device_map=self.device,
                    dtype=dtype,
                    attn_implementation="sdpa"
                )
            )
            self.model.model.eval()

        print(
            "Qwen3-TTS 로드 완료"
        )
    def synthesize(
        self,
        text,
        ref_audio,
        ref_text,
        language="korean"
    ):

        local_ref_audio = self._localize_ref_audio(ref_audio)

        with self._inference_lock:
            if self.engine == "faster":
                wavs, sr = (
                    self.model
                    .generate_voice_clone(
                        text=text,
                        language=language,
                        ref_audio=local_ref_audio,
                        ref_text=ref_text,
                        non_streaming_mode=True,
                        max_new_tokens=self._max_new_tokens(text)
                    )
                )
            else:
                prompt_key = (
                    local_ref_audio,
                    str(ref_text)
                )
                voice_prompt = self._prompt_cache.get(
                    prompt_key
                )
                if voice_prompt is None:
                    voice_prompt = (
                        self.model
                        .create_voice_clone_prompt(
                            ref_audio=local_ref_audio,
                            ref_text=ref_text,
                            x_vector_only_mode=False
                        )
                    )
                    self._prompt_cache[prompt_key] = voice_prompt
                    self._prompt_cache.move_to_end(prompt_key)
                    while len(self._prompt_cache) > self._prompt_cache_size:
                        self._prompt_cache.popitem(last=False)
                else:
                    self._prompt_cache.move_to_end(prompt_key)

                with torch.inference_mode():
                    wavs, sr = (
                        self.model
                        .generate_voice_clone(
                            text=text,
                            language=language,
                            voice_clone_prompt=voice_prompt,
                            non_streaming_mode=True
                        )
                    )

        output_dir = (
            Path("outputs")
        )

        output_dir.mkdir(
            exist_ok=True
        )

        output_path = (
            output_dir
            /
            f"{uuid.uuid4()}.wav"
        )

        sf.write(
            str(output_path),
            wavs[0],
            sr
        )

        filename = (
            output_path.name
        )

        return {
            "audio_path":
            f"{TTS_HOST}/outputs/{filename}"
        }


tts_service = TTSService()
