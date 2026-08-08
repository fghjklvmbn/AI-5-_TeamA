FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 10001 memorypal \
    && useradd --system --uid 10001 --gid memorypal --home-dir /nonexistent memorypal

COPY backend/archive_service/requirements.txt /tmp/archive-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/archive-requirements.txt

COPY --chown=memorypal:memorypal backend/archive_service /app/backend/archive_service
RUN mkdir -p \
      /app/backend/archive_service/voice_uploads \
      /data/private-voice-uploads \
    && chown -R memorypal:memorypal \
      /app/backend/archive_service/voice_uploads \
      /data/private-voice-uploads

WORKDIR /app/backend/archive_service
USER memorypal

EXPOSE 8004

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8004", "--proxy-headers", "--forwarded-allow-ips=*"]

