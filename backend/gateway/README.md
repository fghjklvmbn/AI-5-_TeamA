# MemoryPal 통합 API

Python 3.12용 API 게이트웨이입니다. 기존 모델 서버는 그대로 두고 다음 순서로 연결합니다.

1. `whisper-turbo` STT 서버가 짧은 녹음 조각을 자막으로 변환합니다.
2. 사용자별 메모리 엔진이 관련 기억과 최근 대화를 검색합니다.
3. 인터넷 사용이 활성화된 요청은 `DDGS` 메타검색 결과를 이번 답변의 임시 문맥으로 추가합니다.
4. `Qwen3.5-9B` OpenAI 호환 서버가 답변하고, 새 장기 기억 후보를 추출합니다.
5. 선택한 음성 프로필과 `Qwen3-TTS`가 음성 답변을 만듭니다.

## 실행

```powershell
cd backend/gateway
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item ..\..\.env.example ..\..\.env
python -m memorypal_api
```

모든 서비스 환경 변수는 프로젝트 루트 `.env.example` 한 곳을 참고하세요. 실제 서비스에서는 반드시 `MEMORYPAL_JWT_SECRET`과 DB 접속 정보를 루트 `.env`에서 설정해야 합니다.

웹 검색 결과 수는 `MEMORYPAL_WEB_SEARCH_MAX_RESULTS`로 1~6개 범위에서 조정할 수 있으며 기본값은 4입니다. 검색 결과는 DB나 장기 기억에 저장하지 않습니다.

주요 API는 `/v1/auth/*`, `/v1/sessions`, `/v1/chat/messages`, `/v1/voice/transcribe`, `/v1/memories`이며 OpenAPI 문서는 `/docs`에서 확인할 수 있습니다.

## 자화상 분석

인증된 사용자는 `POST /v1/portrait/generate`에
`{"persona":"default"}` 또는 `{"persona":"emotional_companion"}`를 보내 분석을 시작하고,
`GET /v1/portrait`를 polling해 `queued → analyzing → complete` 진행 상태를 확인합니다.
세션별 일상·감정·자기서술에는 높은 가중치를, 순수 지식 질문에는 0의 가중치를 적용합니다.
특징과 벡터는 사용자별 DB에 저장하며, LM Studio의
`MEMORYPAL_EMBEDDING_MODEL`(기본 `text-embedding-nomic-embed-text-v1.5`)을 우선 사용합니다.
임베딩 서버가 없거나 응답 차원이 맞지 않으면 결정적 로컬 한국어 문자 n-gram 벡터로 전환하고,
실제 사용 방식은 응답의 `vector_method`에서 확인할 수 있습니다.

## 중·대형 운영 프로필과 상태관리

`MEMORYPAL_DATABASE_URL`이 없으면 기존 SQLite를 사용하고, PostgreSQL URL이 있으면
connection pool과 pgvector를 사용하는 `memorypal_gateway` schema로 전환합니다.
`MEMORYPAL_TASK_QUEUE_MODE=redis`에서는 자화상 분석이 Redis 분산 큐와 별도 worker로
실행되며 `run.cmd`/`stop.cmd`가 worker도 함께 관리합니다.

모든 HTTP 거래는 요청 ID와 correlation ID, 현재 작업 상태, append-only 상태 전이,
metadata-only 사용자 거래 이벤트, transactional outbox로 기록됩니다. 대화·첨부·음성
본문, JWT와 비밀번호는 운영 이벤트에 저장하지 않습니다. PostgreSQL/Redis 시작,
SQLite 데이터 이관, 상태 전이와 향후 관리자 read model은
[`deploy/scale`](../../deploy/scale/README.md) 문서를 참고하세요.

