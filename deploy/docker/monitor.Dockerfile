FROM python:3.12-slim-bookworm

WORKDIR /app
COPY backend/monitor_agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/monitor_agent/ ./

ENTRYPOINT ["python", "server.py"]
