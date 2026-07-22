from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.database import (
    AccountAccessFenceError,
    AccountStateTransitionError,
    Database,
)
from memorypal_api.postgres_database import split_postgres_statements


PASSWORD = "password123"


def _settings(tmp_path, *, admin_emails: tuple[str, ...] = ("admin@example.com",)):
    return replace(
        load_settings(),
        database_path=tmp_path / "admin-account-control.db",
        database_url="",
        root_path="",
        admin_emails=admin_emails,
    )


def _register(client: TestClient, email: str, display_name: str = "테스트 사용자") -> dict:
    response = client.post(
        "/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": display_name},
    )
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, email: str):
    return client.post(
        "/v1/auth/login", json={"email": email, "password": PASSWORD},
    )


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _row(app, email: str):
    row = app.state.db.get_user_by_email(email)
    assert row is not None
    return row


def _domain_events(app, target_ref: str):
    return app.state.db.fetch_all(
        "SELECT * FROM admin_account_events WHERE target_admin_ref = ? "
        "ORDER BY occurred_at ASC",
        (target_ref,),
    )


def test_account_state_lifecycle_is_idempotent_terminal_and_invalidates_tokens(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com", "운영자")
        target = _register(client, "target@example.com")
        admin_headers = _headers(admin)
        target_headers = _headers(target)
        target_ref = str(_row(app, "target@example.com")["admin_ref"])

        suspended = client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1}, headers=admin_headers,
        )
        assert suspended.status_code == 200
        assert suspended.json()["account_status"] == "suspended"
        assert suspended.json()["status_version"] == 2
        assert suspended.json()["suspended_at"]
        assert client.get("/v1/auth/me", headers=target_headers).status_code == 403
        assert _login(client, "target@example.com").status_code == 403
        after_suspend = _row(app, "target@example.com")
        assert after_suspend["auth_version"] == 2

        repeated = client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1}, headers=admin_headers,
        )
        assert repeated.status_code == 200
        assert repeated.json()["status_version"] == 2
        assert _row(app, "target@example.com")["auth_version"] == 2
        assert len(_domain_events(app, target_ref)) == 1

        restored = client.post(
            f"/v1/admin/users/{target_ref}/unsuspend",
            json={"expected_version": 2}, headers=admin_headers,
        )
        assert restored.status_code == 200
        assert restored.json()["account_status"] == "active"
        assert restored.json()["status_version"] == 3
        assert restored.json()["suspended_at"] is None
        # Suspension is reversible, but authority rotation keeps every old JWT invalid.
        assert client.get("/v1/auth/me", headers=target_headers).status_code == 401
        fresh = _login(client, "target@example.com")
        assert fresh.status_code == 200
        fresh_headers = _headers(fresh.json())

        repeated_restore = client.post(
            f"/v1/admin/users/{target_ref}/unsuspend",
            json={"expected_version": 2}, headers=admin_headers,
        )
        assert repeated_restore.status_code == 200
        assert repeated_restore.json()["status_version"] == 3
        assert len(_domain_events(app, target_ref)) == 2

        stale_transition = client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1}, headers=admin_headers,
        )
        assert stale_transition.status_code == 409
        assert _row(app, "target@example.com")["account_status"] == "active"
        assert _row(app, "target@example.com")["status_version"] == 3
        assert len(_domain_events(app, target_ref)) == 2

        deactivated = client.request(
            "DELETE",
            f"/v1/admin/users/{target_ref}",
            json={"confirmation": "DEACTIVATE", "expected_version": 3},
            headers=admin_headers,
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["account_status"] == "deactivated"
        assert deactivated.json()["status_version"] == 4
        assert deactivated.json()["deactivated_at"]
        assert client.get("/v1/auth/me", headers=fresh_headers).status_code == 403
        assert _login(client, "target@example.com").status_code == 403

        repeated_deactivate = client.request(
            "DELETE",
            f"/v1/admin/users/{target_ref}",
            json={"confirmation": "DEACTIVATE", "expected_version": 3},
            headers=admin_headers,
        )
        assert repeated_deactivate.status_code == 200
        assert repeated_deactivate.json()["status_version"] == 4
        assert _row(app, "target@example.com")["auth_version"] == 4
        assert len(_domain_events(app, target_ref)) == 3
        assert client.post(
            f"/v1/admin/users/{target_ref}/unsuspend",
            json={"expected_version": 4}, headers=admin_headers,
        ).status_code == 409
        assert client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 4}, headers=admin_headers,
        ).status_code == 409


