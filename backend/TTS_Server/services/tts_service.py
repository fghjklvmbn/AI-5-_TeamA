import os
import torch
import uuid
import soundfile as sf
import hashlib

from collections import OrderedDict
from threading import Lock
from urllib.parse import urlparse
from urllib.request import urlopen

from pathlib import Path
from services.config.tts_config import(
    TTS_HOST
)


class TTSService:

    def __init__(self):

        self.model = None
        self.engine = os.getenv(
            "MEMORYPAL_TTS_ENGINE",
            "faster"
        ).strip().lower()
        self._prompt_cache = OrderedDict()
        self._prompt_cache_size = 8
        self._inference_lock = Lock()

    def _localize_ref_audio(self, ref_audio):
        value = str(ref_audio)
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https"):
            return value

        cache_dir = Path("reference_cache")
        cache_dir.mkdir(exist_ok=True)
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
            suffix = ".wav"
        cache_key = hashlib.sha256(value.encode("utf-8")).hexdigest()
        target = cache_dir / f"{cache_key}{suffix}"
        if target.exists() and target.stat().st_size > 0:
            return str(target.resolve())

        temporary = target.with_suffix(target.suffix + ".part")
        total = 0
        try:
            with urlopen(value, timeout=30) as response, temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 50 * 1024 * 1024:
                        raise ValueError("Reference audio exceeds 50 MB")
                    output.write(chunk)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return str(target.resolve())

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

        if self.engine == "faster":
            from faster_qwen3_tts import FasterQwen3TTS

            self.model = (
                FasterQwen3TTS
                .from_pretrained(
                    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                    device="cuda",
                    dtype=torch.bfloat16,
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
                    device_map="cuda",
                    dtype=torch.bfloat16,
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

        with self._inference_lock:
            if self.engine == "faster":
                local_ref_audio = self._localize_ref_audio(
                    ref_audio
                )
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
                    str(ref_audio),
                    str(ref_text)
                )
                voice_prompt = self._prompt_cache.get(
                    prompt_key
                )
                if voice_prompt is None:
                    voice_prompt = (
                        self.model
                        .create_voice_clone_prompt(
                            ref_audio=ref_audio,
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
