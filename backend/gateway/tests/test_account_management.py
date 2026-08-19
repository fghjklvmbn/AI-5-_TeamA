from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.security import decode_access_token


def _settings(tmp_path, *, admin_emails: tuple[str, ...] = ()):
    return replace(
        load_settings(),
        database_path=tmp_path / "accounts.db",
        database_url="",
        root_path="",
        admin_emails=admin_emails,
        archive_service_token="account-test-archive-service-token-" + "a" * 48,
    )


def _register(client: TestClient, email: str, password: str = "password123") -> dict:
    response = client.post("/v1/auth/register", json={
        "email": email,
        "password": password,
        "display_name": "기존 닉네임",
    })
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, email: str, password: str) -> dict:
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def test_profile_update_is_normalized_and_visible_as_safe_admin_action(tmp_path):
    settings = _settings(tmp_path, admin_emails=("operator@example.com",))
    app = create_app(settings)
    with TestClient(app) as client:
        auth = _register(client, "operator@example.com")
        tracking_secret = "nicknameShouldNeverBecomeATraceId"
        response = client.patch(
            "/v1/auth/profile",
            json={"display_name": "  새로운   닉네임  "},
            headers={
                **_headers(auth),
                "X-Request-ID": tracking_secret,
                "X-Correlation-ID": tracking_secret,
            },
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "새로운 닉네임"
        assert response.headers["X-Request-ID"] != tracking_secret
        assert response.headers["X-Correlation-ID"] != tracking_secret
        assert client.get("/v1/auth/me", headers=_headers(auth)).json()[
            "display_name"
        ] == "새로운 닉네임"
        assert client.patch(
            "/v1/auth/profile",
            json={"display_name": "   "},
            headers=_headers(auth),
        ).status_code == 422
        for unsafe_name in ("두 줄\n닉네임", "관리자\u202e사용자"):
            rejected = client.patch(
                "/v1/auth/profile",
                json={"display_name": unsafe_name},
                headers=_headers(auth),
            )
            assert rejected.status_code == 422
            assert client.get("/v1/auth/me", headers=_headers(auth)).json()[
                "display_name"
            ] == "새로운 닉네임"

        event = app.state.db.fetch_one(
            "SELECT * FROM user_transaction_events "
            "WHERE event_type = 'account_profile_update' AND status = 'succeeded'"
        )
        operation = app.state.db.fetch_one(
            "SELECT * FROM operation_states "
            "WHERE operation_type = 'account_profile_update' AND status = 'succeeded'"
        )
        assert event["user_id"] == auth["user"]["id"]
        assert operation["user_id"] == auth["user"]["id"]
        assert tracking_secret not in event["request_id"]
        assert "새로운 닉네임" not in event["metadata_json"]

        transactions = client.get(
            "/v1/admin/transactions", headers=_headers(auth),
        )
        operations = client.get("/v1/admin/operations", headers=_headers(auth))
        assert transactions.status_code == operations.status_code == 200
        assert any(
            item["event_type"] == "account_profile_update"
            for item in transactions.json()["items"]
        )
        assert any(
            item["operation_type"] == "account_profile_update"
            for item in operations.json()["items"]
        )
        assert "새로운 닉네임" not in transactions.text


def test_password_change_reauthenticates_and_invalidates_every_existing_jwt(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        first = _register(client, "password@example.com")
        second = _login(client, "password@example.com", "password123")

        wrong = client.post(
            "/v1/auth/password",
            json={"current_password": "not-the-password", "new_password": "new-password123"},
            headers=_headers(first),
        )
        assert wrong.status_code == 400
        same = client.post(
            "/v1/auth/password",
            json={"current_password": "password123", "new_password": "password123"},
            headers=_headers(first),
        )
        assert same.status_code == 422
        assert client.get("/v1/auth/me", headers=_headers(second)).status_code == 200

        changed = client.post(
            "/v1/auth/password",
            json={"current_password": "password123", "new_password": "new-password123"},
            headers=_headers(first),
        )
        assert changed.status_code == 204
        assert changed.content == b""
        assert client.get("/v1/auth/me", headers=_headers(first)).status_code == 401
        assert client.get("/v1/auth/me", headers=_headers(second)).status_code == 401
        assert client.post("/v1/auth/login", json={
            "email": "password@example.com", "password": "password123",
        }).status_code == 401
        replacement = _login(client, "password@example.com", "new-password123")
        assert client.get("/v1/auth/me", headers=_headers(replacement)).status_code == 200
        assert app.state.db.get_user_by_id(first["user"]["id"])["auth_version"] == 2

        first_claims = decode_access_token(first["access_token"], settings.jwt_secret)
        assert app.state.db.is_token_revoked(first_claims.jti)
        success_event = app.state.db.fetch_one(
            "SELECT * FROM user_transaction_events "
            "WHERE event_type = 'account_password_change' AND status = 'succeeded'"
        )
        outbox = app.state.db.fetch_one(
            "SELECT * FROM event_outbox WHERE event_id = ?", (success_event["event_id"],),
        )
        for secret in ("password123", "new-password123", "not-the-password"):
            assert secret not in success_event["metadata_json"]
            assert secret not in outbox["payload_json"]


def test_password_validation_never_echoes_or_persists_the_submitted_secret(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        auth = _register(client, "validation@example.com")
        unique_secret = "S" * 129
        response = client.post(
            "/v1/auth/password",
            json={"current_password": unique_secret, "new_password": "new-password123"},
            headers={
                **_headers(auth),
                "X-Request-ID": unique_secret[:128],
                "X-Correlation-ID": unique_secret[:128],
            },
        )
        assert response.status_code == 422
        assert unique_secret not in response.text
        event = app.state.db.fetch_one(
            "SELECT * FROM user_transaction_events "
            "WHERE event_type = 'account_password_change' ORDER BY occurred_at DESC LIMIT 1"
        )
        outbox = app.state.db.fetch_one(
            "SELECT * FROM event_outbox WHERE event_id = ?", (event["event_id"],),
        )
        assert unique_secret not in event["metadata_json"]
        assert unique_secret[:128] not in event["request_id"]
        assert unique_secret not in outbox["payload_json"]


def test_account_deletion_requires_confirmation_and_removes_gateway_user_graph(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)

    async def purge_owner_voices(*_args, **_kwargs):
        return None

    app.state.pipeline.purge_owner_voices = purge_owner_voices
    with TestClient(app) as client:
        auth = _register(client, "delete@example.com")
        user_id = auth["user"]["id"]
        token_claims = decode_access_token(auth["access_token"], settings.jwt_secret)
        session = app.state.db.create_session(user_id, "삭제될 세션")
        app.state.db.upsert_rag_embedding(
            user_id=user_id,
            namespace="account-test",
            source_id="source-1",
            content="삭제되어야 하는 사용자 문서",
            vector=[0.1, 0.2, 0.3],
            embedding_model="test",
        )
        operation = app.state.db.begin_operation(
            "old_user_operation",
            "old-user-request",
            "old-user-correlation",
            user_id=user_id,
        )
        app.state.db.transition_operation(operation["id"], "succeeded", user_id=user_id)

        invalid_confirmation = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": "password123", "confirmation": "delete"},
            headers=_headers(auth),
        )
        assert invalid_confirmation.status_code == 422
        wrong_password = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": "wrong-password", "confirmation": "DELETE"},
            headers=_headers(auth),
        )
        assert wrong_password.status_code == 400
        assert app.state.db.get_user_by_id(user_id) is not None

        deleted = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": "password123", "confirmation": "DELETE"},
            headers=_headers(auth),
        )
        assert deleted.status_code == 204
        assert deleted.content == b""
        assert app.state.db.get_user_by_id(user_id) is None
        assert app.state.db.get_session(user_id, session["id"]) is None
        assert app.state.db.fetch_one(
            "SELECT id FROM rag_embeddings WHERE user_id = ?", (user_id,),
        ) is None
        assert app.state.db.fetch_one(
            "SELECT id FROM operation_states WHERE user_id = ?", (user_id,),
        ) is None
        assert app.state.db.fetch_one(
            "SELECT event_id FROM user_transaction_events WHERE user_id = ?", (user_id,),
        ) is None
        assert app.state.db.is_token_revoked(token_claims.jti)
        assert client.get("/v1/auth/me", headers=_headers(auth)).status_code == 401
        assert client.post("/v1/auth/login", json={
            "email": "delete@example.com", "password": "password123",
        }).status_code == 401

        deletion_event = app.state.db.fetch_one(
            "SELECT * FROM user_transaction_events "
            "WHERE event_type = 'account_deletion' AND status = 'succeeded'"
        )
        deletion_operation = app.state.db.fetch_one(
            "SELECT * FROM operation_states "
            "WHERE operation_type = 'account_deletion' AND status = 'succeeded'"
        )
        assert deletion_event["user_id"] is None
        assert deletion_operation["user_id"] is None
        deletion_outbox = app.state.db.fetch_one(
            "SELECT * FROM event_outbox WHERE event_id = ?",
            (deletion_event["event_id"],),
        )
        assert user_id not in deletion_outbox["payload_json"]
        assert "password123" not in deletion_outbox["payload_json"]


def test_admin_accounts_cannot_use_regular_account_deletion(tmp_path):
    app = create_app(_settings(tmp_path, admin_emails=("allowlisted@example.com",)))
    with TestClient(app) as client:
        allowlisted = _register(client, "allowlisted@example.com")
        denied = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": "password123", "confirmation": "DELETE"},
            headers=_headers(allowlisted),
        )
        assert denied.status_code == 403
        assert app.state.db.get_user_by_id(allowlisted["user"]["id"]) is not None

        database_admin = _register(client, "database-admin@example.com")
        app.state.db.execute(
            "UPDATE users SET is_admin = 1 WHERE id = ?",
            (database_admin["user"]["id"],),
        )
        denied = client.request(
            "DELETE",
            "/v1/auth/account",
            json={"current_password": "password123", "confirmation": "DELETE"},
            headers=_headers(database_admin),
        )
        assert denied.status_code == 403
        assert app.state.db.get_user_by_id(database_admin["user"]["id"]) is not None
