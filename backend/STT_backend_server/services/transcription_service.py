# stt-server/services/transcription_service.py

from models.whisper_model import accelerator, device, model, model_name


class TranscriptionService:

    device = device
    accelerator = accelerator
    model_name = model_name

    @staticmethod
    def transcribe(
        audio_path
    ):
        result = model.transcribe(
            audio_path,
            language="ko"
        )

        return result["text"]
