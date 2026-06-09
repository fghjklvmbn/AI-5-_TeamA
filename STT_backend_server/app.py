# stt-server/app.py
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from pathlib import Path

from fastapi import FastAPI
from fastapi import UploadFile
from fastapi import File

from services.transcription_service import (
    TranscriptionService
)

app = FastAPI()

UPLOAD_DIR = Path("uploads")

UPLOAD_DIR.mkdir(
    exist_ok=True
)


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...)
):

    target = (
        UPLOAD_DIR /
        audio.filename
    )

    target.write_bytes(
        await audio.read()
    )

    text = (
        TranscriptionService.transcribe(
            str(target)
        )
    )

    return {
        "text": text
    }