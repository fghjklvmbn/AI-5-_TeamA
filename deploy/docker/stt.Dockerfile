ARG MODEL_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${MODEL_BASE_IMAGE}

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MEMORYPAL_STT_MODEL_DIR=/models/whisper

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -n "$TORCH_INDEX_URL" ]; then \
      python -m pip install --no-cache-dir torch torchaudio --index-url "$TORCH_INDEX_URL"; \
    fi

COPY backend/STT_backend_server/requirements.txt /tmp/stt-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/stt-requirements.txt

RUN groupadd --system --gid 10002 memorypal-model \
    && useradd --system --uid 10002 --gid memorypal-model \
      --create-home --home-dir /home/memorypal-model memorypal-model \
    && mkdir -p /models/whisper \
    && chown -R memorypal-model:memorypal-model /models /home/memorypal-model

COPY --chown=memorypal-model:memorypal-model \
  backend/STT_backend_server /app/backend/STT_backend_server

WORKDIR /app/backend/STT_backend_server
USER memorypal-model

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--forwarded-allow-ips=*"]

