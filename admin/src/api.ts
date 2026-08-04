import type {
  AdminUser,
  CorrelationDetail,
  ListResult,
  OperationState,
  Overview,
  TransactionEvent,
  UserMetric,
} from './types';

const explicitApiUrl = import.meta.env.VITE_API_URL as string | undefined;
const isLocal = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
export const API_URL = (explicitApiUrl || (isLocal
  ? 'http://127.0.0.1:8010/v1'
  : '/api_memoripal/project3/gateway/v1')).replace(/\/$/, '');

const TOKEN_KEY = 'memorypal.admin.session';

type TokenResponse = {
  access_token: string;
  expires_at: number;
  user: AdminUser;
};

type AdminMeResponse = {
  user_id: string;
  role: 'admin';
  authorization_source: 'allowlist' | 'database';
};

type RawOverview = {
  generated_at: string;
  total_user_count: number;
  active_user_count: number;
  transaction_count: number;
  succeeded_count: number;
  failed_count: number;
  average_latency_ms: number;
  maximum_latency_ms: number;
  operations: Record<string, number>;
  outbox: Record<string, number>;
  routes: Array<{
    event_type: string;
    status: string;
    http_path: string;
    transaction_count: number;
    user_count: number;
    average_latency_ms: number;
    maximum_latency_ms: number;
  }>;
};

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function readError(detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) return message;
  }
  return '요청을 처리하지 못했습니다.';
}

async function request<T>(path: string, init: RequestInit = {}, token?: string, signal?: AbortSignal): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, signal });
  if (!response.ok) {
    let message = response.status === 401 ? '관리자 세션이 만료되었습니다.' : '요청을 처리하지 못했습니다.';
    try {
      const payload = await response.json() as { detail?: unknown };
      message = readError(payload.detail);
    } catch {
      // Reverse proxies may return HTML. Do not expose the response body.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function query(params: Record<string, string | number | undefined>) {
  const result = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') result.set(key, String(value));
  });
  const value = result.toString();
  return value ? `?${value}` : '';
}

function normalizeList<T>(payload: ListResult<T> | T[]): ListResult<T> {
  if (Array.isArray(payload)) return { items: payload, total: payload.length };
  return {
    items: payload.items || [],
    total: Number(payload.total || payload.items?.length || 0),
    next_cursor: payload.next_cursor ?? null,
  };
}

function buildTrend(events: TransactionEvent[], from: string, to: string) {
  const start = new Date(from).getTime();
  const end = new Date(to).getTime();
  const bucketCount = 12;
  const width = Math.max(1, (end - start) / bucketCount);
  const points = Array.from({ length: bucketCount }, (_, index) => ({
    bucket: new Date(start + width * index).toISOString(),
    transaction_count: 0,
    succeeded_count: 0,
    failed_count: 0,
    average_latency_ms: 0,
    latency_total: 0,
    latency_count: 0,
  }));
  events.forEach((event) => {
    const at = new Date(event.occurred_at).getTime();
    const index = Math.min(bucketCount - 1, Math.max(0, Math.floor((at - start) / width)));
    const point = points[index];
    point.transaction_count += 1;
    if (event.status === 'succeeded') point.succeeded_count += 1;
    if (event.status === 'failed' || event.status === 'cancelled') point.failed_count += 1;
    if (event.latency_ms !== null) {
      point.latency_total += Number(event.latency_ms || 0);
      point.latency_count += 1;
    }
  });
  return points.map(({ latency_total, latency_count, ...point }) => ({
    ...point,
    average_latency_ms: latency_count ? latency_total / latency_count : 0,
  }));
}

function normalizeOverview(raw: RawOverview, events: TransactionEvent[], from: string, to: string): Overview {
  const statusCounts: Record<string, number> = {};
  const pathMap = new Map<string, { transaction_count: number; succeeded: number; latency: number }>();
  raw.routes.forEach((row) => {
    statusCounts[row.status] = (statusCounts[row.status] || 0) + Number(row.transaction_count || 0);
    const path = row.http_path || row.event_type || 'unknown';
    const current = pathMap.get(path) || { transaction_count: 0, succeeded: 0, latency: 0 };
    current.transaction_count += Number(row.transaction_count || 0);
    if (row.status === 'succeeded') current.succeeded += Number(row.transaction_count || 0);
    current.latency += Number(row.average_latency_ms || 0) * Number(row.transaction_count || 0);
    pathMap.set(path, current);
  });
  const completed = Number(raw.succeeded_count || 0) + Number(raw.failed_count || 0);
  return {
    transaction_count: Number(raw.transaction_count || 0),
    unique_users: Number(raw.active_user_count || 0),
    success_rate: completed ? Number(raw.succeeded_count || 0) / completed * 100 : 0,
    average_latency_ms: Number(raw.average_latency_ms || 0),
    failed_count: Number(raw.failed_count || 0),
    active_operations: ['queued', 'running', 'retrying'].reduce((sum, key) => sum + Number(raw.operations?.[key] || 0), 0),
    trend: buildTrend(events, from, to),
    status_counts: statusCounts,
    top_paths: [...pathMap.entries()].map(([http_path, metric]) => ({
      http_path,
      transaction_count: metric.transaction_count,
      success_rate: metric.transaction_count ? metric.succeeded / metric.transaction_count * 100 : 0,
      average_latency_ms: metric.transaction_count ? metric.latency / metric.transaction_count : 0,
    })).sort((a, b) => b.transaction_count - a.transaction_count),
    generated_at: raw.generated_at,
  };
}