def test_protected_admins_and_self_cannot_be_targeted(tmp_path):
    settings = _settings(
        tmp_path, admin_emails=("admin@example.com", "allowlisted@example.com"),
    )
    app = create_app(settings)
    with TestClient(app) as client:
        actor = _register(client, "admin@example.com")
        _register(client, "allowlisted@example.com")
        database_admin = _register(client, "database-admin@example.com")
        _register(client, "ordinary@example.com")
        app.state.db.execute(
            "UPDATE users SET is_admin = 1 WHERE id = ?",
            (database_admin["user"]["id"],),
        )
        headers = _headers(actor)
        for email in (
            "admin@example.com", "allowlisted@example.com", "database-admin@example.com",
        ):
            ref = str(_row(app, email)["admin_ref"])
            response = client.post(
                f"/v1/admin/users/{ref}/suspend",
                json={"expected_version": 1}, headers=headers,
            )
            assert response.status_code == 403
            assert _row(app, email)["account_status"] == "active"

        ordinary_ref = str(_row(app, "ordinary@example.com")["admin_ref"])
        assert client.post(
            f"/v1/admin/users/{ordinary_ref}/suspend",
            json={"expected_version": 1}, headers=headers,
        ).status_code == 200


def test_user_listing_filters_account_status_and_keeps_no_activity_users_private(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com")
        _register(client, "quiet@example.com", "민감한 이름")
        headers = _headers(admin)
        quiet_ref = str(_row(app, "quiet@example.com")["admin_ref"])

        active = client.get(
            "/v1/admin/users", params={"status": "active"}, headers=headers,
        )
        assert active.status_code == 200
        quiet = next(item for item in active.json()["items"] if item["user_id"] == quiet_ref)
        assert quiet["account_status"] == "active"
        assert quiet["protected"] is False
        assert quiet["session_count"] == quiet["message_count"] == quiet["memory_count"] == 0
        assert "quiet@example.com" not in active.text
        assert "민감한 이름" not in active.text

        assert client.post(
            f"/v1/admin/users/{quiet_ref}/suspend",
            json={"expected_version": 1}, headers=headers,
        ).status_code == 200
        suspended = client.get(
            "/v1/admin/users", params={"status": "suspended"}, headers=headers,
        )
        assert suspended.status_code == 200
        assert [item["user_id"] for item in suspended.json()["items"]] == [quiet_ref]
        assert all(
            item["user_id"] != quiet_ref
            for item in client.get(
                "/v1/admin/users", params={"status": "active"}, headers=headers,
            ).json()["items"]
        )
        assert client.get(
            "/v1/admin/users", params={"status": "succeeded"}, headers=headers,
        ).status_code == 422


def test_user_pagination_only_emits_cursor_when_a_lookahead_row_exists(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com")
        for index in range(49):
            app.state.db.create_user(
                f"quiet-{index}@example.com", f"Quiet {index}", "hash", "salt",
            )
        headers = _headers(admin)
        exact_page = client.get(
            "/v1/admin/users", params={"status": "active", "limit": 50}, headers=headers,
        )
        assert exact_page.status_code == 200
        assert len(exact_page.json()["items"]) == 50
        assert exact_page.json()["next_cursor"] is None

        app.state.db.create_user("lookahead@example.com", "Lookahead", "hash", "salt")
        first_page = client.get(
            "/v1/admin/users", params={"status": "active", "limit": 50}, headers=headers,
        )
        assert first_page.status_code == 200
        assert len(first_page.json()["items"]) == 50
        assert first_page.json()["next_cursor"]
        final_page = client.get(
            "/v1/admin/users",
            params={
                "status": "active",
                "limit": 50,
                "cursor": first_page.json()["next_cursor"],
            },
            headers=headers,
        )
        assert final_page.status_code == 200
        assert len(final_page.json()["items"]) == 1
        assert final_page.json()["next_cursor"] is None


def test_mutation_ids_are_server_generated_and_free_form_reason_is_rejected(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com")
        _register(client, "target@example.com")
        target_ref = str(_row(app, "target@example.com")["admin_ref"])
        client_trace = "client-controlled-trace-0001"
        headers = {
            **_headers(admin),
            "X-Request-ID": client_trace,
            "X-Correlation-ID": client_trace,
        }

        rejected = client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={
                "expected_version": 1,
                "reason": "email=target@example.com secret free text",
            },
            headers=headers,
        )
        assert rejected.status_code == 422
        assert _row(app, "target@example.com")["account_status"] == "active"
        assert client.post(
            f"/v1/admin/users/{target_ref}/suspend", json={}, headers=headers,
        ).status_code == 422

        response = client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1}, headers=headers,
        )
        assert response.status_code == 200
        request_id = response.headers["X-Request-ID"]
        correlation_id = response.headers["X-Correlation-ID"]
        assert request_id != client_trace
        assert correlation_id != client_trace
        uuid.UUID(request_id)
        uuid.UUID(correlation_id)

        event = _domain_events(app, target_ref)[0]
        assert event["request_id"] == request_id
        assert event["correlation_id"] == correlation_id
        assert event["action"] == "admin_user_suspend"
        assert event["before_status"] == "active"
        assert event["after_status"] == "suspended"
        assert set(dict(event)) == {
            "id", "actor_admin_ref", "target_admin_ref", "action", "before_status",
            "after_status", "status_version", "request_id", "correlation_id", "occurred_at",
        }
        audit = app.state.db.fetch_one(
            "SELECT * FROM admin_audit_events WHERE request_id = ?", (request_id,),
        )
        assert audit["action"] == "admin_user_suspend"
        assert audit["target_admin_ref"] == target_ref
        assert audit["before_status"] == "active"
        assert audit["after_status"] == "suspended"
        assert "reason" not in {
            row[1] for row in app.state.db.fetch_all("PRAGMA table_info(admin_account_events)")
        }


