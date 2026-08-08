import asyncio
import hmac
import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from services.tts_service import tts_service


INFERENCE_SLOT_WAIT_SECONDS = 0.05
_inference_slot = asyncio.Semaphore(1)
router = APIRouter()


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
    ref_audio: UploadFile = File(...),
):
    upload_root = Path(
        os.getenv("MEMORYPAL_TTS_REFERENCE_UPLOAD_DIR", "/tmp/memorypal-reference")
    ).resolve()
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
    try:
        request = TTSRequest(
            text=text,
            ref_audio=str(temporary_path),
            ref_text=ref_text,
            language=language,
        )
        return await synthesize(request)
    finally:
        temporary_path.unlink(missing_ok=True)
