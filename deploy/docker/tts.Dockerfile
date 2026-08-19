ARG MODEL_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${MODEL_BASE_IMAGE}

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/huggingface

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 sox \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -n "$TORCH_INDEX_URL" ]; then \
      python -m pip install --no-cache-dir torch torchaudio --index-url "$TORCH_INDEX_URL"; \
    fi

COPY backend/TTS_Server/requirements.txt /tmp/tts-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/tts-requirements.txt

RUN groupadd --system --gid 10002 memorypal-model \
    && useradd --system --uid 10002 --gid memorypal-model \
      --create-home --home-dir /home/memorypal-model memorypal-model \
    && mkdir -p \
      /models/huggingface \
      /app/backend/TTS_Server/outputs \
      /app/backend/TTS_Server/reference_audio \
      /app/backend/archive_service/voice_uploads \
      /data/private-voice-uploads \
    && chown -R memorypal-model:memorypal-model \
      /models /app /data /home/memorypal-model

COPY --chown=memorypal-model:memorypal-model \
  backend/TTS_Server /app/backend/TTS_Server

WORKDIR /app/backend/TTS_Server
USER memorypal-model

EXPOSE 8003

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003", "--proxy-headers", "--forwarded-allow-ips=*"]
