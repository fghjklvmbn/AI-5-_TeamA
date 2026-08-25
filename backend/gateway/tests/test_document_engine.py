import pytest

from memorypal_api.database import Database
from memorypal_api.services.document_engine import DocumentEngine, DocumentExtractionError


def test_extracts_utf8_and_cp949_text(tmp_path):
    engine = DocumentEngine(Database(tmp_path / "memorypal.db"))
    assert engine.extract("note.txt", "회의는 금요일입니다.".encode()) == "회의는 금요일입니다."
    assert engine.extract("note.csv", "이름,상태\n민수,완료".encode("cp949")) == "이름,상태\n민수,완료"


def test_retrieves_relevant_attachment_chunks(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    user = db.create_user("reader@example.com", "독자", "hash", "salt")
    session = db.create_session(user["id"])
    db.create_attachment(user["id"], session["id"], "project.md", "text/markdown", 100, "배포 일정은 8월 20일입니다.\n\n테스트 담당자는 지민입니다.")
    context = DocumentEngine(db).retrieve_context(user["id"], session["id"], "배포 일정이 언제야?")
    assert "project.md" in context and "8월 20일" in context


def test_consumed_attachment_is_reused_only_when_user_mentions_it(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    user = db.create_user("reuse@example.com", "재사용", "hash", "salt")
    session = db.create_session(user["id"])
    attachment = db.create_attachment(
        user["id"], session["id"], "project-plan.md", "text/markdown", 100,
        "프로젝트 배포 일정은 8월 20일입니다.",
    )
    db.consume_attachments(user["id"], [attachment["id"]])
    engine = DocumentEngine(db)

    assert engine.retrieve_context(user["id"], session["id"], "오늘 날씨는?") == ""
    reused = engine.retrieve_context(
        user["id"], session["id"], "전에 올린 project-plan.md의 일정을 알려줘",
    )
    assert "project-plan.md" in reused
    assert "8월 20일" in reused
    just_uploaded = engine.retrieve_context(
        user["id"], session["id"], "방금 올린 문서를 기준으로 일정도 알려줘",
    )
    assert "project-plan.md" in just_uploaded
    assert "8월 20일" in just_uploaded


def test_rejects_unsupported_or_empty_files(tmp_path):
    engine = DocumentEngine(Database(tmp_path / "memorypal.db"))
    with pytest.raises(DocumentExtractionError):
        engine.extract("image.png", b"png")
    with pytest.raises(DocumentExtractionError):
        engine.extract("empty.txt", b"  \n")
