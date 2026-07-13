# stt-server/app.py
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi import UploadFile
from fastapi import File

from services.transcription_service import (
    TranscriptionService
)

app = FastAPI()

@app.get("/health")
def health():

    return {
        "status": "ok"
    }


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...)
):
    suffix = Path(audio.filename or "segment.wav").suffix or ".wav"
    content = await audio.read()
    if not content:
        return {"text": ""}

    target: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(content)
            target = Path(temp.name)
        text = TranscriptionService.transcribe(str(target))
        return {"text": text}
    finally:
        if target is not None:
            target.unlink(missing_ok=True)
