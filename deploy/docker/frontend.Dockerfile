FROM node:22-bookworm-slim AS build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund

COPY frontend/ ./

ARG MEMORYPAL_MAIN_PUBLIC_API_URL=http://127.0.0.1:8000/v1
ENV MEMORYPAL_MAIN_PUBLIC_API_URL=${MEMORYPAL_MAIN_PUBLIC_API_URL}

RUN npm run build:web

FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup -S -g 10001 memorypal \
    && adduser -S -D -H -u 10001 -G memorypal memorypal

WORKDIR /app

COPY --chown=memorypal:memorypal scripts/static_server.py /app/static_server.py
COPY --from=build --chown=memorypal:memorypal /app/frontend/dist-main /app/dist-main

USER memorypal
EXPOSE 8081

CMD ["python", "/app/static_server.py", "--directory", "/app/dist-main", "--host", "0.0.0.0", "--port", "8081", "--prefix", "/api_memoripal/main"]
