from memorypal_api.database import Database


def create_user(db: Database, email: str):
    return db.create_user(email, "테스트", "hash", "salt")


def test_delete_session_removes_its_conversations(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    user = create_user(db, "owner@example.com"); session = db.create_session(user["id"], "삭제할 대화")
    db.save_conversation(user["id"], session["id"], "질문", "답변")
    assert db.delete_session(user["id"], session["id"])
    assert db.get_history(user["id"], session["id"]) == []


def test_delete_session_rejects_another_users_session(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    owner = create_user(db, "owner@example.com"); other = create_user(db, "other@example.com")
    session = db.create_session(owner["id"])
    assert db.delete_session(other["id"], session["id"]) is False


def test_personalized_voice_ownership_is_scoped_per_user(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    owner = create_user(db, "owner@example.com"); other = create_user(db, "other@example.com")
    db.add_user_voice(owner["id"], "voice")
    assert db.user_has_voice(owner["id"], "voice")
    assert not db.user_has_voice(other["id"], "voice")


def test_delete_personalized_voice_removes_only_the_owners_mapping(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    owner = create_user(db, "owner@example.com"); other = create_user(db, "other@example.com")
    db.add_user_voice(owner["id"], "owner-voice")
    db.add_user_voice(other["id"], "other-voice")

    assert db.delete_user_voice(owner["id"], "owner-voice")
    assert not db.user_has_voice(owner["id"], "owner-voice")
    assert db.user_has_voice(other["id"], "other-voice")
    assert not db.delete_user_voice(owner["id"], "other-voice")


def test_attachments_are_scoped_and_removed_with_session(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    owner = create_user(db, "owner@example.com"); other = create_user(db, "other@example.com")
    session = db.create_session(owner["id"])
    attachment = db.create_attachment(owner["id"], session["id"], "guide.txt", "text/plain", 12, "내용")
    assert db.get_attachment(other["id"], attachment["id"]) is None
    db.delete_session(owner["id"], session["id"])
    assert db.get_attachment(owner["id"], attachment["id"]) is None


def test_regenerate_updates_only_the_assistant_response(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    owner = create_user(db, "owner@example.com"); session = db.create_session(owner["id"])
    first = db.save_conversation(owner["id"], session["id"], "같은 질문", "기존 답변")
    updated = db.update_conversation_response(owner["id"], first["id"], "새 답변", "new.wav")
    assert updated["user_text"] == "같은 질문"
    assert updated["assistant_text"] == "새 답변"
    assert len(db.get_history(owner["id"], session["id"])) == 1


def test_session_working_memory_is_scoped_and_deleted_with_session(tmp_path):
    db = Database(tmp_path / "memorypal.db"); db.initialize()
    owner = create_user(db, "owner@example.com"); other = create_user(db, "other@example.com")
    session = db.create_session(owner["id"])
    db.upsert_session_working_memory(owner["id"], session["id"], "최근 대화", 3)
    assert db.get_session_working_memory(owner["id"], session["id"]) == "최근 대화"
    assert db.get_session_working_memory(other["id"], session["id"]) == ""
    db.delete_session(owner["id"], session["id"])
    assert db.get_session_working_memory(owner["id"], session["id"]) == ""
