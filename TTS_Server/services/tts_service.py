from qwen_tts import Qwen3TTSModel
import torch
import uuid
import soundfile as sf

from pathlib import Path
from services.config.tts_config import(
    TTS_HOST,
    TTS_PORT
)


class TTSService:

    def __init__(self):

        self.model = None

    def load_model(self):

        print(
            "Qwen3-TTS 로딩중..."
        )

        self.model = (
            Qwen3TTSModel
            .from_pretrained(
                "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                device_map="cpu",
                dtype=torch.float32,
                attn_implementation="sdpa"
            )
        )

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

        wavs, sr = (
            self.model
            .generate_voice_clone(
                text=text,
                language=language,
                ref_audio=ref_audio,
                ref_text=ref_text
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
            f"http://{TTS_HOST}:{TTS_PORT}/outputs/{filename}"
        }


tts_service = TTSService()