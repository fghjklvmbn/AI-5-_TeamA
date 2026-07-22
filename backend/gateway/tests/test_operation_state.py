from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from memorypal_api.app import create_app
from memorypal_api.config import load_settings
from memorypal_api.database import Database


def test_operation_state_enforces_version_progress_and_terminal_status(tmp_path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    operation = db.begin_operation(
        "portrait", "request-0001", "correlation-0001", status="queued",
    )
    running = db.transition_operation(
        operation["id"], "running", progress_percent=30, expected_version=1,
    )
    retrying = db.transition_operation(
        operation["id"], "retrying", progress_percent=20, expected_version=2,
    )
    assert retrying["progress_percent"] == 30
    resumed = db.transition_operation(
        operation["id"], "running", progress_percent=40, expected_version=3,
    )
    complete = db.transition_operation(
        operation["id"], "succeeded", expected_version=4,
    )
    assert running["status"] == "running"
    assert resumed["progress_percent"] == 40
    assert complete["progress_percent"] == 100
    assert complete["version"] == 5
    with pytest.raises(ValueError, match="invalid operation transition"):
        db.transition_operation(operation["id"], "running")


def test_operation_state_rejects_stale_version(tmp_path):
    db = Database(tmp_path / "version.db")
    db.initialize()
    operation = db.begin_operation(
        "chat", "request-0002", "correlation-0002", status="running",
    )
    with pytest.raises(RuntimeError, match="version conflict"):
        db.transition_operation(
            operation["id"], "succeeded", expected_version=99,
        )


def test_http_middleware_records_sanitized_user_transaction(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "http-state.db", database_url="", root_path="",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        registered = client.post("/v1/auth/register", json={
            "email": "state@example.com",
            "password": "password123",
            "display_name": "상태 테스트",
        }).json()
        token = registered["access_token"]
        response = client.get(
            "/v1/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Correlation-ID": "correlation-http-0001",
            },
        )
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == "correlation-http-0001"
        assert response.headers["X-Request-ID"]

        events = app.state.db.list_transaction_events(
            correlation_id="correlation-http-0001",
        )
        assert len(events) == 1
        event = events[0]
        assert event["user_id"] == registered["user"]["id"]
        assert event["http_path"] == "/v1/auth/me"
        assert event["http_status"] == 200
        assert "Authorization" not in event["metadata_json"]
        assert "password123" not in event["metadata_json"]
        outbox = app.state.db.fetch_one(
            "SELECT * FROM event_outbox WHERE event_id = ?", (event["event_id"],),
        )
        assert outbox["status"] == "published"
        assert outbox["published_at"]


def test_transaction_outbox_is_retryable_and_idempotently_completed(tmp_path):
    db = Database(tmp_path / "outbox.db")
    db.initialize()
    event_id = db.record_transaction_event(
        user_id=None,
        operation_id=None,
        request_id="request-outbox-0001",
        correlation_id="correlation-outbox-0001",
        event_type="http_request_completed",
        status="failed",
        http_method="POST",
        http_path="/v1/chat/messages",
        http_status=503,
        latency_ms=250,
        metadata={"service": "gateway"},
    )

    claimed = db.claim_outbox_events("relay-test-0001")
    assert [row["event_id"] for row in claimed] == [event_id]
    assert db.claim_outbox_events("relay-test-0002") == []
    summary = db.summarize_transaction_events()
    assert summary[0]["transaction_count"] == 1
    assert summary[0]["http_path"] == "/v1/chat/messages"
    assert summary[0]["average_latency_ms"] == 250.0
    db.execute(
        "UPDATE event_outbox SET locked_until = '2000-01-01T00:00:00+00:00' "
        "WHERE event_id = ?",
        (event_id,),
    )
    reclaimed = db.claim_outbox_events("relay-test-0002")
    assert [row["event_id"] for row in reclaimed] == [event_id]
    assert not db.mark_outbox_published(event_id, "relay-test-0001")
    assert db.mark_outbox_published(event_id, "relay-test-0002")
    assert not db.mark_outbox_published(event_id, "relay-test-0002")
    assert db.claim_outbox_events("relay-test-0003") == []


def test_reused_client_request_id_does_not_merge_http_operations(tmp_path):
    settings = replace(
        load_settings(), database_path=tmp_path / "request-ids.db", database_url="", root_path="",
    )
    app = create_app(settings)
    shared_headers = {
        "X-Request-ID": "client-request-shared-0001",
        "X-Correlation-ID": "correlation-shared-0001",
    }
    with TestClient(app) as client:
        first = client.post("/v1/auth/register", headers=shared_headers, json={
            "email": "request-one@example.com",
            "password": "password123",
            "display_name": "첫 사용자",
        })
        second = client.post("/v1/auth/register", headers=shared_headers, json={
            "email": "request-two@example.com",
            "password": "password123",
            "display_name": "둘 사용자",
        })
        assert first.status_code == second.status_code == 201

        operations = app.state.db.list_operations(
            correlation_id="correlation-shared-0001",
        )
        events = app.state.db.list_transaction_events(
            correlation_id="correlation-shared-0001",
        )
        assert len(operations) == 2
        assert len({row["id"] for row in operations}) == 2
        assert len(events) == 2
        assert {row["user_id"] for row in events} == {
            first.json()["user"]["id"], second.json()["user"]["id"],
        }
