FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 10001 memorypal \
    && useradd --system --uid 10001 --gid memorypal --home-dir /nonexistent memorypal

COPY backend/gateway/requirements.txt /tmp/gateway-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/gateway-requirements.txt

COPY --chown=memorypal:memorypal backend/gateway /app/backend/gateway
COPY --chown=memorypal:memorypal deploy/scale/postgres/migrations /app/deploy/scale/postgres/migrations

WORKDIR /app/backend/gateway
USER memorypal

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "memorypal_api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
