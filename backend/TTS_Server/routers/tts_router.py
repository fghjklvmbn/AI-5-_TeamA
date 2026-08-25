import asyncio
import hmac
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from services.tts_service import reference_upload_root, tts_service


INFERENCE_SLOT_WAIT_SECONDS = 0.05
_inference_slot = asyncio.Semaphore(1)
router = APIRouter()


def _normalize_reference_audio(source: Path) -> Path:
    """Convert browser-recorded reference audio to a decoder-stable mono WAV."""
    if source.suffix.casefold() == ".wav":
        return source
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reference audio conversion is unavailable.",
        )
    fd, normalized_name = tempfile.mkstemp(
        prefix="reference-normalized-", suffix=".wav", dir=source.parent,
    )
    os.close(fd)
    normalized = Path(normalized_name)
    try:
        result = subprocess.run(
            [
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source), "-ac", "1", "-ar", "24000", str(normalized),
            ],
            check=False,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0 or not normalized.is_file() or normalized.stat().st_size < 44:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The reference audio could not be decoded.",
            )
        return normalized
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The reference audio conversion timed out.",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reference audio conversion failed.",
        ) from exc
    finally:
        if normalized.exists() and normalized.stat().st_size < 44:
            normalized.unlink(missing_ok=True)


def require_model_service(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Authenticate GPU requests and reject a missing/weak server-side secret."""
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


def install_model_service_auth_middleware(app) -> None:
    @app.middleware("http")
    async def reject_unauthenticated_compute_requests(request: Request, call_next):
        # JSON parsing/validation should not consume caller-controlled bodies
        # until the server-to-server credential has been accepted.
        if request.url.path.rstrip("/") in {"/synthesize", "/synthesize-upload"}:
            try:
                require_model_service(request.headers.get("Authorization"))
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
        return await call_next(request)


@router.get("/health")
def health():
    return {
        "status": "ok",
        "engine": tts_service.engine,
        "device": tts_service.device,
        "accelerator": tts_service.accelerator,
    }


@router.get("/internal/ready", dependencies=[Depends(require_model_service)])
def internal_ready():
    return {"status": "ready"}


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=600)
    ref_audio: str = Field(min_length=1, max_length=2048)
    ref_text: str = Field(min_length=1, max_length=500)
    language: Literal["korean"] = "korean"
    voice_style: Literal["calm", "warm", "bright"] = "calm"


@router.post("/synthesize", dependencies=[Depends(require_model_service)])
async def synthesize(request: TTSRequest):
    try:
        await asyncio.wait_for(
            _inference_slot.acquire(), timeout=INFERENCE_SLOT_WAIT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The speech synthesis model is busy. Retry shortly.",
            headers={"Retry-After": "1"},
        ) from exc
    try:
        return await run_in_threadpool(
            tts_service.synthesize,
            text=request.text,
            ref_audio=request.ref_audio,
            ref_text=request.ref_text,
            language=request.language,
            voice_style=request.voice_style,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        _inference_slot.release()


@router.post("/synthesize-upload", dependencies=[Depends(require_model_service)])
async def synthesize_upload(
    text: str = Form(min_length=1, max_length=600),
    ref_text: str = Form(min_length=1, max_length=500),
    language: Literal["korean"] = Form(default="korean"),
    voice_style: Literal["calm", "warm", "bright"] = Form(default="calm"),
    ref_audio: UploadFile = File(...),
):
    upload_root = reference_upload_root()
    upload_root.mkdir(parents=True, exist_ok=True)
    suffix = Path(ref_audio.filename or "reference.wav").suffix.casefold()
    if suffix not in {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}:
        raise HTTPException(status_code=422, detail="Unsupported reference audio format.")
    content = await ref_audio.read(20 * 1024 * 1024 + 1)
    if not content or len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Reference audio must be between 1 byte and 20MB.")
    fd, temporary_name = tempfile.mkstemp(prefix="reference-", suffix=suffix, dir=upload_root)
    os.close(fd)
    temporary_path = Path(temporary_name)
    temporary_path.write_bytes(content)
    normalized_path = temporary_path
    try:
        normalized_path = await run_in_threadpool(_normalize_reference_audio, temporary_path)
        request = TTSRequest(
            text=text,
            ref_audio=str(normalized_path),
            ref_text=ref_text,
            language=language,
            voice_style=voice_style,
        )
        return await synthesize(request)
    finally:
        if normalized_path != temporary_path:
            normalized_path.unlink(missing_ok=True)
        temporary_path.unlink(missing_ok=True)
