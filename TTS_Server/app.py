from fastapi import FastAPI

from pydantic import BaseModel

from services.synthesis_service import (
    SynthesisService
)

app = FastAPI()


class TTSRequest(
    BaseModel
):

    text: str


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


@app.post("/synthesize")
def synthesize(
    request: TTSRequest
):

    audio_path = (
        SynthesisService.synthesize(
            request.text
        )
    )

    return {
        "audio_path":
        audio_path
    }