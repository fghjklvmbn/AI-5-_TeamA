from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from pathlib import Path

import pytest


MODEL_FILE = Path(__file__).resolve().parents[1] / "models" / "whisper_model.py"


def _load_model_module(monkeypatch, *, requested: str, cuda: bool, hip: str | None):
    calls = []
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: cuda)
    torch.version = types.SimpleNamespace(hip=hip)
    whisper = types.ModuleType("whisper")
    whisper.load_model = lambda *args, **kwargs: calls.append((args, kwargs)) or object()
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "whisper", whisper)
    monkeypatch.setenv("MEMORYPAL_STT_DEVICE", requested)
    monkeypatch.setenv("MEMORYPAL_STT_MODEL", "turbo")
    monkeypatch.delenv("MEMORYPAL_STT_MODEL_DIR", raising=False)

    name = f"memorypal_stt_device_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, MODEL_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_stt_auto_uses_cpu_without_gpu(monkeypatch):
    module, calls = _load_model_module(
        monkeypatch, requested="auto", cuda=False, hip=None,
    )

    assert module.accelerator == "cpu"
    assert module.device == "cpu"
    assert calls[0][1]["device"] == "cpu"


def test_stt_auto_recognizes_rocm_through_pytorch_cuda_api(monkeypatch):
    module, calls = _load_model_module(
        monkeypatch, requested="auto", cuda=True, hip="7.2.1",
    )

    assert module.accelerator == "rocm"
    assert module.device == "cuda"
    assert calls[0][1]["device"] == "cuda"


def test_stt_explicit_cuda_falls_back_to_cpu(monkeypatch):
    with pytest.warns(RuntimeWarning):
        module, calls = _load_model_module(
            monkeypatch, requested="cuda", cuda=False, hip=None,
        )

    assert module.accelerator == "cpu"
    assert module.device == "cpu"
    assert calls[0][1]["device"] == "cpu"