def test_stale_authority_fences_roll_back_writes_and_cancel_portrait(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com")
        _register(client, "target@example.com")
        row = _row(app, "target@example.com")
        user_id = str(row["id"])
        target_ref = str(row["admin_ref"])
        expected = int(row["auth_version"])
        session = app.state.db.create_session(user_id)
        existing_conversation = app.state.db.save_conversation(
            user_id, session["id"], "보존할 질문", "보존할 답변",
            expected_auth_version=expected,
        )
        attachment = app.state.db.create_attachment(
            user_id, session["id"], "before.txt", "text/plain", 6, "before",
            expected_auth_version=expected,
        )
        existing_memory = app.state.db.upsert_memory(
            user_id, session["id"], "fact", "preserved memory", "preserved memory",
            "preserved memory", 0.8, 0.8, expected_auth_version=expected,
        )
        portrait, _ = app.state.db.begin_portrait_generation(
            user_id, "default", expected_auth_version=expected,
        )

        assert client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1}, headers=_headers(admin),
        ).status_code == 200
        with pytest.raises(AccountAccessFenceError):
            app.state.db.save_conversation(
                user_id, session["id"], "저장되면 안 됨", "차단",
                expected_auth_version=expected,
            )
        with pytest.raises(AccountAccessFenceError):
            app.state.db.upsert_session_working_memory(
                user_id, session["id"], "stale", 1,
                expected_auth_version=expected,
            )
        with pytest.raises(AccountAccessFenceError):
            app.state.db.upsert_memory(
                user_id, session["id"], "fact", "stale memory", "stale memory",
                "stale memory", 0.8, 0.8, expected_auth_version=expected,
            )
        with pytest.raises(AccountAccessFenceError):
            app.state.db.add_user_voice(
                user_id, "stale-voice", expected_auth_version=expected,
            )
        with pytest.raises(AccountAccessFenceError):
            app.state.db.create_session(
                user_id, "정지 후 생성 금지", expected_auth_version=expected,
            )
        with pytest.raises(AccountAccessFenceError):
            app.state.db.delete_session(
                user_id, session["id"], expected_auth_version=expected,
            )
        with pytest.raises(AccountAccessFenceError):
            app.state.db.delete_attachment(
                user_id, attachment["id"], expected_auth_version=expected,
            )
        with pytest.raises(AccountAccessFenceError):
            app.state.db.delete_memory(
                user_id, existing_memory["id"], expected_auth_version=expected,
            )

        assert [row["id"] for row in app.state.db.list_sessions(user_id)] == [session["id"]]
        assert [row["id"] for row in app.state.db.get_history(user_id, session["id"])] == [
            existing_conversation["id"]
        ]
        assert app.state.db.get_session_working_memory(user_id, session["id"]) == ""
        assert [row["id"] for row in app.state.db.list_attachments(user_id, session["id"])] == [
            attachment["id"]
        ]
        assert [row["id"] for row in app.state.db.list_memories(user_id)] == [
            existing_memory["id"]
        ]
        assert app.state.db.list_user_voice_ids(user_id) == set()
        stopped = app.state.db.get_portrait(user_id)
        assert stopped["generation_id"] == portrait["generation_id"]
        assert stopped["status"] == "failed"
        assert stopped["error"] == "account_inactive"
        assert not app.state.db.claim_portrait_generation(
            user_id, portrait["generation_id"], "late-worker",
        )


