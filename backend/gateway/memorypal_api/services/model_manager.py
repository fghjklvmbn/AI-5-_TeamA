from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..config import Settings


class ModelManagerError(RuntimeError):
    pass


class ModelManagerUnavailable(ModelManagerError):
    pass


class ModelManagerConflict(ModelManagerError):
    pass


_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_QUANTIZATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,39}$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,299}$")


class ModelManager:
    """Authenticated Gateway adapter around LM Studio v1 and Hugging Face APIs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        parsed = urlsplit(settings.llm_url)
        path = parsed.path.rstrip("/")
        if path.endswith("/v1"):
            path = path[:-3]
        self.native_base = urlunsplit(parsed._replace(path=f"{path}/api/v1", query="", fragment=""))
        self.state_path = settings.database_path.parent / "model_downloads.json"
        self._state_lock = asyncio.Lock()
        self.quota_bytes = 10 * 1024**3
        self.reservation_bytes = 3 * 1024**3
        self.max_loaded_models = 3

    def _read_state(self) -> dict[str, list[dict[str, Any]]]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_state(self, state: dict[str, list[dict[str, Any]]]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.state_path.parent, prefix="model-jobs-", suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                json.dump(state, handle, ensure_ascii=False)
            Path(name).replace(self.state_path)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def _parameter_billions(model_id: str) -> float | None:
        matches = re.findall(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*[Bb](?![A-Za-z])", model_id)
        return max((float(value) for value in matches), default=None)

    @staticmethod
    def _model_identity(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold()).replace("gguf", "")

    @classmethod
    def _allowed_llm(cls, item: dict[str, Any]) -> bool:
        model_id = str(item.get("id") or item.get("modelId") or item.get("key") or "")
        tags = {str(tag).casefold() for tag in item.get("tags") or []}
        text = f"{model_id} {' '.join(tags)}".casefold()
        if any(word in text for word in ("embedding", "embed-", "reranker", "text-embedding")):
            return False
        size = cls._parameter_billions(model_id)
        return size is not None and size <= 3.0

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.llm_api_key}"}

    async def _request(self, method: str, path: str, *, json_body: dict | None = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.request(
                    method, f"{self.native_base}{path}", headers=self._headers(), json=json_body,
                )
            if response.status_code == 409:
                raise ModelManagerConflict(self._detail(response))
            if response.status_code >= 400:
                raise ModelManagerUnavailable(self._detail(response))
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelManagerUnavailable(f"LM Studio 서버에 연결할 수 없습니다: {exc}") from exc

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            return str(payload.get("error") or payload.get("detail") or payload.get("message") or response.text)
        except ValueError:
            return response.text[:500] or f"LM Studio HTTP {response.status_code}"

    @staticmethod
    def _validate_opaque(value: str, label: str) -> str:
        value = value.strip()
        if not _OPAQUE_ID.fullmatch(value) or ".." in value:
            raise ModelManagerError(f"올바르지 않은 {label}입니다.")
        return value

    async def status(self) -> dict[str, Any]:
        try:
            payload = await self.models()
            online = True
            count = len(payload.get("models") or [])
            error = None
        except ModelManagerError as exc:
            online, count, error = False, 0, str(exc)
        root = self.settings.lmstudio_model_root
        delete_supported = bool(
            root is not None and root.is_dir() and shutil.which(self.settings.lmstudio_cli)
        )
        gpu_memory = await self._gpu_memory_status()
        return {
            "server_online": online,
            "model_count": count,
            "delete_supported": delete_supported,
            "delete_reason": None if delete_supported else (
                "Gateway가 LM Studio 모델 폴더와 lms CLI를 함께 사용할 수 있어야 삭제할 수 있습니다."
            ),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
            **gpu_memory,
        }

    async def _gpu_memory_status(self) -> dict[str, Any]:
        resource_url = str(
            getattr(self.settings, "monitor_llm_url", "")
            or getattr(self.settings, "llm_resource_url", "")
            or ""
        ).rstrip("/")
        if not resource_url:
            return {"gpu_metrics_available": False}
        try:
            async with httpx.AsyncClient(timeout=min(5.0, self.settings.request_timeout_seconds)) as client:
                response = await client.get(
                    f"{resource_url}/v1/metrics/current",
                    headers={"Authorization": f"Bearer {self.settings.model_service_token}"},
                )
                response.raise_for_status()
                payload = response.json()
            gpu = payload.get("gpu") or {}
            total = int(gpu.get("vram_total_bytes") or 0)
            used = int(gpu.get("vram_used_bytes") or 0)
            free = int(gpu.get("vram_free_bytes") or 0)
            if total <= 0 or min(used, free) < 0 or used > total or free > total:
                return {"gpu_metrics_available": False}
            return {
                "gpu_metrics_available": True,
                "gpu_name": " · ".join(str(name) for name in (gpu.get("names") or ["LLM 서버 GPU"]))[:300],
                "gpu_count": max(1, int(gpu.get("count") or 1)),
                "vram_total_bytes": total,
                "vram_used_bytes": used,
                "vram_free_bytes": free,
                "gpu_metrics_source": "llm-server",
            }
        except (httpx.HTTPError, TypeError, ValueError):
            return {"gpu_metrics_available": False}

    async def models(self) -> dict[str, Any]:
        payload = await self._request("GET", "/models")
        if not isinstance(payload, dict):
            raise ModelManagerUnavailable("LM Studio 모델 목록 형식이 올바르지 않습니다.")
        return payload

    async def user_models(self, user_id: str) -> dict[str, Any]:
        payload = await self.models()
        state = self._read_state()
        owned = {self._model_identity(str(job.get("model") or "").split("/", 1)[-1]) for job in state.get(user_id, []) if job.get("status") in {"completed", "complete", "downloaded"}}
        default = self.settings.llm_default_model.casefold()
        visible = []
        for model in payload.get("models") or []:
            key = str(model.get("key") or ""); text = f"{key} {model.get('display_name') or ''}".casefold()
            if any(word in text for word in ("embedding", "embed-", "reranker", "text-embedding")):
                continue
            if self.settings.llm_companion_model.casefold() in text:
                continue
            identity = self._model_identity(f"{key} {model.get('display_name') or ''}")
            if default in text or any(name and (name in identity or identity in name) for name in owned):
                visible.append(model)
        return {"models": visible}

    async def ensure_loaded(self, model_key: str) -> None:
        model_key = self._validate_opaque(model_key, "모델 키")
        if self.settings.llm_companion_model.casefold() in model_key.casefold():
            raise ModelManagerConflict("정서적 동반자 모델은 직접 모델로 선택할 수 없습니다.")
        payload = await self.models()
        for model in payload.get("models") or []:
            if str(model.get("key") or "") == model_key:
                if model.get("loaded_instances"):
                    return
                raise ModelManagerConflict("선택한 모델이 언로드되어 있습니다. 설정에서 다시 로드해 주세요.")
        raise ModelManagerConflict("선택한 모델을 LM Studio에서 찾을 수 없습니다. 다시 선택해 주세요.")

    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        query = " ".join(query.split())
        if len(query) < 2:
            raise ModelManagerError("검색어는 두 글자 이상 입력해 주세요.")
        headers = {"Accept": "application/json"}
        if self.settings.huggingface_token:
            headers["Authorization"] = f"Bearer {self.settings.huggingface_token}"
        try:
            async with httpx.AsyncClient(timeout=min(30.0, self.settings.request_timeout_seconds)) as client:
                response = await client.get(
                    "https://huggingface.co/api/models",
                    params={
                        "search": query, "filter": "gguf", "sort": "downloads",
                        "direction": "-1", "limit": max(1, min(20, limit)), "full": "true",
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelManagerUnavailable(f"Hugging Face 검색을 완료하지 못했습니다: {exc}") from exc
        results = []
        for item in payload if isinstance(payload, list) else []:
            model_id = str(item.get("id") or item.get("modelId") or "")
            if not _MODEL_ID.fullmatch(model_id) or not self._allowed_llm(item):
                continue
            results.append({
                "id": model_id,
                "author": str(item.get("author") or model_id.split("/", 1)[0]),
                "downloads": int(item.get("downloads") or 0),
                "likes": int(item.get("likes") or 0),
                "last_modified": item.get("lastModified"),
                "pipeline_tag": item.get("pipeline_tag"),
                "tags": [str(tag) for tag in (item.get("tags") or [])[:12]],
                "url": f"https://huggingface.co/{model_id}",
                "parameter_billions": self._parameter_billions(model_id),
            })
        return results

    async def download(self, user_id: str, model: str) -> dict[str, Any]:
        model = model.strip()
        parsed = urlsplit(model)
        if parsed.scheme:
            parts = parsed.path.strip("/").split("/")
            if parsed.scheme != "https" or parsed.hostname != "huggingface.co" or len(parts) != 2:
                raise ModelManagerError("Hugging Face 저장소 URL만 다운로드할 수 있습니다.")
            model = f"https://huggingface.co/{parts[0]}/{parts[1]}"
        elif not _MODEL_ID.fullmatch(model):
            raise ModelManagerError("모델 ID는 owner/repository 형식이어야 합니다.")
        model_id = model.removeprefix("https://huggingface.co/")
        size = self._parameter_billions(model_id)
        if size is None or size > 3:
            raise ModelManagerError("3B 이하로 확인되는 LLM만 다운로드할 수 있습니다.")
        await self.user_jobs(user_id)
        async with self._state_lock:
            state = self._read_state(); jobs = state.get(user_id, [])
            existing = next((job for job in jobs if str(job.get("model") or "").casefold() == model_id.casefold() and job.get("status") not in {"failed", "cancelled", "canceled"}), None)
            if existing:
                return existing
            used = sum(int(job.get("total_size_bytes") or self.reservation_bytes) for job in jobs if job.get("status") not in {"failed", "cancelled", "canceled"})
            if used + self.reservation_bytes > self.quota_bytes:
                raise ModelManagerConflict("사용자 모델 저장 한도 10GB를 초과합니다.")
            result = await self._request("POST", "/models/download", json_body={"model": model, "quantization": "Q4_K_M"})
            status = str(result.get("status") or "pending")
            record = {**result, "model": model_id, "status": status, "reserved_bytes": self.reservation_bytes}
            if not record.get("job_id") and status == "already_downloaded":
                record["job_id"] = f"existing-{hashlib.sha256(model_id.encode()).hexdigest()[:16]}"
                record["status"] = "completed"
                available = await self.models()
                needle = re.sub(r"[^a-z0-9]", "", model_id.split("/", 1)[-1].casefold())
                match = next((item for item in available.get("models") or [] if needle in re.sub(r"[^a-z0-9]", "", f"{item.get('key','')} {item.get('display_name','')}".casefold())), None)
                if match:
                    record["total_size_bytes"] = int(match.get("size_bytes") or 0)
            jobs.append(record); state[user_id] = jobs; await asyncio.to_thread(self._write_state, state)
            return record

    async def download_status(self, job_id: str) -> dict[str, Any]:
        job_id = self._validate_opaque(job_id, "다운로드 작업 ID")
        return await self._request("GET", f"/models/download/status/{job_id}")

    async def dismiss_download(self, user_id: str, job_id: str) -> dict[str, Any]:
        job_id = self._validate_opaque(job_id, "다운로드 작업 ID")
        async with self._state_lock:
            state = self._read_state()
            jobs = state.get(user_id, [])
            target = next((job for job in jobs if str(job.get("job_id") or "") == job_id), None)
            if target is None:
                return {"dismissed": False, "job_id": job_id}
            status = str(target.get("status") or "").casefold()
            if status not in {"failed", "cancelled", "canceled"}:
                raise ModelManagerConflict("실패하거나 취소된 다운로드만 닫을 수 있습니다.")
            state[user_id] = [job for job in jobs if str(job.get("job_id") or "") != job_id]
            await asyncio.to_thread(self._write_state, state)
            return {"dismissed": True, "job_id": job_id}

    async def user_jobs(self, user_id: str, refresh: bool = True) -> dict[str, Any]:
        async with self._state_lock:
            state = self._read_state(); jobs = state.get(user_id, [])
            deduplicated: dict[str, dict[str, Any]] = {}
            for raw in jobs:
                job = dict(raw); model = str(job.get("model") or "")
                if not model:
                    continue
                if not job.get("job_id"):
                    job["job_id"] = f"existing-{hashlib.sha256(model.encode()).hexdigest()[:16]}"
                if job.get("status") == "already_downloaded":
                    job["status"] = "completed"
                key = model.casefold()
                current = deduplicated.get(key)
                if current is None or (job.get("job_id") and not str(job["job_id"]).startswith("existing-")):
                    deduplicated[key] = job
            jobs = list(deduplicated.values())
            missing_sizes = [job for job in jobs if job.get("status") in {"completed", "complete", "downloaded"} and not job.get("total_size_bytes")]
            if missing_sizes:
                try:
                    available = await self.models()
                    for job in missing_sizes:
                        owned = self._model_identity(str(job.get("model") or "").split("/", 1)[-1])
                        match = next((item for item in available.get("models") or [] if owned and (owned in self._model_identity(f"{item.get('key','')} {item.get('display_name','')}") or self._model_identity(f"{item.get('key','')} {item.get('display_name','')}") in owned)), None)
                        if match and match.get("size_bytes"):
                            job["total_size_bytes"] = int(match["size_bytes"])
                except ModelManagerError:
                    pass
            if refresh:
                for job in jobs:
                    if job.get("job_id") and not str(job["job_id"]).startswith("existing-") and str(job.get("status", "")).casefold() not in {"completed", "complete", "failed", "cancelled", "canceled"}:
                        try: job.update(await self.download_status(str(job["job_id"])))
                        except ModelManagerError: pass
                state[user_id] = jobs; await asyncio.to_thread(self._write_state, state)
            used = sum(int(job.get("total_size_bytes") or job.get("reserved_bytes") or 0) for job in jobs if job.get("status") not in {"failed", "cancelled", "canceled"})
            return {"jobs": jobs, "quota_bytes": self.quota_bytes, "used_bytes": used}

    async def load(self, model_key: str, context_length: int) -> dict[str, Any]:
        model_key = self._validate_opaque(model_key, "모델 키")
        available = await self.models()
        companion = self.settings.llm_companion_model.casefold()
        models = available.get("models") or []
        requested = next((model for model in models if str(model.get("key") or "") == model_key), None)
        if requested and requested.get("loaded_instances"):
            return {
                "already_loaded": True,
                "model_key": model_key,
                "loaded_instances": requested.get("loaded_instances"),
            }
        # The companion is unloaded before a direct model is loaded, so count
        # the resource state that will remain after that transition.
        loaded_model_count = sum(
            1 for model in models
            if model.get("loaded_instances")
            and companion not in str(model.get("key") or "").casefold()
        )
        if loaded_model_count >= self.max_loaded_models:
            raise ModelManagerConflict("리소스가 부족하여 로드가 제한됩니다.")
        for model in models:
            if companion not in str(model.get("key") or "").casefold():
                continue
            for instance in model.get("loaded_instances") or []:
                instance_id = str(instance.get("id") or "")
                if instance_id:
                    await self.unload(instance_id)
        return await self._request("POST", "/models/load", json_body={
            "model": model_key,
            "context_length": context_length,
            "flash_attention": True,
            "offload_kv_cache_to_gpu": True,
            "echo_load_config": True,
        })

    async def unload(self, instance_id: str) -> dict[str, Any]:
        instance_id = self._validate_opaque(instance_id, "모델 인스턴스 ID")
        return await self._request("POST", "/models/unload", json_body={"instance_id": instance_id})

    async def delete(self, model_key: str) -> dict[str, Any]:
        model_key = self._validate_opaque(model_key, "모델 키")
        root = self.settings.lmstudio_model_root
        if root is None:
            raise ModelManagerUnavailable("이 Gateway에서는 모델 파일 삭제가 설정되지 않았습니다.")
        models = await self.models()
        for model in models.get("models") or []:
            if str(model.get("key") or "") == model_key and model.get("loaded_instances"):
                raise ModelManagerConflict("로드된 모델은 먼저 언로드해야 삭제할 수 있습니다.")
        target = await asyncio.to_thread(self._resolve_cli_model_path, model_key, root)
        await asyncio.to_thread(target.unlink)
        parent = target.parent
        root_resolved = root.resolve()
        while parent != root_resolved and parent.is_relative_to(root_resolved):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return {"deleted": True, "model_key": model_key}

    def _resolve_cli_model_path(self, model_key: str, root: Path) -> Path:
        root = root.resolve()
        if not root.is_dir():
            raise ModelManagerUnavailable("설정된 LM Studio 모델 폴더를 찾을 수 없습니다.")
        executable = shutil.which(self.settings.lmstudio_cli)
        if executable is None:
            raise ModelManagerUnavailable("Gateway에서 lms CLI를 찾을 수 없습니다.")
        try:
            completed = subprocess.run(
                [executable, "ls", "--json"], check=True, capture_output=True,
                text=True, timeout=20, shell=False,
            )
            payload = json.loads(completed.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise ModelManagerUnavailable("lms CLI로 모델 파일을 확인하지 못했습니다.") from exc
        items = payload.get("models", []) if isinstance(payload, dict) else payload
        for item in items if isinstance(items, list) else []:
            if str(item.get("modelKey") or item.get("key") or "") != model_key:
                continue
            raw_path = item.get("path")
            if not raw_path:
                break
            target = Path(str(raw_path))
            target = target.resolve() if target.is_absolute() else (root / target).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ModelManagerUnavailable("모델 파일 경로가 허용된 폴더 밖에 있습니다.")
            return target
        raise ModelManagerUnavailable("lms CLI 목록에서 정확한 모델 파일을 찾지 못했습니다.")
