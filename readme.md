# MemoryPal beta

사용자의 목소리와 장기 기억을 이어 주는 크로스플랫폼 AI 대화 앱입니다.

## 구성

- `frontend`: Expo + React Native 기반 iOS/Android/Web 공용 모바일 UI
- `backend/gateway`: Python 3.12 통합 API, JWT 로그인/로그아웃, 사용자별 대화/메모리 엔진
- `backend/STT_backend_server`: Whisper Turbo 음성인식 서버
- `backend/TTS_Server`: Qwen3-TTS 음성합성 서버
- `backend/archive_service`: 음성 프로필 아카이브 서버

통합 흐름은 `Whisper Turbo → 메모리 검색 → Qwen3.5-4B → 메모리 저장 → Qwen3-TTS`입니다. 기존 모델 서버의 역할은 유지하고, 새 게이트웨이가 인증과 사용자별 컨텍스트를 책임집니다.

## 빠른 시작

1. Python 3.12에서 [백엔드 안내](backend/gateway/README.md)에 따라 통합 API를 실행합니다.
2. STT, Qwen OpenAI 호환 서버, TTS, 아카이브 서버 주소를 `backend/gateway/.env`에 지정합니다.
3. [프론트 안내](frontend/README.md)에 따라 Expo 앱을 실행합니다.

API 문서는 통합 서버 실행 후 `http://localhost:8000/docs`에서 확인할 수 있습니다.
