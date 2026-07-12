from fastapi import APIRouter, UploadFile, File
import uuid
import shutil
from pathlib import Path

router = APIRouter()

@router.post("/upload/audio")
def upload_audio(
    file: UploadFile = File(...)
):

    save_dir = Path(
        "voice_uploads/input_audio"
    )

    save_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = (
        f"{uuid.uuid4()}.wav"
    )

    save_path = (
        save_dir / filename
    )

    with open(
        save_path,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    return {
        "audio_path":
        str(save_path),

        "audio_url":
        f"/voice_uploads/input_audio/{filename}"
    }