def test_legacy_migration_backfills_account_state(tmp_path):
    path = tmp_path / "legacy-state.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
            "display_name TEXT NOT NULL, password_hash TEXT NOT NULL, "
            "password_salt TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO users VALUES ('legacy', 'legacy@example.com', 'Legacy', "
            "'hash', 'salt', '2026-01-01T00:00:00+00:00')"
        )
    database = Database(path)
    database.initialize()
    row = database.get_user_by_id("legacy")
    assert row["account_status"] == "active"
    assert row["status_version"] == 1
    assert row["status_changed_at"] == row["created_at"]
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO users (id, email, display_name, password_hash, password_salt, "
            "created_at, auth_version, account_status, status_version, status_changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, 'active', 1, ?)",
            (
                "missing-ref", "missing-ref@example.com", "Missing", "hash", "salt",
                "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
            ),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("UPDATE users SET admin_ref = NULL WHERE id = ?", ("legacy",))
    with pytest.raises(sqlite3.IntegrityError):
        database.execute("UPDATE users SET admin_ref = '   ' WHERE id = ?", ("legacy",))
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "UPDATE users SET status_changed_at = NULL WHERE id = ?", ("legacy",),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "UPDATE users SET status_changed_at = '' WHERE id = ?", ("legacy",),
        )


def test_postgres_migration_adds_account_state_constraints_once():
    schema = (
        Path(__file__).resolve().parents[1] / "migrations" / "postgres_schema.sql"
    ).read_text(encoding="utf-8")
    for name, expression in (
        ("ck_users_auth_version", "auth_version >= 1"),
        (
            "ck_users_account_status",
            "account_status IN ('active','suspended','deactivated')",
        ),
        ("ck_users_status_version", "status_version >= 1"),
    ):
        auto_name = f"users_{name.removeprefix('ck_users_')}_check"
        assert f"conname IN ('{auto_name}', '{name}')" in schema
        assert f"ADD CONSTRAINT {name}" in schema
        assert expression in schema
        assert f"VALIDATE CONSTRAINT {name}" in schema
        assert f"DROP CONSTRAINT IF EXISTS {name}" not in schema

    statements = split_postgres_statements(schema)
    constraint_block = next(
        statement for statement in statements
        if statement.startswith("DO $$") and "ck_users_account_status" in statement
    )
    assert constraint_block.endswith("END\n$$")
    assert constraint_block.count("VALIDATE CONSTRAINT") == 3
    assert "ADD CONSTRAINT ck_users_admin_ref_nonblank" in schema
    assert "CHECK (btrim(admin_ref) <> '') NOT VALID" in schema
    assert "VALIDATE CONSTRAINT ck_users_admin_ref_nonblank" in schema


def test_postgres_statement_splitter_preserves_quotes_comments_and_dollar_blocks():
    script = """
    SELECT 'semi;colon';
    -- ignored ; delimiter
    DO $migration$
    BEGIN
        PERFORM 'inside;block';
    END;
    $migration$;
    SELECT "quoted;identifier";
    """
    assert split_postgres_statements(script) == [
        "SELECT 'semi;colon'",
        "-- ignored ; delimiter\n    DO $migration$\n"
        "    BEGIN\n        PERFORM 'inside;block';\n    END;\n    $migration$",
        'SELECT "quoted;identifier"',
    ]


