from typing import Optional
from pydantic import BaseModel


class ConversationCreate(
    BaseModel
):

    session_id: str

    user_text: str

    assistant_text: str

    input_audio_path: str

    output_audio_path: str

    voice_id: Optional[str] = None