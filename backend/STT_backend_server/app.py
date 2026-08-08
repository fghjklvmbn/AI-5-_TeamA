# stt-server/app.py
import asyncio
import hmac
import os
import tempfile
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from services.transcription_service import TranscriptionService


MAX_AUDIO_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/aac",
    "audio/flac",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
}
INFERENCE_SLOT_WAIT_SECONDS = 0.05
_inference_slot = asyncio.Semaphore(1)

app = FastAPI()


def require_model_service(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Authenticate compute requests and fail closed when the service is misconfigured."""
    expected = os.getenv("MEMORYPAL_MODEL_SERVICE_TOKEN", "").strip()
    if len(expected) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model service authentication is not configured.",
        )
    scheme, separator, supplied = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not supplied
        or not hmac.compare_digest(supplied, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid model service credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.middleware("http")
async def reject_unauthenticated_compute_requests(request: Request, call_next):
    # FastAPI parses multipart bodies before endpoint dependencies. Authenticate
    # here as well so an anonymous caller cannot force a large upload to spool.
    if request.url.path.rstrip("/") == "/transcribe":
        try:
            require_model_service(request.headers.get("Authorization"))
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
    return await call_next(request)


def _validated_audio_suffix(audio: UploadFile) -> str:
    content_type = (audio.content_type or "").split(";", 1)[0].strip().casefold()
    suffix = Path(audio.filename or "").suffix.casefold()
    if content_type not in ALLOWED_AUDIO_CONTENT_TYPES or suffix not in ALLOWED_AUDIO_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio format.",
        )
    return suffix


async def _read_limited_audio(audio: UploadFile) -> bytes:
    if audio.size is not None and audio.size > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio upload must not exceed 20MB.",
        )
    content = bytearray()
    while True:
        chunk = await audio.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Audio upload must not exceed 20MB.",
            )
    return bytes(content)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": getattr(TranscriptionService, "device", "unknown"),
        "accelerator": getattr(TranscriptionService, "accelerator", "unknown"),
        "model": getattr(TranscriptionService, "model_name", "unknown"),
    }


@app.get("/internal/ready", dependencies=[Depends(require_model_service)])
def internal_ready():
    return {"status": "ready"}


@app.post("/transcribe", dependencies=[Depends(require_model_service)])
async def transcribe(audio: UploadFile = File(...)):
    suffix = _validated_audio_suffix(audio)
    try:
        content = await _read_limited_audio(audio)
    finally:
        await audio.close()
    if not content:
        raise HTTPException(status_code=422, detail="Audio upload is empty.")

    try:
        await asyncio.wait_for(
            _inference_slot.acquire(), timeout=INFERENCE_SLOT_WAIT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The speech recognition model is busy. Retry shortly.",
            headers={"Retry-After": "1"},
        ) from exc

    target: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(content)
            target = Path(temp.name)
        text = await run_in_threadpool(TranscriptionService.transcribe, str(target))
        return {"text": text}
    finally:
        if target is not None:
            target.unlink(missing_ok=True)
        _inference_slot.release()
