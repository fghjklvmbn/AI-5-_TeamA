import hashlib
import os
import shutil
import uuid

from datetime import UTC, datetime, timedelta
from pathlib import Path

from database.models import (
    VoiceProfile
)

from repositories.voice_repository import (
    VoiceRepository
)


class VoiceService:
    _MANAGED_AUDIO_SUFFIXES = {
        ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm",
    }


    @staticmethod
    def create(
        db,
        payload
    ):

        voice = VoiceProfile(

            id=str(
                uuid.uuid4()
            ),

            voice_name=
            payload.voice_name,

            audio_path=
            payload.audio_path,

            reference_text=
            payload.reference_text,

            description=
            payload.description,

            registration_state="active",

            created_at=
            datetime.now(UTC)
        )

        return (
            VoiceRepository.create(
                db,
                voice
            )
        )

    @staticmethod
    def get_all(
        db,
        default_voice_id,
    ):

        return (
            VoiceRepository.get_all(
                db,
                default_voice_id,
            )
        )

    @staticmethod
    def get_by_id(
        db,
        voice_id,
        default_voice_id,
    ):

        return (
            VoiceRepository.get_by_id(
                db,
                voice_id,
                default_voice_id,
            )
        )

    @staticmethod
    def get_internal_all(db):
        return VoiceRepository.get_internal_all(db)

    @staticmethod
    def get_internal_by_id(db, voice_id):
        return VoiceRepository.get_internal_by_id(db, voice_id)

    @staticmethod
    def token_hash(registration_token: str) -> str:
        return hashlib.sha256(registration_token.encode("utf-8")).hexdigest()

    @staticmethod
    def create_pending(
        db,
        *,
        owner_ref: str,
        registration_token: str,
        voice_name: str,
        audio_path: Path,
        reference_text: str,
        description: str | None,
        ttl_seconds: int,
    ):
        try:
            token_hash = VoiceService.token_hash(registration_token)
            now = datetime.now(UTC)
            owner = VoiceRepository.lock_owner(db, owner_ref, now)
            if owner.state == "purged":
                raise ValueError("owner_has_been_purged")
            existing = VoiceRepository.get_by_registration_token(db, token_hash)
            if existing is not None:
                if existing.owner_ref != owner_ref:
                    raise ValueError("registration_token_conflict")
                audio_path.unlink(missing_ok=True)
                return existing, False

            voice = VoiceProfile(
                id=str(uuid.uuid4()),
                voice_name=voice_name,
                audio_path=str(audio_path.resolve()),
                reference_text=reference_text,
                description=description,
                owner_ref=owner_ref,
                registration_token_hash=token_hash,
                registration_state="pending",
                expires_at=now + timedelta(seconds=max(60, ttl_seconds)),
                created_at=now,
            )
            return VoiceRepository.create(db, voice), True
        except Exception:
            db.rollback()
            audio_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def confirm(db, voice_id: str, owner_ref: str, registration_token: str):
        owner = VoiceRepository.lock_owner(db, owner_ref, datetime.now(UTC))
        if owner.state == "purged":
            db.rollback()
            raise ValueError("owner_has_been_purged")
        voice = VoiceRepository.get_owned_registration(
            db,
            voice_id,
            owner_ref,
            VoiceService.token_hash(registration_token),
        )
        if voice is None:
            return None
        if voice.registration_state == "active":
            return voice
        if voice.expires_at is not None:
            expiry = voice.expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry <= datetime.now(UTC):
                return None
        return VoiceRepository.activate(db, voice)

    @staticmethod
    def purge_owner(
        db,
        *,
        owner_ref: str,
        private_root: Path,
        voice_id: str | None = None,
        default_voice_id: str = "00000000-0000-0000-0000-000000000001",
        legacy_root: Path | None = None,
    ) -> int:
        """Commit the tombstone/row deletion before best-effort file cleanup."""
        now = datetime.now(UTC)
        owner = VoiceRepository.lock_owner(db, owner_ref, now)
        if voice_id == default_voice_id:
            db.rollback()
            raise ValueError("default_voice_cannot_be_purged")
        if voice_id is None:
            owner.state = "purged"
            owner.purged_at = owner.purged_at or now
            voices = VoiceRepository.list_owned_voices_for_update(db, owner_ref)
        else:
            voice = VoiceRepository.get_owned_or_legacy_voice(db, voice_id, owner_ref)
            voices = [] if voice is None else [voice]
        paths = []
        for voice in voices:
            try:
                paths.append(VoiceService._private_path(
                    str(voice.audio_path), private_root,
                ))
            except ValueError:
                # Never touch a path outside the private root. The owner row
                # and profile deletion must still commit to revoke access.
                pass
            legacy_candidates = [voice.legacy_source_path]
            if voice.owner_ref is None:
                legacy_candidates.append(voice.audio_path)
            for legacy_path in legacy_candidates:
                if legacy_path and legacy_root is not None:
                    try:
                        paths.append(VoiceService._path_in_root(
                            str(legacy_path), legacy_root,
                        ))
                    except ValueError:
                        pass
        for voice in voices:
            db.delete(voice)
        db.commit()
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # The unreferenced-file reaper retries after DB-first deletion.
                pass
        return len(voices)

    @staticmethod
    def _path_in_root(audio_path: str, root_path: Path) -> Path:
        root = root_path.resolve()
        target = Path(audio_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError("audio_path_outside_allowed_root")
        return target

    @staticmethod
    def _sniff_legacy_audio_suffix(source: Path) -> str:
        """Identify only the small set of audio containers accepted by Archive."""
        try:
            with source.open("rb") as stream:
                header = stream.read(64)
        except OSError as exc:
            raise ValueError("legacy_voice_file_unreadable") from exc
        if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
            return ".wav"
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            return ".webm"
        if header.startswith(b"OggS"):
            return ".ogg"
        if header.startswith(b"fLaC"):
            return ".flac"
        if header.startswith(b"ID3"):
            return ".mp3"
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return ".m4a"
        if len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 == 0xF0:
            return ".aac"
        raise ValueError("unsupported_legacy_voice_format")

    @staticmethod
    def adopt_legacy(
        db,
        *,
        voice_id: str,
        owner_ref: str,
        default_voice_id: str,
        legacy_root: Path,
        private_root: Path,
    ):
        if voice_id == default_voice_id:
            raise ValueError("default_voice_cannot_be_adopted")
        owner = VoiceRepository.lock_owner(db, owner_ref, datetime.now(UTC))
        if owner.state == "purged":
            db.rollback()
            raise ValueError("owner_has_been_purged")
        voice = VoiceRepository.get_legacy_or_adopted_voice_for_update(
            db, voice_id, owner_ref,
        )
        if voice is None:
            db.rollback()
            return None
        if voice.owner_ref not in (None, owner_ref):
            db.rollback()
            raise ValueError("voice_owned_by_another_account")

        private_root = private_root.resolve()
        private_root.mkdir(parents=True, exist_ok=True)
        current_path = Path(str(voice.audio_path)).resolve()
        source_value = voice.legacy_source_path
        copied_destination: Path | None = None
        if not current_path.is_relative_to(private_root):
            source = VoiceService._path_in_root(str(voice.audio_path), legacy_root)
            if not source.is_file():
                db.rollback()
                raise ValueError("legacy_voice_file_not_found")
            # Legacy deployments sometimes stored WebM without an extension or
            # with a misleading one. Never trust the filename for migration.
            suffix = VoiceService._sniff_legacy_audio_suffix(source)
            destination = private_root / (
                f"{uuid.uuid5(uuid.NAMESPACE_URL, f'memorypal-legacy:{voice_id}')}{suffix}"
            )
            if not destination.exists():
                temporary = destination.with_suffix(destination.suffix + f".{uuid.uuid4()}.part")
                try:
                    shutil.copy2(source, temporary)
                    os.replace(temporary, destination)
                    copied_destination = destination
                finally:
                    temporary.unlink(missing_ok=True)
            source_value = str(source)
            voice.audio_path = str(destination)

        voice.owner_ref = owner_ref
        voice.registration_state = "active"
        voice.registration_token_hash = None
        voice.expires_at = None
        voice.legacy_source_path = source_value
        try:
            db.commit()
            db.refresh(voice)
        except Exception:
            db.rollback()
            if copied_destination is not None:
                copied_destination.unlink(missing_ok=True)
            raise

        if voice.legacy_source_path:
            try:
                source = VoiceService._path_in_root(
                    str(voice.legacy_source_path), legacy_root,
                )
                source.unlink(missing_ok=True)
                voice.legacy_source_path = None
                db.commit()
                db.refresh(voice)
            except OSError:
                db.rollback()
        return voice

    @staticmethod
    def _private_path(audio_path: str, private_root: Path) -> Path:
        try:
            return VoiceService._path_in_root(audio_path, private_root)
        except ValueError as exc:
            raise ValueError("voice_audio_path_outside_private_root") from exc

    @staticmethod
    def delete_owned(
        db,
        *,
        voice_id: str,
        owner_ref: str,
        registration_token: str,
        private_root: Path,
    ) -> bool:
        VoiceRepository.lock_owner(db, owner_ref, datetime.now(UTC))
        voice = VoiceRepository.get_owned_registration(
            db,
            voice_id,
            owner_ref,
            VoiceService.token_hash(registration_token),
        )
        if voice is None:
            return False
        path = VoiceService._private_path(str(voice.audio_path), private_root)
        VoiceRepository.delete(db, voice)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # The DB record is authoritative.  The unreferenced-file reaper
            # retries filesystem cleanup without leaving a usable profile.
            pass
        return True

    @staticmethod
    def cleanup_expired(db, private_root: Path, *, limit: int = 100) -> int:
        removed = 0
        for voice in VoiceRepository.list_expired_pending(db, datetime.now(UTC), limit):
            try:
                path = VoiceService._private_path(str(voice.audio_path), private_root)
                VoiceRepository.delete(db, voice)
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                removed += 1
            except (OSError, ValueError):
                db.rollback()
        return removed

    @staticmethod
    def cleanup_unreferenced_files(
        db,
        private_root: Path,
        *,
        older_than_seconds: int,
    ) -> int:
        root = private_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        referenced = {
            str(Path(path).resolve())
            for path in VoiceRepository.list_private_audio_paths(db)
        }
        cutoff = datetime.now(UTC).timestamp() - max(60, older_than_seconds)
        removed = 0
        for path in root.iterdir():
            try:
                uuid.UUID(path.stem)
                managed = path.suffix.casefold() in VoiceService._MANAGED_AUDIO_SUFFIXES
            except ValueError:
                managed = False
            if (
                not managed
                or not path.is_file()
                or str(path.resolve()) in referenced
            ):
                continue
            try:
                if path.stat().st_mtime <= cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
        return removed
