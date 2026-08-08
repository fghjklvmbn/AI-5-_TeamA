archive_service port : 8004

최초 실행 및 SQL 변경 후 마이그레이션 명령어
python migrate.py

서버 실행 명령어 (시작 시에는 읽기 전용 스키마/체크섬 검증만 수행)
uvicorn app:app --reload --port 8004
