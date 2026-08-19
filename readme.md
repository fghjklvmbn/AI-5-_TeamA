# MemoryPal beta

사용자의 목소리와 장기 기억을 결합한 개인화 AI 대화 프로젝트입니다.

## 구성

- `frontend`: Expo + React Native 기반 Web/iOS/Android UI
- `admin`: 개인정보를 노출하지 않는 운영 관리자 콘솔
- `backend/gateway`: 인증, 대화, 기억, 작업 상태를 담당하는 통합 API
- `backend/STT_backend_server`: Whisper 기반 음성 인식 서비스
- `backend/TTS_Server`: Qwen3-TTS 기반 음성 생성 서비스
- `backend/archive_service`: 개인화 음성 등록 및 공개 음성 파일 서비스

브라우저와 앱은 Gateway만 호출합니다. Gateway가 내부 STT/TTS/Archive/LLM을 호출하며, STT와 TTS는 서버 전용 Bearer 토큰 없이는 요청을 받지 않습니다. CORS는 브라우저 출처 제한일 뿐 인증 수단으로 사용하지 않습니다.

## Windows 설치와 실행

Python 3.12, Node.js 20 이상과 `STT`, `qwen3-tts`, `archive` Conda 환경을 준비한 뒤 프로젝트 루트에서 실행합니다.

1. `install.cmd`: Python/Node 의존성을 설치하고 main·project3 정적 빌드를 각각 생성합니다.
2. 생성된 `.env`에서 내부 서비스 및 공개 API 주소를 환경에 맞게 확인합니다.
3. `run.cmd`: Gateway(8010), STT(8001), TTS(8003), Archive(8004), Frontend(8081), Admin(8082)과 필요 시 portrait worker를 시작합니다.
4. `stop.cmd`: 위 프로세스 트리를 검증한 뒤 종료합니다.

Project3를 별도 포트와 별도 정적 산출물로 실행하려면 main의 STT/TTS가 정상 실행 중인 상태에서 `run-sidecar.cmd`를 사용합니다. 종료는 `stop-sidecar.cmd`입니다.

실행 중 후반 서비스의 readiness 또는 배포 manifest 검사가 실패하면, 그 실행 명령에서 새로 시작한 프로세스만 역순으로 롤백합니다. 기존에 실행 중이던 서비스는 건드리지 않습니다.

## 비밀값

`install.cmd`는 JWT 키와 STT/TTS 서비스 토큰을 Git에서 제외된 `.runtime/secrets/` 아래에 생성합니다. 실제 비밀값을 `.env`, `EXPO_PUBLIC_*`, `VITE_*`에 넣지 마세요. 관리형 배포에서는 다음 직접 환경 변수 또는 대응하는 `*_FILE` 중 정확히 하나만 사용합니다.

- `MEMORYPAL_JWT_SECRET` / `MEMORYPAL_JWT_SECRET_FILE`
- `MEMORYPAL_MODEL_SERVICE_TOKEN` / `MEMORYPAL_MODEL_SERVICE_TOKEN_FILE`
- `MEMORYPAL_ARCHIVE_SERVICE_TOKEN` / `MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE`

값은 32자 이상이어야 하며 누락, 예시값, 약한 파일, 직접값과 파일의 동시 설정은 시작 단계에서 거부됩니다. 일반 `uninstall.cmd`는 DB·업로드·runtime 비밀값을 보존합니다. 모두 삭제하려는 경우에만 PowerShell에서 `./uninstall.ps1 -RemoveData`를 실행하세요.

## 정적 빌드 프로필

main과 project3는 동일한 `dist`를 공유하지 않습니다.

- Frontend: `frontend/dist-main`, `frontend/dist-project3`
- Admin: `admin/dist-main`, `admin/dist-project3`

각 빌드에는 profile/base URL/API URL을 기록한 `deployment-profile.json`이 포함됩니다. 실행 스크립트는 로컬 산출물과 이미 포트를 점유한 서버의 manifest를 모두 검증해 잘못된 프로필 제공을 차단합니다.

## 배포와 데이터베이스

외부 Nginx는 Gateway와 STT/TTS 경로를 이 컴퓨터로 전달합니다. 브라우저와 앱은 Gateway만 호출하며, STT 변환과 TTS 합성 경로는 공용 API가 아니라 서버 전용 Bearer 토큰으로 보호됩니다. 생성 음성 파일은 `/api_memoripal/tts/outputs/`에서 읽습니다. Archive API와 테스트 UI는 외부에서 차단합니다. 자세한 설정은 [배포 안내](deploy/README.md)를 참고하세요.

PostgreSQL+pgvector, Redis와 분리 worker 구성은 [확장 배포 안내](deploy/scale/README.md)를 따릅니다. 애플리케이션 시작 시 DDL을 실행하지 않으며, 체크섬이 기록된 독립 마이그레이션 작업이 먼저 성공해야 합니다. SQLite 데이터 이관 도구는 충돌 행의 내용과 테이블별 정확한 행 수까지 검증합니다.

Gateway API 문서는 실행 후 `http://127.0.0.1:8010/docs`에서 확인할 수 있습니다.