def test_postgres_write_fence_uses_a_row_share_lock(tmp_path):
    class PostgresDialectDatabase(Database):
        @property
        def backend_name(self) -> str:
            return "postgresql+pgvector"

    class Cursor:
        def fetchone(self):
            return {"allowed": 1}

    class Connection:
        def __init__(self):
            self.query = ""
            self.params = ()

        def execute(self, query, params):
            self.query = query
            self.params = params
            return Cursor()

    database = PostgresDialectDatabase(tmp_path / "unused.db")
    connection = Connection()
    database._require_account_fence(connection, "user-id", 7)
    assert connection.query.endswith(" FOR SHARE")
    assert connection.params == ("user-id", 7)


def test_postgres_self_delete_acquires_for_update_without_lock_upgrade(tmp_path):
    class Cursor:
        def __init__(self, row=None, rowcount=1):
            self.row = row
            self.rowcount = rowcount

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.queries: list[str] = []

        def execute(self, query, _params=()):
            self.queries.append(query)
            if query.startswith("SELECT 1 FROM users"):
                return Cursor({"allowed": 1})
            if query.startswith("SELECT admin_ref FROM users"):
                return Cursor({"admin_ref": None})
            return Cursor()

    class PostgresDeleteDatabase(Database):
        def __init__(self):
            super().__init__(tmp_path / "unused-delete.db")
            self.connection = Connection()

        @property
        def backend_name(self) -> str:
            return "postgresql+pgvector"

        @contextmanager
        def transaction(self):
            yield self.connection

    database = PostgresDeleteDatabase()
    assert database.delete_user_account(
        "user-id",
        expected_hash="hash",
        expected_salt="salt",
        expected_auth_version=3,
        token_jti="token-jti",
        token_expires_at=2_000_000_000,
    )
    assert database.connection.queries[0].endswith(" FOR UPDATE")
    assert "FOR SHARE" not in database.connection.queries[0]


def test_postgres_admin_transition_locks_actor_and_target_in_one_stable_query(tmp_path):
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Connection:
        def __init__(self):
            self.queries: list[str] = []

        def execute(self, query, _params=()):
            self.queries.append(query)
            return Cursor([
                {
                    "id": "actor-id",
                    "admin_ref": "actor-ref",
                    "account_status": "active",
                    "auth_version": 5,
                    "is_admin": False,
                    "email": "admin@example.com",
                },
                {
                    "id": "target-id",
                    "admin_ref": "target-ref",
                    "account_status": "active",
                    "auth_version": 1,
                    "status_version": 1,
                    "is_admin": True,
                    "email": "protected@example.com",
                },
            ])

    class PostgresTransitionDatabase(Database):
        def __init__(self):
            super().__init__(tmp_path / "unused-transition.db")
            self.connection = Connection()

        @property
        def backend_name(self) -> str:
            return "postgresql+pgvector"

        @contextmanager
        def transaction(self):
            yield self.connection

    database = PostgresTransitionDatabase()
    with pytest.raises(AccountStateTransitionError) as exc_info:
        database.transition_admin_account_status(
            actor_user_id="actor-id",
            actor_admin_ref="actor-ref",
            actor_expected_auth_version=5,
            target_admin_ref="target-ref",
            action="admin_user_suspend",
            expected_version=1,
            protected_admin_emails=("admin@example.com",),
            request_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
        )
    assert exc_info.value.code == "protected_admin"
    assert len(database.connection.queries) == 1
    lock_query = database.connection.queries[0]
    assert "WHERE id = ? OR admin_ref = ?" in lock_query
    assert "ORDER BY id FOR UPDATE" in lock_query


