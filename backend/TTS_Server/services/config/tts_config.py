import os


TTS_HOST = os.getenv("MEMORYPAL_TTS_PUBLIC_URL", "http://127.0.0.1:8003").rstrip("/")