export const sessionStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export const adminApi = {
  async login(email: string, password: string) {
    const auth = await request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    const admin = await request<AdminMeResponse>('/admin/me', {}, auth.access_token);
    return { ...auth, user: { ...auth.user, role: admin.role } };
  },
  async me(token: string, signal?: AbortSignal) {
    const [, user] = await Promise.all([
      request<AdminMeResponse>('/admin/me', {}, token, signal),
      request<AdminUser>('/auth/me', {}, token, signal),
    ]);
    return { ...user, role: 'admin' };
  },
  logout(token: string) {
    return request<void>('/auth/logout', { method: 'POST' }, token);
  },
  async overview(token: string, from: string, to: string, signal?: AbortSignal) {
    const [overview, eventPayload] = await Promise.all([
      request<RawOverview>(`/admin/overview${query({ from, to })}`, {}, token, signal),
      request<ListResult<TransactionEvent>>(`/admin/transactions${query({ from, to, limit: 200 })}`, {}, token, signal),
    ]);
    return normalizeOverview(overview, eventPayload.items || [], from, to);
  },
  async transactions(
    token: string,
    filters: { from: string; to: string; status?: string; search?: string; limit?: number },
    signal?: AbortSignal,
  ) {
    const { search, ...serverFilters } = filters;
    const payload = await request<ListResult<TransactionEvent> | TransactionEvent[]>(
      `/admin/transactions${query(serverFilters)}`, {}, token, signal,
    );
    const result = normalizeList(payload);
    if (!search) return result;
    const term = search.toLowerCase();
    const items = result.items.filter((item) => [item.user_id, item.correlation_id, item.event_type].some((value) => value?.toLowerCase().includes(term)));
    return { items, total: items.length };
  },
  async operations(
    token: string,
    filters: { from: string; to: string; status?: string; search?: string; limit?: number },
    signal?: AbortSignal,
  ) {
    const { search, ...serverFilters } = filters;
    const payload = await request<ListResult<OperationState> | OperationState[]>(
      `/admin/operations${query(serverFilters)}`, {}, token, signal,
    );
    const result = normalizeList(payload);
    if (!search) return result;
    const term = search.toLowerCase();
    const items = result.items.filter((item) => [item.user_id, item.correlation_id, item.operation_type].some((value) => value?.toLowerCase().includes(term)));
    return { items, total: items.length };
  },
  async users(
    token: string,
    from: string,
    to: string,
    status?: string,
    cursor?: string,
    signal?: AbortSignal,
  ) {
    const payload = await request<ListResult<UserMetric> | UserMetric[]>(
      `/admin/users${query({ from, to, status, cursor, limit: 50 })}`, {}, token, signal,
    );
    return normalizeList(payload);
  },
  suspendUser(token: string, userRef: string, expectedVersion: number) {
    return request<void>(
      `/admin/users/${encodeURIComponent(userRef)}/suspend`,
      { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }) },
      token,
    );
  },
  unsuspendUser(token: string, userRef: string, expectedVersion: number) {
    return request<void>(
      `/admin/users/${encodeURIComponent(userRef)}/unsuspend`,
      { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }) },
      token,
    );
  },
  deactivateUser(token: string, userRef: string, expectedVersion: number) {
    return request<void>(
      `/admin/users/${encodeURIComponent(userRef)}`,
      {
        method: 'DELETE',
        body: JSON.stringify({
          confirmation: 'DEACTIVATE',
          expected_version: expectedVersion,
        }),
      },
      token,
    );
  },
  correlation(token: string, correlationId: string, from: string, to: string, signal?: AbortSignal) {
    return request<CorrelationDetail>(
      `/admin/correlations/${encodeURIComponent(correlationId)}${query({ from, to })}`, {}, token, signal,
    );
  },
};