def test_admin_request_is_rejected_if_actor_auth_version_changes_after_dependency(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com")
        _register(client, "target@example.com")
        actor = _row(app, "admin@example.com")
        target_ref = str(_row(app, "target@example.com")["admin_ref"])
        original_transition = app.state.db.transition_admin_account_status
        captured: dict[str, int] = {}

        def rotate_actor_then_transition(**kwargs):
            captured["expected"] = int(kwargs["actor_expected_auth_version"])
            app.state.db.execute(
                "UPDATE users SET auth_version = auth_version + 1 WHERE id = ?",
                (actor["id"],),
            )
            return original_transition(**kwargs)

        app.state.db.transition_admin_account_status = rotate_actor_then_transition
        response = client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1},
            headers=_headers(admin),
        )
        assert response.status_code == 403
        assert captured["expected"] == 1
        target = _row(app, "target@example.com")
        assert target["account_status"] == "active"
        assert target["status_version"] == 1
        assert _domain_events(app, target_ref) == []


@pytest.mark.parametrize("action", ["suspend", "deactivate"])
def test_stale_self_delete_cannot_erase_admin_state_or_audit(tmp_path, action):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com")
        target = _register(client, f"{action}@example.com")
        row = _row(app, f"{action}@example.com")
        target_ref = str(row["admin_ref"])
        if action == "suspend":
            response = client.post(
                f"/v1/admin/users/{target_ref}/suspend",
                json={"expected_version": 1}, headers=_headers(admin),
            )
        else:
            response = client.request(
                "DELETE",
                f"/v1/admin/users/{target_ref}",
                json={"confirmation": "DEACTIVATE", "expected_version": 1},
                headers=_headers(admin),
            )
        assert response.status_code == 200

        with pytest.raises(AccountAccessFenceError):
            app.state.db.delete_user_account(
                target["user"]["id"],
                expected_hash=row["password_hash"],
                expected_salt=row["password_salt"],
                expected_auth_version=1,
                token_jti=f"stale-{action}",
                token_expires_at=2_000_000_000,
            )
        preserved = _row(app, f"{action}@example.com")
        expected_status = "suspended" if action == "suspend" else "deactivated"
        assert preserved["account_status"] == expected_status
        assert app.state.db.fetch_one(
            "SELECT 1 FROM admin_account_events WHERE target_admin_ref = ?",
            (target_ref,),
        ) is not None
        assert app.state.db.fetch_one(
            "SELECT 1 FROM admin_audit_events WHERE target_admin_ref = ? AND http_status = 200",
            (target_ref,),
        ) is not None


def test_attachment_extracted_after_suspension_is_not_persisted(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        _register(client, "admin@example.com")
        target = _register(client, "document-owner@example.com")
        target_headers = _headers(target)
        session_response = client.post(
            "/v1/sessions", json={"title": "문서"}, headers=target_headers,
        )
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]
        actor = _row(app, "admin@example.com")
        owner = _row(app, "document-owner@example.com")

        def extract_then_suspend(_filename: str, _content: bytes) -> str:
            app.state.db.transition_admin_account_status(
                actor_user_id=actor["id"],
                actor_admin_ref=actor["admin_ref"],
                actor_expected_auth_version=int(actor["auth_version"]),
                target_admin_ref=owner["admin_ref"],
                action="admin_user_suspend",
                expected_version=1,
                protected_admin_emails=app.state.settings.admin_emails,
                request_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
            )
            return "추출은 끝났지만 저장되면 안 되는 내용"

        app.state.document_engine.extract = extract_then_suspend
        response = client.post(
            f"/v1/sessions/{session_id}/attachments",
            files={"file": ("long.txt", b"long-running extraction", "text/plain")},
            headers=target_headers,
        )
        assert response.status_code == 403
        assert app.state.db.list_attachments(owner["id"], session_id) == []


