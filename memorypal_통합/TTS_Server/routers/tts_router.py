from fastapi import (
    APIRouter
)

from pydantic import (
    BaseModel
)

from services.tts_service import (
    tts_service
)

router = APIRouter()


@router.get(
    "/health"
)
def health():

    return {
        "status":
        "ok"
    }

class TTSRequest(
    BaseModel
):
    text: str
    ref_audio: str
    ref_text: str
    language: str = (
        "korean"
    )

@router.post(
    "/synthesize"
)

def synthesize(
    request: TTSRequest
):
    return (
        tts_service
        .synthesize(
            text=request.text,
            ref_audio=request.ref_audio,
            ref_text=request.ref_text,
            language=request.language
        )
    )