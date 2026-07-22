# MemoryPal beta

사용자의 목소리와 장기 기억을 이어 주는 크로스플랫폼 AI 대화 앱입니다.

## 구성

- `frontend`: Expo + React Native 기반 iOS/Android/Web 공용 모바일 UI
- `backend/gateway`: Python 3.12 통합 API, JWT 로그인/로그아웃, 사용자별 대화/메모리 엔진
- `backend/STT_backend_server`: Whisper Turbo 음성인식 서버
- `backend/TTS_Server`: Qwen3-TTS 음성합성 서버
- `backend/archive_service`: 음성 프로필 아카이브 서버

통합 흐름은 `Whisper Turbo → 메모리 검색 → Qwen3.5-9B → 메모리 저장 → Qwen3-TTS`입니다. 기존 모델 서버의 역할은 유지하고, 새 게이트웨이가 인증과 사용자별 컨텍스트를 책임집니다.

## 빠른 시작

1. Python 3.12에서 [백엔드 안내](backend/gateway/README.md)에 따라 통합 API를 실행합니다.
2. 루트 `.env.example`을 `.env`로 복사하고 STT, LLM, TTS, 아카이브 및 DB 주소를 한 곳에서 지정합니다.
3. [프론트 안내](frontend/README.md)에 따라 Expo 앱을 실행합니다.

API 문서는 통합 서버 실행 후 `http://localhost:8000/docs`에서 확인할 수 있습니다.

## Windows 통합 설치 및 실행

프로젝트 최상단의 파일을 순서대로 사용할 수 있습니다.

1. `install.cmd`: Python 가상환경과 Frontend 패키지를 설치하고, 기본 SQLite DB 스키마와 웹 번들을 생성합니다.
2. `run.cmd`: Gateway(8000)와 Frontend(8081)를 함께 백그라운드로 실행합니다.
3. `stop.cmd`: `run.cmd`로 시작한 Gateway와 Frontend만 안전하게 종료하고 로그는 보존합니다.
4. `uninstall.cmd`: 실행 프로세스를 종료하고 `.venv`, `node_modules`, 빌드, `__pycache__`를 제거합니다.

LLM 서버에서 모델을 다시 로드할 때는 `load-llm.cmd default` 또는 `load-llm.cmd companion`을 사용합니다. GTX 1660 SUPER에 두 모델이 동시에 상주하지 않도록 기존 모델을 먼저 내리고, 선택한 모델을 LM Studio의 `--gpu max`(전체 GPU offload)로 로드합니다.

실제 비밀번호와 JWT 키가 들어가는 루트 `.env`는 Git에서 제외됩니다. 일반 삭제는 사용자 DB와
`.env`를 보존합니다. 로컬 DB와 업로드 파일까지 지우려는 경우에만
PowerShell에서 `uninstall.ps1 -RemoveData`를 실행하세요. 외부 PostgreSQL과 STT/TTS/LLM 모델
데이터는 기존 서비스 인프라이므로 이 스크립트가 변경하거나 삭제하지 않습니다.

기본 실행은 설치가 간단한 SQLite/로컬 큐를 유지합니다. 중·대형 운영 전환 시에는
[`deploy/scale/README.md`](deploy/scale/README.md)의 PostgreSQL+pgvector, Redis,
분리 worker 및 기존 DB 이관 절차를 사용하세요.