def test_self_hard_delete_preserves_pseudonymous_admin_target_audit(tmp_path):
    app = create_app(replace(
        _settings(tmp_path),
        archive_service_token="audit-test-archive-service-token-" + "a" * 48,
    ))

    async def purge_owner_voices(*_args, **_kwargs):
        return None

    app.state.pipeline.purge_owner_voices = purge_owner_voices
    with TestClient(app) as client:
        admin = _register(client, "admin@example.com")
        _register(client, "audit-target@example.com")
        target_ref = str(_row(app, "audit-target@example.com")["admin_ref"])
        headers = _headers(admin)
        assert client.post(
            f"/v1/admin/users/{target_ref}/suspend",
            json={"expected_version": 1}, headers=headers,
        ).status_code == 200
        assert client.post(
            f"/v1/admin/users/{target_ref}/unsuspend",
            json={"expected_version": 2}, headers=headers,
        ).status_code == 200
        target_login = _login(client, "audit-target@example.com")
        assert target_login.status_code == 200
        domain_before = app.state.db.fetch_all(
            "SELECT * FROM admin_account_events WHERE target_admin_ref = ?",
            (target_ref,),
        )
        audit_before = app.state.db.fetch_all(
            "SELECT * FROM admin_audit_events WHERE target_admin_ref = ?",
            (target_ref,),
        )
        assert len(domain_before) == 2
        assert len(audit_before) == 2

        deleted = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": PASSWORD, "confirmation": "DELETE"},
            headers=_headers(target_login.json()),
        )
        assert deleted.status_code == 204
        assert app.state.db.get_user_by_admin_ref(target_ref) is None
        domain_after = app.state.db.fetch_all(
            "SELECT * FROM admin_account_events WHERE target_admin_ref = ?",
            (target_ref,),
        )
        audit_after = app.state.db.fetch_all(
            "SELECT * FROM admin_audit_events WHERE target_admin_ref = ?",
            (target_ref,),
        )
        assert [row["id"] for row in domain_after] == [row["id"] for row in domain_before]
        assert [row["id"] for row in audit_after] == [row["id"] for row in audit_before]
        assert "audit-target@example.com" not in str([dict(row) for row in domain_after])


def test_profile_write_is_fenced_when_admin_suspends_after_dependency(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        _register(client, "admin@example.com")
        target_auth = _register(client, "profile-race@example.com")
        actor = _row(app, "admin@example.com")
        target = _row(app, "profile-race@example.com")
        original_update = app.state.db.update_user_display_name
        captured: dict[str, int] = {}

        def suspend_then_update(user_id, display_name, *, expected_auth_version):
            captured["expected"] = expected_auth_version
            app.state.db.transition_admin_account_status(
                actor_user_id=actor["id"],
                actor_admin_ref=actor["admin_ref"],
                actor_expected_auth_version=int(actor["auth_version"]),
                target_admin_ref=target["admin_ref"],
                action="admin_user_suspend",
                expected_version=1,
                protected_admin_emails=app.state.settings.admin_emails,
                request_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
            )
            return original_update(
                user_id, display_name, expected_auth_version=expected_auth_version,
            )

        app.state.db.update_user_display_name = suspend_then_update
        response = client.patch(
            "/v1/auth/profile",
            json={"display_name": "변경되면 안 됨"},
            headers=_headers(target_auth),
        )
        assert response.status_code == 403
        assert captured["expected"] == 1
        current = _row(app, "profile-race@example.com")
        assert current["account_status"] == "suspended"
        assert current["display_name"] == "테스트 사용자"


def test_password_write_is_fenced_when_admin_deactivates_after_dependency(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        _register(client, "admin@example.com")
        target_auth = _register(client, "password-race@example.com")
        actor = _row(app, "admin@example.com")
        target = _row(app, "password-race@example.com")
        original_hash = str(target["password_hash"])
        original_salt = str(target["password_salt"])
        original_change = app.state.db.change_user_password
        captured: dict[str, int] = {}

        def deactivate_then_change(user_id, **kwargs):
            captured["expected"] = int(kwargs["expected_auth_version"])
            app.state.db.transition_admin_account_status(
                actor_user_id=actor["id"],
                actor_admin_ref=actor["admin_ref"],
                actor_expected_auth_version=int(actor["auth_version"]),
                target_admin_ref=target["admin_ref"],
                action="admin_user_deactivate",
                expected_version=1,
                protected_admin_emails=app.state.settings.admin_emails,
                request_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
            )
            return original_change(user_id, **kwargs)

        app.state.db.change_user_password = deactivate_then_change
        response = client.post(
            "/v1/auth/password",
            json={
                "current_password": PASSWORD,
                "new_password": "new-password-456",
            },
            headers=_headers(target_auth),
        )
        assert response.status_code == 403
        assert captured["expected"] == 1
        current = _row(app, "password-race@example.com")
        assert current["account_status"] == "deactivated"
        assert current["password_hash"] == original_hash
        assert current["password_salt"] == original_salt
