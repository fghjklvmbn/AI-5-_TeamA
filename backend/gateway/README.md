# MemoryPal 통합 API

Python 3.12용 API 게이트웨이입니다. 기존 모델 서버는 그대로 두고 다음 순서로 연결합니다.

1. `whisper-turbo` STT 서버가 짧은 녹음 조각을 자막으로 변환합니다.
2. 사용자별 메모리 엔진이 관련 기억과 최근 대화를 검색합니다.
3. `Qwen3.5-4B` OpenAI 호환 서버가 답변하고, 새 장기 기억 후보를 추출합니다.
4. 선택한 음성 프로필과 `Qwen3-TTS`가 음성 답변을 만듭니다.

## 실행

```powershell
cd backend/gateway
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
python -m memorypal_api
```

환경 변수는 `.env.example`을 참고하세요. 실제 서비스에서는 반드시 `MEMORYPAL_JWT_SECRET`을 긴 무작위 값으로 바꾸고, 실행 환경에서 환경 변수로 주입해야 합니다.

주요 API는 `/v1/auth/*`, `/v1/sessions`, `/v1/chat/messages`, `/v1/voice/transcribe`, `/v1/memories`이며 OpenAPI 문서는 `/docs`에서 확인할 수 있습니다.

