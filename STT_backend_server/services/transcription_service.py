# stt-server/services/transcription_service.py

from models.whisper_model import model


class TranscriptionService:

    @staticmethod
    def transcribe(
        audio_path
    ):

        result = model.transcribe(
            audio_path,
            language="ko"
        )

        return result["text"]