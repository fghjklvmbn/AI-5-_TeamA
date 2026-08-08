-- The Gateway tables are the single runtime source of truth. memorypal_ops is
-- a read-only namespace for the future administrator service, avoiding a
-- second operation-state table that could drift from the live state machine.
CREATE OR REPLACE VIEW memorypal_ops.operation_states AS
SELECT
    id,
    user_id,
    request_id,
    correlation_id,
    operation_type,
    resource_id,
    status,
    progress_percent,
    version,
    error_code,
    created_at,
    updated_at,
    started_at,
    completed_at
FROM memorypal_gateway.operation_states;

CREATE OR REPLACE VIEW memorypal_ops.operation_state_transitions AS
SELECT
    id,
    operation_id,
    from_status,
    to_status,
    version,
    progress_percent,
    reason,
    occurred_at
FROM memorypal_gateway.operation_state_transitions;

CREATE OR REPLACE VIEW memorypal_ops.user_transaction_events AS
SELECT
    event_id,
    user_id,
    operation_id,
    request_id,
    correlation_id,
    event_type,
    status,
    http_method,
    http_path,
    http_status,
    latency_ms,
    metadata_json,
    occurred_at
FROM memorypal_gateway.user_transaction_events;

CREATE OR REPLACE VIEW memorypal_ops.transaction_hourly_metrics AS
SELECT * FROM memorypal_gateway.admin_transaction_hourly_metrics;

CREATE OR REPLACE VIEW memorypal_ops.operation_status_metrics AS
SELECT * FROM memorypal_gateway.admin_operation_status_metrics;

COMMENT ON VIEW memorypal_ops.user_transaction_events IS
    'Metadata-only audit read model. Conversation, document, audio, and credential bodies are prohibited.';
COMMENT ON VIEW memorypal_ops.operation_states IS
    'Live operation snapshots. Grant SELECT only to the future least-privilege admin role.';
