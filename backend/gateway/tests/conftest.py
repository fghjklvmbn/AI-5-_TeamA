from __future__ import annotations

import os


# Gateway settings fail closed. Tests must opt into explicit, deterministic
# credentials before importing application modules that call load_settings().
os.environ["MEMORYPAL_JWT_SECRET"] = "gateway-test-jwt-secret-" + "j" * 48
os.environ["MEMORYPAL_MODEL_SERVICE_TOKEN"] = "model-service-test-token-" + "m" * 48
os.environ.pop("MEMORYPAL_JWT_SECRET_FILE", None)
os.environ.pop("MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", None)
