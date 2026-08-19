# MemoryPal 공유용 소스 안내

이 배포본은 실행 중 생성되는 로컬 데이터와 비밀값을 제외한 소스 전용 패키지입니다.

## 제외된 항목

- `.env`, `.runtime/`, 비밀키와 로컬 실행 상태
- PostgreSQL/SQLite 데이터, Redis 데이터, 로그와 테스트 캐시
- `.venv/`, `node_modules/`, `.pnpm-store/` 등 설치된 의존성
- `dist-main/`, `dist-project3/` 등 다시 생성할 수 있는 빌드 결과
- 업로드한 음성, 합성 음성, 문서 업로드와 임시 출력
- Git/Codex/편집기 메타데이터와 기존 ZIP 파일

## 새 컴퓨터에서 실행

### Docker 권장

- Windows: `docker-up.cmd`
- Linux: `./docker-up.sh`
- 종료: Windows `docker-down.cmd`, Linux `./docker-down.sh`

첫 실행 시 `.runtime/docker.env`와 필요한 로컬 비밀값이 새로 생성됩니다. 기본 웹 주소는
`http://127.0.0.1:8081/api_memoripal/main/`이며, 기본 Gateway 주소는
`http://127.0.0.1:8000/v1`입니다.

### 직접 실행

Windows에서는 `install.cmd`로 의존성과 예제 환경설정을 준비한 다음 `run.cmd`를 사용합니다.
Linux 및 GPU별 실행 방법은 루트 `readme.md`와 `deploy/README.md`를 참고하세요.

## 주의사항

- 실제 `.env`나 `.runtime/`을 다시 공유하지 마세요.
- 공개 도메인은 이 소스 패키지에 고정하지 않았습니다.
- 다른 컴퓨터의 Nginx에서 접근하게 할 때만 `MEMORYPAL_PUBLIC_BIND_HOST=0.0.0.0`을 설정하고,
  방화벽에서 신뢰할 수 있는 LAN 주소만 허용하세요.
- 모델 파일은 용량과 라이선스 문제로 포함하지 않습니다. LLM/STT/TTS 모델은 실행 환경에서
  별도로 설치하거나 원격 모델 API를 설정해야 합니다.
