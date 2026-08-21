from __future__ import annotations

import os


# Gateway settings fail closed. Tests must opt into explicit, deterministic
# credentials before importing application modules that call load_settings().
os.environ["MEMORYPAL_JWT_SECRET"] = "gateway-test-jwt-secret-" + "j" * 48
os.environ["MEMORYPAL_MODEL_SERVICE_TOKEN"] = "model-service-test-token-" + "m" * 48
os.environ["MEMORYPAL_ARCHIVE_SERVICE_TOKEN"] = "archive-service-test-token-" + "a" * 48
# Empty process values also prevent python-dotenv from repopulating *_FILE
# settings from a developer's ignored root .env during module import.
os.environ["MEMORYPAL_JWT_SECRET_FILE"] = ""
os.environ["MEMORYPAL_MODEL_SERVICE_TOKEN_FILE"] = ""
os.environ["MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE"] = ""
os.environ["MEMORYPAL_LLM_CHARACTER_CUE_ENABLED"] = "false"
