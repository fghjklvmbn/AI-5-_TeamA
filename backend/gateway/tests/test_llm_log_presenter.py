from memorypal_api.services.llm_log_presenter import deduplicate_presented_logs, present_llm_log


def event(message: str, *, source: str = "runtime", event_type: str = "runtime_event"):
    return {
        "cursor": 1, "source": source, "level": "debug", "event_type": event_type,
        "model_key": None, "message": message, "stats": {},
        "occurred_at": "2026-08-24T00:00:00+00:00",
    }


def test_presents_nested_model_load_as_readable_event():
    result = present_llm_log(event(
        '{"timestamp":1787534286756,"data":{"type":"runtime.log","level":"debug",'
        '"message":"llama_server: model loaded","modelIdentifier":"liquidai_lfm2.5-2.6b"}}'
    ))
    assert result["event_type"] == "model_loaded"
    assert result["model_key"] == "liquidai_lfm2.5-2.6b"
    assert result["title"] == "모델 로드 완료"
    assert result["importance"] == "important"
    assert result["occurred_at"].endswith("+00:00")


def test_extracts_generation_performance_from_llama_timing():
    result = present_llm_log(event(
        '{"data":{"level":"debug","modelIdentifier":"qwen3.5-4b","message":"'
        'prompt eval time = 1853.02 ms / 670 tokens (2.77 ms per token, 361.57 tokens per second)\\n'
        'eval time = 10058.64 ms / 768 tokens (13.10 ms per token, 76.35 tokens per second)\\n'
        'total time = 11911.65 ms / 1438 tokens"}}'
    ))
    assert result["event_type"] == "inference_completed"
    assert result["title"] == "응답 생성 완료"
    assert result["stats"] == {
        "prompt_tokens": 670, "prompt_tokens_per_second": 361.57,
        "completion_tokens": 768, "tokens_per_second": 76.35,
        "duration_ms": 11911.65, "total_tokens": 1438,
    }


def test_marks_model_catalog_polling_as_routine():
    result = present_llm_log(event(
        '{"data":{"type":"server.log","content":"[INFO] Returning 6 models from v1 API","level":"info"}}',
        source="server", event_type="server_event",
    ))
    assert result["event_type"] == "model_catalog_returned"
    assert result["message"] == "사용 가능한 모델 6개를 반환했습니다."
    assert result["importance"] == "routine"


def test_normalizes_fallback_epoch_and_deduplicates_server_runtime_pair():
    base = {
        "event_type": "model_loaded", "level": "info", "message": "model loaded",
        "stats": {}, "occurred_at": "1787534444907",
    }
    server = present_llm_log({**base, "cursor": 1, "source": "server", "model_key": None})
    runtime = present_llm_log({**base, "cursor": 2, "source": "runtime", "model_key": "qwen3.5-4b"})
    result = deduplicate_presented_logs([server, runtime])

    assert len(result) == 1
    assert result[0]["model_key"] == "qwen3.5-4b"
    assert result[0]["occurred_at"].endswith("+00:00")
