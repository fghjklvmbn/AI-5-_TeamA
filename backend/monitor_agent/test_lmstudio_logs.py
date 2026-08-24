from pathlib import Path

from lmstudio_logs import LMStudioLogCollector, LogEventStore, classify_event, sanitize_payload


def test_sanitize_payload_removes_model_io_and_credentials():
    sanitized = sanitize_payload({
        "type": "llm.prediction.output",
        "output": "private answer",
        "messages": [{"content": "private prompt"}],
        "authorization": "Bearer secret",
        "stats": {"tokens_per_second": 23.4},
    })

    assert sanitized == {
        "type": "llm.prediction.output",
        "stats": {"tokens_per_second": 23.4},
    }


def test_event_store_redacts_content_and_supports_incremental_cursor(tmp_path: Path):
    store = LogEventStore(tmp_path / "events.jsonl", maximum=100)
    first = store.append(
        "model",
        '{"type":"llm.prediction.output","modelIdentifier":"qwen3.5-4b",'
        '"output":"private answer","stats":{"tokens_per_second":18.5}}',
    )
    second = store.append(
        "runtime",
        'ERROR Failed to load qwen3.5-4b Authorization: Bearer top-secret',
    )

    assert first is not None and second is not None
    assert first["message"] == "llm.prediction.output"
    assert first["stats"] == {"tokens_per_second": 18.5}
    assert first["event_type"] == "inference_completed"
    assert second["event_type"] == "model_load_failed"
    assert "top-secret" not in second["message"]
    assert store.read(after_cursor=first["cursor"])["items"] == [second]
    assert "private answer" not in (tmp_path / "events.jsonl").read_text(encoding="utf-8")


def test_event_store_filters_by_source_level_and_model(tmp_path: Path):
    store = LogEventStore(tmp_path / "events.jsonl")
    store.append("server", '{"level":"info","message":"ready"}')
    expected = store.append(
        "runtime",
        '{"level":"error","message":"engine aborted","model":"qwen3.5-4b"}',
    )

    result = store.read(source="runtime", level="error", model_key="QWEN3.5")
    assert result["items"] == [expected]


def test_event_store_flattens_real_lms_nested_runtime_shape(tmp_path: Path):
    store = LogEventStore(tmp_path / "events.jsonl")
    result = store.append(
        "runtime",
        '{"timestamp":1787534286756,"data":{"type":"runtime.log","level":"debug",'
        '"message":"llama_server: model loaded","modelIdentifier":"liquidai_lfm2.5-2.6b"}}',
    )

    assert result is not None
    assert result["model_key"] == "liquidai_lfm2.5-2.6b"
    assert result["message"] == "llama_server: model loaded"
    assert result["event_type"] == "model_loaded"
    assert "T" in result["occurred_at"]


def test_event_classifier_covers_load_and_inference_states():
    assert classify_event("runtime", "Engine startup aborted", {}) == "model_load_failed"
    assert classify_event("server", "Model loaded successfully", {}) == "model_loaded"
    assert classify_event("model", "prediction output complete", {}) == "inference_completed"


def test_collector_builds_privacy_safe_source_commands(tmp_path: Path):
    collector = LMStudioLogCollector(
        "lms.exe", LogEventStore(tmp_path / "events.jsonl"), ("server", "runtime", "model"),
    )

    assert collector._command("server") == [
        "lms.exe", "log", "stream", "--source", "server", "--json",
    ]
    assert collector._command("model")[-3:] == ["--filter", "output", "--stats"]
