import os
import warnings

import torch
import whisper


def resolve_device() -> tuple[str, str]:
    requested = os.getenv(
        "MEMORYPAL_STT_DEVICE",
        os.getenv("MEMORYPAL_DEVICE", "auto"),
    ).strip().lower()
    if requested not in {"auto", "cpu", "cuda", "rocm"}:
        raise RuntimeError("MEMORYPAL_STT_DEVICE must be auto, cpu, cuda, or rocm")
    cuda_available = bool(torch.cuda.is_available())
    rocm_available = bool(
        cuda_available and getattr(getattr(torch, "version", None), "hip", None)
    )
    if requested in {"cuda", "rocm"} and not cuda_available:
        warnings.warn(
            f"{requested.upper()} was requested for STT but is unavailable; "
            "falling back to CPU.",
            RuntimeWarning,
        )
        return "cpu", "cpu"
    if requested == "rocm" and not rocm_available:
        warnings.warn(
            "ROCm was requested for STT but this PyTorch build has no HIP runtime; "
            "falling back to CPU.",
            RuntimeWarning,
        )
        return "cpu", "cpu"
    if requested == "auto":
        accelerator = "rocm" if rocm_available else "cuda" if cuda_available else "cpu"
    elif requested == "cuda" and rocm_available:
        accelerator = "rocm"
    else:
        accelerator = requested
    # PyTorch intentionally exposes ROCm devices through its torch.cuda API.
    return accelerator, "cuda" if accelerator in {"cuda", "rocm"} else "cpu"


accelerator, device = resolve_device()
model_name = os.getenv("MEMORYPAL_STT_MODEL", "turbo").strip() or "turbo"
download_root = os.getenv("MEMORYPAL_STT_MODEL_DIR", "").strip() or None

model = whisper.load_model(model_name, device=device, download_root=download_root)
