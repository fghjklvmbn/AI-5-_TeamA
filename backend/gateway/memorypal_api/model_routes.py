from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .dependencies import CurrentUser, get_current_user
from .schemas import (
    ModelDownloadRequest,
    ModelLoadRequest,
    PersonaActivationRequest,
    ModelSelectionRequest,
    ModelUnloadRequest,
)
from .services.model_manager import (
    ModelManagerConflict,
    ModelManagerError,
    ModelManagerUnavailable,
)


router = APIRouter(prefix="/v1/model-manager", tags=["model-manager"])


def _require_none(persona: str) -> None:
    if persona != "none":
        raise HTTPException(status_code=403, detail="직접 모델 관리는 페르소나 없음에서만 사용할 수 있습니다.")


def _raise_manager(exc: ModelManagerError) -> None:
    if isinstance(exc, ModelManagerConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ModelManagerUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/persona/activate")
async def activate_persona(
    payload: PersonaActivationRequest, request: Request,
    _user: CurrentUser = Depends(get_current_user),
):
    try:
        return await request.app.state.model_manager.activate_persona(
            _user.id, payload.persona,
        )
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.get("/status")
async def manager_status(
    request: Request, persona: str = "none", _user: CurrentUser = Depends(get_current_user),
):
    _require_none(persona)
    return await request.app.state.model_manager.status()


@router.get("/search")
async def search_models(
    request: Request,
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=12, ge=1, le=20),
    persona: str = "none",
    _user: CurrentUser = Depends(get_current_user),
):
    _require_none(persona)
    try:
        return {"models": await request.app.state.model_manager.search(q, limit)}
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.get("/models")
async def list_models(
    request: Request, persona: str = "none", _user: CurrentUser = Depends(get_current_user),
):
    _require_none(persona)
    try:
        return await request.app.state.model_manager.user_models(_user.id)
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.get("/selection")
async def get_model_selection(
    request: Request, persona: str = "default", _user: CurrentUser = Depends(get_current_user),
):
    if persona not in {"default", "emotional_companion", "none"}:
        raise HTTPException(status_code=422, detail="Unsupported persona")
    return await request.app.state.model_manager.selected_model(_user.id, persona)


@router.put("/selection")
async def set_model_selection(
    payload: ModelSelectionRequest, request: Request,
    _user: CurrentUser = Depends(get_current_user),
):
    try:
        return await request.app.state.model_manager.select_model(
            _user.id, payload.model_key, payload.persona,
        )
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.post("/downloads")
async def download_model(
    payload: ModelDownloadRequest, request: Request,
    _user: CurrentUser = Depends(get_current_user),
):
    try:
        return await request.app.state.model_manager.download(_user.id, payload.model)
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.get("/downloads/{job_id}")
async def download_status(
    job_id: str, request: Request, persona: str = "none",
    _user: CurrentUser = Depends(get_current_user),
):
    _require_none(persona)
    try:
        return await request.app.state.model_manager.download_status(job_id)
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.delete("/downloads/{job_id}")
async def dismiss_download(
    job_id: str, request: Request, persona: str = "none",
    _user: CurrentUser = Depends(get_current_user),
):
    _require_none(persona)
    try:
        return await request.app.state.model_manager.dismiss_download(_user.id, job_id)
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.get("/downloads")
async def list_downloads(request: Request, persona: str = "none", _user: CurrentUser = Depends(get_current_user)):
    _require_none(persona)
    return await request.app.state.model_manager.user_jobs(_user.id)


@router.post("/load")
async def load_model(
    payload: ModelLoadRequest, request: Request,
    _user: CurrentUser = Depends(get_current_user),
):
    try:
        return await request.app.state.model_manager.load(payload.model_key, payload.context_length)
    except ModelManagerError as exc:
        _raise_manager(exc)


@router.post("/unload")
async def unload_model(
    payload: ModelUnloadRequest, request: Request,
    _user: CurrentUser = Depends(get_current_user),
):
    try:
        return await request.app.state.model_manager.unload(payload.instance_id)
    except ModelManagerError as exc:
        _raise_manager(exc)
