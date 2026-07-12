from pydantic import BaseModel


class VoiceCreate(
    BaseModel
):
    voice_name: str
    audio_path: str
    reference_text: str
    description: str | None = None