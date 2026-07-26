from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, VoiceProfile
from services.voice_service import VoiceService


def make_database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_voice(db, voice_id: str, audio_path: Path):
    db.add(VoiceProfile(
        id=voice_id,
        voice_name="테스트 음성",
        audio_path=str(audio_path),
        reference_text="안녕하세요.",
        description="삭제 테스트",
    ))
    db.commit()


def test_delete_voice_removes_database_row_and_uploaded_file(tmp_path):
    upload_dir = tmp_path / "voice_uploads"
    upload_dir.mkdir()
    audio_path = upload_dir / "sample.webm"
    audio_path.write_bytes(b"voice")
    db = make_database()
    add_voice(db, "voice-1", audio_path)

    assert VoiceService.delete(db, "voice-1", upload_dir)
    assert db.query(VoiceProfile).filter(VoiceProfile.id == "voice-1").first() is None
    assert not audio_path.exists()
    assert list(upload_dir.iterdir()) == []


def test_delete_voice_rejects_file_outside_managed_upload_directory(tmp_path):
    upload_dir = tmp_path / "voice_uploads"
    upload_dir.mkdir()
    outside_file = tmp_path / "default.wav"
    outside_file.write_bytes(b"default")
    db = make_database()
    add_voice(db, "voice-2", outside_file)

    with pytest.raises(ValueError, match="관리되는 개인화 음성"):
        VoiceService.delete(db, "voice-2", upload_dir)

    assert db.query(VoiceProfile).filter(VoiceProfile.id == "voice-2").first() is not None
    assert outside_file.exists()


def test_delete_voice_resolves_archive_relative_audio_path(tmp_path):
    upload_dir = tmp_path / "private_voice_uploads"
    upload_dir.mkdir()
    audio_path = upload_dir / "relative.webm"
    audio_path.write_bytes(b"voice")
    db = make_database()
    add_voice(db, "voice-3", Path("private_voice_uploads/relative.webm"))

    assert VoiceService.delete(db, "voice-3", upload_dir, tmp_path)
    assert db.query(VoiceProfile).filter(VoiceProfile.id == "voice-3").first() is None
    assert not audio_path.exists()
