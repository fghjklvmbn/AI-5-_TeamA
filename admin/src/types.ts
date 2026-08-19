export type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  role?: string;
};

export type TransactionStatus = 'succeeded' | 'failed' | 'cancelled' | 'running' | 'queued' | 'retrying';

export type TransactionEvent = {
  event_id: string;
  user_id: string | null;
  operation_id: string | null;
  request_id: string;
  correlation_id: string;
  event_type: string;
  status: TransactionStatus | string;
  http_method: string | null;
  http_path: string | null;
  http_status: number | null;
  latency_ms: number | null;
  occurred_at: string;
};

export type OperationState = {
  id: string;
  user_id: string | null;
  request_id: string;
  correlation_id: string;
  operation_type: string;
  resource_id: string | null;
  status: TransactionStatus | string;
  progress_percent: number;
  version: number;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type TrendPoint = {
  bucket: string;
  transaction_count: number;
  succeeded_count: number;
  failed_count: number;
  average_latency_ms: number;
};

export type PathMetric = {
  http_path: string;
  transaction_count: number;
  success_rate: number;
  average_latency_ms: number;
};

export type Overview = {
  transaction_count: number;
  unique_users: number;
  success_rate: number;
  average_latency_ms: number;
  failed_count: number;
  active_operations: number;
  trend: TrendPoint[];
  status_counts: Record<string, number>;
  top_paths: PathMetric[];
  generated_at?: string;
};

export type UserMetric = {
  user_id: string;
  account_status: 'active' | 'suspended' | 'deactivated';
  status_version: number;
  protected: boolean;
  status_changed_at: string | null;
  suspended_at: string | null;
  deactivated_at: string | null;
  created_at: string;
  session_count: number;
  message_count: number;
  memory_count: number;
  transaction_count: number;
  failed_count: number;
  last_seen_at: string | null;
};

export type CorrelationDetail = {
  correlation_id: string;
  transactions: TransactionEvent[];
  operations: OperationState[];
};

export type ListResult<T> = {
  items: T[];
  total: number;
  next_cursor?: string | null;
};

export type ServiceHealth = 'green' | 'yellow' | 'red';

export type HardwareMetric = {
  service: 'stt' | 'llm' | 'tts' | 'gateway' | 'archive';
  status: ServiceHealth;
  reason: string;
  sampled_at: string;
  service_online: boolean;
  process_count?: number;
  response_latency_ms: number | null;
  latency_baseline_ms: number | null;
  cpu: { process_percent: number };
  ram: {
    total_bytes: number;
    available_bytes: number;
    used_percent: number;
    process_rss_bytes: number;
    process_percent: number;
  };
  gpu: null | {
    names: string[];
    count: number;
    cuda_utilization_percent: number;
    memory_controller_utilization_percent: number;
    vram_total_bytes: number;
    vram_used_bytes: number;
    vram_free_bytes: number;
    vram_used_percent: number;
  };
};

export type HardwareMonitorResponse = {
  generated_at: string;
  interval_seconds: number;
  services: HardwareMetric[];
  history: HardwareMetric[];
};
