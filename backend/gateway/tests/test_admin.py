from __future__ import annotations

import sqlite3
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.database import Database


def _settings(tmp_path, *, admin_emails: tuple[str, ...] = ()):
    return replace(
        load_settings(),
        database_path=tmp_path / "admin.db",
        database_url="",
        root_path="",
        admin_emails=admin_emails,
    )


def _register(client: TestClient, email: str) -> dict:
    response = client.post("/v1/auth/register", json={
        "email": email,
        "password": "password123",
        "display_name": "관리자 테스트",
    })
    assert response.status_code == 201
    return response.json()


def _headers(result: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {result['access_token']}"}


def test_admin_is_fail_closed_and_audited_without_polluting_product_events(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        registered = _register(client, "ordinary@example.com")
        before = len(app.state.db.list_transaction_events())
        response = client.get("/v1/admin/me", headers=_headers(registered))
        assert response.status_code == 403
        assert len(app.state.db.list_transaction_events()) == before

        audit = app.state.db.fetch_one(
            "SELECT * FROM admin_audit_events ORDER BY occurred_at DESC LIMIT 1"
        )
        assert audit["http_path"] == "/v1/admin/me"
        assert audit["http_status"] == 403
        assert audit["admin_ref"]


def test_anonymous_admin_4xx_does_not_grow_audit_table(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        before = app.state.db.fetch_one(
            "SELECT COUNT(*) AS count FROM admin_audit_events"
        )["count"]
        for _ in range(3):
            response = client.get("/v1/admin/me")
            assert response.status_code == 401
            assert response.headers["X-Request-ID"]
            assert response.headers["X-Correlation-ID"]
        after = app.state.db.fetch_one(
            "SELECT COUNT(*) AS count FROM admin_audit_events"
        )["count"]

    assert after == before


def test_allowlisted_admin_receives_only_privacy_safe_operational_data(tmp_path):
    app = create_app(_settings(tmp_path, admin_emails=("admin@example.com",)))
    with TestClient(app) as client:
        registered = _register(client, "ADMIN@example.com")
        headers = _headers(registered)
        assert client.get("/v1/auth/me", headers=headers).status_code == 200

        me = client.get("/v1/admin/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["role"] == "admin"
        assert me.json()["authorization_source"] == "allowlist"
        assert me.json()["user_id"] != registered["user"]["id"]

        services = client.get("/v1/admin/services", headers=headers)
        assert services.status_code == 200
        assert {item["service"] for item in services.json()["services"]} == {
            "stt", "llm", "tts", "gateway", "archive",
        }

        app.state.db.record_transaction_event(
            user_id=registered["user"]["id"],
            operation_id=None,
            request_id="nullable-latency-request",
            correlation_id="nullable-latency-correlation",
            event_type="nullable_latency_test",
            status="succeeded",
            http_method="GET",
            http_path="/nullable-latency",
            http_status=200,
            latency_ms=None,
        )

        overview = client.get("/v1/admin/overview", headers=headers)
        assert overview.status_code == 200
        overview_payload = overview.json()
        assert overview_payload["transaction_count"] >= 3
        assert len(overview_payload["trend"]) == 12
        assert sum(
            point["transaction_count"] for point in overview_payload["trend"]
        ) == overview_payload["transaction_count"]
        assert sum(
            row["transaction_count"] for row in overview_payload["routes"]
        ) == overview_payload["transaction_count"]
        nullable_route = next(
            row for row in overview_payload["routes"]
            if row["http_path"] == "/nullable-latency"
        )
        assert nullable_route["average_latency_ms"] == 0
        assert nullable_route["maximum_latency_ms"] == 0

        transactions = client.get("/v1/admin/transactions?limit=1", headers=headers)
        assert transactions.status_code == 200
        payload = transactions.json()
        assert len(payload["items"]) == 1
        serialized = transactions.text.casefold()
        for sensitive in ("admin@example.com", "관리자 테스트", "password123", "metadata_json"):
            assert sensitive.casefold() not in serialized
        item = payload["items"][0]
        assert item["user_id"] != registered["user"]["id"]

        if payload["next_cursor"]:
            second = client.get(
                "/v1/admin/transactions",
                params={"limit": 1, "cursor": payload["next_cursor"]},
                headers=headers,
            )
            assert second.status_code == 200
            assert second.json()["items"][0]["event_id"] != item["event_id"]

        users = client.get("/v1/admin/users", headers=headers)
        assert users.status_code == 200
        assert users.json()["items"][0]["user_id"] == me.json()["user_id"]
        assert "email" not in users.text.casefold()
        assert "display_name" not in users.text
        filtered_users = client.get(
            "/v1/admin/users", params={"status": "active"}, headers=headers,
        )
        assert filtered_users.status_code == 200
        assert filtered_users.json()["items"]

        operations = client.get("/v1/admin/operations", headers=headers)
        assert operations.status_code == 200
        operation = operations.json()["items"][0]
        transitions = client.get(
            f"/v1/admin/operations/{operation['id']}/transitions", headers=headers,
        )
        assert transitions.status_code == 200
        assert transitions.json()["items"]
        assert "reason" not in transitions.text


def test_database_admin_and_correlation_timeline(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        registered = _register(client, "database-admin@example.com")
        app.state.db.execute(
            "UPDATE users SET is_admin = 1 WHERE id = ?",
            (registered["user"]["id"],),
        )
        headers = {
            **_headers(registered),
            "X-Correlation-ID": "admin-correlation-0001",
        }
        assert client.get("/v1/auth/me", headers=headers).status_code == 200
        me = client.get("/v1/admin/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["authorization_source"] == "database"

        correlation = client.get(
            "/v1/admin/correlations/admin-correlation-0001", headers=headers,
        )
        assert correlation.status_code == 200
        assert correlation.json()["transactions"]
        assert "metadata_json" not in correlation.text


def test_admin_query_window_is_limited_to_31_days(tmp_path):
    app = create_app(_settings(tmp_path, admin_emails=("admin@example.com",)))
    with TestClient(app) as client:
        registered = _register(client, "admin@example.com")
        now = datetime.now(UTC)
        response = client.get(
            "/v1/admin/overview",
            params={
                "from": (now - timedelta(days=32)).isoformat(),
                "to": now.isoformat(),
            },
            headers=_headers(registered),
        )
        assert response.status_code == 422


def test_admin_overview_does_not_truncate_route_groups(tmp_path):
    app = create_app(_settings(tmp_path, admin_emails=("admin@example.com",)))
    with TestClient(app) as client:
        registered = _register(client, "admin@example.com")
        occurred_at = datetime.now(UTC).isoformat()
        with app.state.db.transaction() as db:
            for index in range(250):
                event_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO user_transaction_events ("
                    "event_id, user_id, operation_id, request_id, correlation_id, "
                    "event_type, status, http_method, http_path, http_status, "
                    "latency_ms, metadata_json, occurred_at"
                    ") VALUES (?, ?, NULL, ?, ?, 'route_group_test', 'succeeded', "
                    "'GET', ?, 200, ?, '{}', ?)",
                    (
                        event_id,
                        registered["user"]["id"],
                        f"route-request-{index:04d}",
                        f"route-correlation-{index:04d}",
                        f"/route-group/{index:04d}",
                        index,
                        occurred_at,
                    ),
                )

        response = client.get("/v1/admin/overview", headers=_headers(registered))
        assert response.status_code == 200
        route_groups = [
            row for row in response.json()["routes"]
            if row["event_type"] == "route_group_test"
        ]
        assert len(route_groups) == 250
        assert sum(row["transaction_count"] for row in route_groups) == 250


def test_existing_sqlite_users_receive_admin_columns_and_opaque_reference(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
            "display_name TEXT NOT NULL, password_hash TEXT NOT NULL, "
            "password_salt TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO users VALUES ('legacy-id', 'legacy@example.com', 'Legacy', "
            "'hash', 'salt', '2026-01-01T00:00:00+00:00')"
        )
    gateway_db = Database(path)
    gateway_db.initialize()
    row = gateway_db.get_user_by_id("legacy-id")
    assert row["is_admin"] == 0
    assert row["auth_version"] == 1
    assert row["admin_ref"]
    assert row["admin_ref"] != row["id"]
