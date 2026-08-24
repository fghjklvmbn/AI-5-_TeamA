FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py server.py lmstudio_logs.py ./
ENTRYPOINT ["python", "server.py", "--service", "llm", "--host", "0.0.0.0", "--port", "8101", "--process-names", "lm-studio,lms,llmster", "--health-url", "http://127.0.0.1:1234/api/v1/models", "--gpu"]
