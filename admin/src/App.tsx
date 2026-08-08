import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Ban,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleGauge,
  Clock3,
  Eye,
  EyeOff,
  Fingerprint,
  Gauge,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  LogOut,
  Menu,
  Moon,
  Network,
  RefreshCcw,
  Search,
  ShieldCheck,
  Sun,
  Trash2,
  UserRoundCheck,
  Users,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { adminApi, ApiError, sessionStore } from './api';
import type {
  AdminUser,
  CorrelationDetail,
  ListResult,
  OperationState,
  Overview,
  TransactionEvent,
  UserMetric,
} from './types';

type Page = 'overview' | 'transactions' | 'operations' | 'users';
type RangeKey = '1h' | '24h' | '7d' | '30d';

const EMPTY_OVERVIEW: Overview = {
  transaction_count: 0,
  unique_users: 0,
  success_rate: 0,
  average_latency_ms: 0,
  failed_count: 0,
  active_operations: 0,
  trend: [],
  status_counts: {},
  top_paths: [],
};

const PAGE_META: Record<Page, { label: string; eyebrow: string; title: string; icon: LucideIcon }> = {
  overview: { label: '운영 개요', eyebrow: 'OPERATIONS OVERVIEW', title: 'MemoryPal의 흐름을 한눈에', icon: LayoutDashboard },
  transactions: { label: '트랜잭션', eyebrow: 'TRANSACTION EXPLORER', title: '사용자 요청 흐름', icon: Activity },
  operations: { label: '작업 상태', eyebrow: 'STATE MANAGEMENT', title: '진행 중인 작업과 상태 전이', icon: CircleGauge },
  users: { label: '사용자 분석', eyebrow: 'USER ACTIVITY', title: '사용자별 이용 지표', icon: Users },
};

const RANGE_LABELS: Record<RangeKey, string> = {
  '1h': '최근 1시간',
  '24h': '최근 24시간',
  '7d': '최근 7일',
  '30d': '최근 30일',
};

const STATUS_LABELS: Record<string, string> = {
  succeeded: '성공',
  failed: '실패',
  cancelled: '취소',
  queued: '대기',
  running: '처리 중',
  retrying: '재시도',
};

const ACCOUNT_STATUS_LABELS: Record<UserMetric['account_status'], string> = {
  active: '활성',
  suspended: '정지',
  deactivated: '비활성화',
};

type UserControlAction = 'suspend' | 'unsuspend' | 'deactivate';

function normalizeStatus(page: Page, status: string): string | undefined {
  if (!status) return undefined;
  const valid = page === 'users' ? ACCOUNT_STATUS_LABELS : STATUS_LABELS;
  return Object.prototype.hasOwnProperty.call(valid, status) ? status : undefined;
}

function periodFor(range: RangeKey, now: number) {
  const duration = { '1h': 3_600_000, '24h': 86_400_000, '7d': 604_800_000, '30d': 2_592_000_000 }[range];
  return { from: new Date(now - duration).toISOString(), to: new Date(now).toISOString() };
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('ko-KR', { notation: value >= 100_000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value || 0);
}

function formatPercent(value: number) {
  return `${Number(value || 0).toFixed(value < 10 && value > 0 ? 1 : 0)}%`;
}

function formatLatency(value: number | null | undefined) {
  const latency = Number(value || 0);
  if (latency >= 1000) return `${(latency / 1000).toFixed(2)}초`;
  return `${Math.round(latency)}ms`;
}

function formatDate(value: string | null | undefined, withDate = true) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ko-KR', {
    ...(withDate ? { month: '2-digit', day: '2-digit' } : {}),
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

function compactId(value: string | null | undefined, head = 8) {
  if (!value) return '익명';
  if (value.length <= head + 5) return value;
  return `${value.slice(0, head)}…${value.slice(-4)}`;
}

function statusTone(status: string) {
  if (status === 'succeeded') return 'success';
  if (status === 'failed' || status === 'cancelled') return 'danger';
  if (status === 'running') return 'info';
  if (status === 'retrying') return 'warning';
  return 'neutral';
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge ${statusTone(status)}`}><i />{STATUS_LABELS[status] || status}</span>;
}

function LoginView({ onLogin }: { onLogin: (token: string, user: AdminUser) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const result = await adminApi.login(email.trim(), password);
      sessionStore.set(result.access_token);
      onLogin(result.access_token, result.user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '로그인할 수 없습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <div className="login-ambient ambient-one" />
      <div className="login-ambient ambient-two" />
      <section className="login-story" aria-label="MemoryPal 관리자 콘솔 소개">
        <div className="brand-mark"><span>M</span></div>
        <p className="eyebrow">MEMORYPAL OPERATIONS</p>
        <h1>서비스의 모든 흐름을<br /><em>조용하고 선명하게.</em></h1>
        <p className="story-copy">요청부터 백그라운드 작업까지, 상태 변화와 성능을 한곳에서 확인하세요. 대화 본문과 인증 정보는 수집하거나 표시하지 않습니다.</p>
        <div className="trust-row">
          <span><ShieldCheck size={17} /> 민감 정보 비노출</span>
          <span><Network size={17} /> 상태 전이 추적</span>
        </div>
      </section>
      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <div className="mobile-brand"><div className="brand-mark small"><span>M</span></div><strong>MemoryPal</strong></div>
          <div className="login-title">
            <p className="eyebrow">ADMIN CONSOLE</p>
            <h2>관리자 로그인</h2>
            <p>승인된 관리자 계정으로 접속해 주세요.</p>
          </div>
          <label className="field-label" htmlFor="admin-email">이메일</label>
          <div className="input-wrap">
            <input id="admin-email" autoComplete="username" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@memorypal.ai" required />
          </div>
          <label className="field-label" htmlFor="admin-password">비밀번호</label>
          <div className="input-wrap password-wrap">
            <input id="admin-password" autoComplete="current-password" type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" required />
            <button type="button" className="icon-button inline" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}>
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {error && <div className="login-error" role="alert"><CircleAlert size={17} />{error}</div>}
          <button className="primary-button login-button" disabled={submitting}>
            {submitting ? <><LoaderCircle className="spin" size={18} />권한 확인 중</> : <>운영 콘솔 열기<ChevronRight size={18} /></>}
          </button>
          <p className="login-footnote"><Fingerprint size={15} /> 세션은 이 브라우저 탭을 닫으면 안전하게 종료됩니다.</p>
        </form>
      </section>
    </main>
  );
}

function Sidebar({ page, onPage, user, onLogout, open, onClose, health }: {
  page: Page;
  onPage: (page: Page) => void;
  user: AdminUser;
  onLogout: () => void;
  open: boolean;
  onClose: () => void;
  health: 'current' | 'syncing' | 'delayed';
}) {
  return (
    <>
      <button className={`sidebar-scrim ${open ? 'open' : ''}`} onClick={onClose} aria-label="메뉴 닫기" />
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand-mark small"><span>M</span></div>
          <div><strong>MemoryPal</strong><small>Operations</small></div>
          <button className="icon-button sidebar-close" onClick={onClose} aria-label="메뉴 닫기"><X size={20} /></button>
        </div>
        <nav className="nav-list" aria-label="관리자 메뉴">
          <p className="nav-caption">MONITOR</p>
          {(Object.keys(PAGE_META) as Page[]).map((key) => {
            const item = PAGE_META[key];
            const Icon = item.icon;
            return (
              <button key={key} className={page === key ? 'active' : ''} onClick={() => { onPage(key); onClose(); }}>
                <Icon size={19} /><span>{item.label}</span>{page === key && <i />}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-status">
          <div className={`live-dot ${health}`}><i /> {health === 'syncing' ? '메타데이터 동기화 중' : health === 'delayed' ? '연결 상태 확인 필요' : '운영 메타데이터 최신'}</div>
          <p>{health === 'delayed' ? '마지막 요청에 실패했습니다. 상단에서 다시 시도해 주세요.' : '본문 없이 30초 간격으로 상태를 갱신합니다.'}</p>
        </div>
        <div className="admin-profile">
          <div className="avatar">{(user.display_name || user.email || 'A').slice(0, 1).toUpperCase()}</div>
          <div><strong>{user.display_name || '관리자'}</strong><span>{user.email}</span></div>
          <button className="icon-button" onClick={onLogout} aria-label="로그아웃"><LogOut size={17} /></button>
        </div>
      </aside>
    </>
  );
}

function KpiCard({ label, value, detail, icon: Icon, tone, change }: {
  label: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  tone: string;
  change?: number;
}) {
  return (
    <article className={`kpi-card ${tone}`}>
      <div className="kpi-top"><span>{label}</span><div className="kpi-icon"><Icon size={19} /></div></div>
      <strong>{value}</strong>
      <div className="kpi-detail">
        {change !== undefined && <span className={change >= 0 ? 'positive' : 'negative'}>{change >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{Math.abs(change)}%</span>}
        <small>{detail}</small>
      </div>
    </article>
  );
}

function EmptyState({ title = '표시할 데이터가 없습니다', description = '선택한 기간이나 필터를 변경해 보세요.' }: { title?: string; description?: string }) {
  return <div className="empty-state"><div><BarChart3 size={24} /></div><strong>{title}</strong><p>{description}</p></div>;
}

function LoadingRows() {
  return <div className="loading-rows" aria-label="데이터 불러오는 중">{[1, 2, 3, 4, 5].map((value) => <span key={value} />)}</div>;
}

function TrendChart({ overview }: { overview: Overview }) {
  const points = overview.trend || [];
  const hasTransactions = points.some((point) => Number(point.transaction_count || 0) > 0);
  const max = Math.max(1, ...points.map((point) => Number(point.transaction_count || 0)));
  return (
    <article className="panel trend-panel">
      <header className="panel-heading">
        <div><p className="section-kicker">TRAFFIC</p><h3>트랜잭션 흐름</h3></div>
        <div className="legend"><span className="purple">전체 요청</span><span className="red">실패</span></div>
      </header>
      {hasTransactions ? (
        <div className="bar-chart" role="img" aria-label="기간별 전체 요청과 실패 요청 막대 차트">
          <div className="chart-grid"><i /><i /><i /><i /></div>
          {points.slice(-16).map((point, index) => {
            const total = Number(point.transaction_count || 0);
            const failed = Math.min(total, Number(point.failed_count || 0));
            const totalHeight = total > 0 ? Math.max(3, total / max * 100) : 0;
            // The failure bar is nested inside the total bar, so its height is
            // relative to that bucket rather than to the chart-wide maximum.
            const failedHeight = total > 0 ? failed / total * 100 : 0;
            return (
              <div className="bar-column" key={`${point.bucket}-${index}`} title={`${formatDate(point.bucket)} · ${point.transaction_count}건`}>
                <div className="bars"><span style={{ height: `${totalHeight}%` }}><i style={{ height: `${failedHeight}%` }} /></span></div>
                <small>{formatDate(point.bucket, false).slice(0, 5)}</small>
              </div>
            );
          })}
        </div>
      ) : <EmptyState />}
    </article>
  );
}

function StatusBreakdown({ overview }: { overview: Overview }) {
  const counts = overview.status_counts || {};
  const total = Math.max(1, Object.values(counts).reduce((sum, count) => sum + Number(count || 0), 0));
  const succeeded = Number(counts.succeeded || 0);
  const failed = Number(counts.failed || 0) + Number(counts.cancelled || 0);
  const successDegrees = succeeded / total * 360;
  const failedDegrees = failed / total * 360;
  return (
    <article className="panel status-panel">
      <header className="panel-heading"><div><p className="section-kicker">HEALTH</p><h3>상태 분포</h3></div></header>
      <div className="donut-layout">
        <div className="donut" style={{ background: `conic-gradient(var(--success) 0 ${successDegrees}deg, var(--danger) ${successDegrees}deg ${successDegrees + failedDegrees}deg, var(--violet) ${successDegrees + failedDegrees}deg 360deg)` }}>
          <div><strong>{formatPercent(overview.success_rate)}</strong><span>성공률</span></div>
        </div>
        <div className="status-legend">
          {['succeeded', 'failed', 'running', 'queued', 'retrying'].map((status) => (
            <div key={status}><span><i className={statusTone(status)} />{STATUS_LABELS[status]}</span><strong>{formatNumber(Number(counts[status] || 0))}</strong></div>
          ))}
        </div>
      </div>
    </article>
  );
}

function TopPaths({ overview }: { overview: Overview }) {
  return (
    <article className="panel paths-panel">
      <header className="panel-heading"><div><p className="section-kicker">ENDPOINTS</p><h3>많이 사용된 경로</h3></div></header>
      {(overview.top_paths || []).length ? <div className="mini-table">
        <div className="mini-row header"><span>경로</span><span>요청</span><span>성공률</span><span>평균 지연</span></div>
        {overview.top_paths.slice(0, 6).map((item) => <div className="mini-row" key={item.http_path}>
          <code>{item.http_path || '—'}</code><strong>{formatNumber(item.transaction_count)}</strong><span>{formatPercent(item.success_rate)}</span><span>{formatLatency(item.average_latency_ms)}</span>
        </div>)}
      </div> : <EmptyState />}
    </article>
  );
}

function OverviewPage({ overview }: { overview: Overview }) {
  return (
    <>
      <section className="kpi-grid">
        <KpiCard label="전체 트랜잭션" value={formatNumber(overview.transaction_count)} detail="선택 기간 누적" icon={Zap} tone="violet" />
        <KpiCard label="활성 사용자" value={formatNumber(overview.unique_users)} detail="고유 사용자 기준" icon={Users} tone="blue" />
        <KpiCard label="요청 성공률" value={formatPercent(overview.success_rate)} detail="완료된 요청 기준" icon={CheckCircle2} tone="green" />
        <KpiCard label="평균 응답시간" value={formatLatency(overview.average_latency_ms)} detail="Gateway 처리 시간" icon={Gauge} tone="amber" />
        <KpiCard label="실패 요청" value={formatNumber(overview.failed_count)} detail="실패·취소 포함" icon={CircleAlert} tone="red" />
        <KpiCard label="활성 작업" value={formatNumber(overview.active_operations)} detail="대기·처리·재시도" icon={RefreshCcw} tone="cyan" />
      </section>
      <section className="overview-grid"><TrendChart overview={overview} /><StatusBreakdown overview={overview} /></section>
      <TopPaths overview={overview} />
    </>
  );
}

function TransactionsPage({ result, loading, onCorrelation }: { result: ListResult<TransactionEvent>; loading: boolean; onCorrelation: (id: string) => void }) {
  return (
    <article className="panel data-panel">
      <header className="panel-heading table-heading"><div><p className="section-kicker">AUDIT STREAM</p><h3>트랜잭션 이벤트</h3><p>본문 없이 요청 경로와 성능 메타데이터만 표시합니다.</p></div><span className="record-count">{formatNumber(result.total)}건</span></header>
      {loading ? <LoadingRows /> : result.items.length ? (
        <div className="table-scroll"><table>
          <thead><tr><th>시간</th><th>상태</th><th>요청</th><th>HTTP</th><th>지연시간</th><th>사용자</th><th>Correlation</th></tr></thead>
          <tbody>{result.items.map((event) => <tr key={event.event_id}>
            <td className="nowrap"><span className="muted-cell">{formatDate(event.occurred_at)}</span></td>
            <td><StatusBadge status={event.status} /></td>
            <td><div className="request-cell"><span className={`method ${(event.http_method || '').toLowerCase()}`}>{event.http_method || 'EVENT'}</span><code>{event.http_path || event.event_type}</code></div></td>
            <td><span className={Number(event.http_status || 0) >= 400 ? 'http-error' : ''}>{event.http_status ?? '—'}</span></td>
            <td><strong>{formatLatency(event.latency_ms)}</strong></td>
            <td><code className="muted-code">{compactId(event.user_id)}</code></td>
            <td><button className="link-button" onClick={() => onCorrelation(event.correlation_id)}>{compactId(event.correlation_id, 10)}<ChevronRight size={14} /></button></td>
          </tr>)}</tbody>
        </table></div>
      ) : <EmptyState title="조건에 맞는 트랜잭션이 없습니다" />}
    </article>
  );
}

function OperationsPage({ result, loading, onCorrelation }: { result: ListResult<OperationState>; loading: boolean; onCorrelation: (id: string) => void }) {
  return (
    <article className="panel data-panel">
      <header className="panel-heading table-heading"><div><p className="section-kicker">OPERATION STATES</p><h3>작업 상태</h3><p>작업 단위의 현재 상태와 단조 증가하는 진행률입니다.</p></div><span className="record-count">{formatNumber(result.total)}건</span></header>
      {loading ? <LoadingRows /> : result.items.length ? (
        <div className="table-scroll"><table className="operation-table">
          <thead><tr><th>최근 변경</th><th>작업</th><th>상태</th><th>진행률</th><th>사용자</th><th>오류 코드</th><th>Correlation</th></tr></thead>
          <tbody>{result.items.map((operation) => <tr key={operation.id}>
            <td className="nowrap"><span className="muted-cell">{formatDate(operation.updated_at)}</span></td>
            <td><div className="operation-name"><strong>{operation.operation_type}</strong><code>{compactId(operation.id, 7)}</code></div></td>
            <td><StatusBadge status={operation.status} /></td>
            <td><div className="progress-cell"><div><i style={{ width: `${Math.min(100, Math.max(0, operation.progress_percent || 0))}%` }} /></div><strong>{operation.progress_percent || 0}%</strong></div></td>
            <td><code className="muted-code">{compactId(operation.user_id)}</code></td>
            <td><span className={operation.error_code ? 'error-code' : 'muted-cell'}>{operation.error_code || '—'}</span></td>
            <td><button className="link-button" onClick={() => onCorrelation(operation.correlation_id)}>{compactId(operation.correlation_id, 10)}<ChevronRight size={14} /></button></td>
          </tr>)}</tbody>
        </table></div>
      ) : <EmptyState title="조건에 맞는 작업이 없습니다" />}
    </article>
  );
}

function AccountStatusBadge({ status }: { status: UserMetric['account_status'] }) {
  const tone = status === 'active' ? 'success' : status === 'suspended' ? 'warning' : 'danger';
  return <span className={`account-status ${tone}`}><i />{ACCOUNT_STATUS_LABELS[status]}</span>;
}

function UserControlDialog({ token, target, action, onClose, onSuccess, onUnauthorized, onConflict }: {
  token: string;
  target: UserMetric;
  action: UserControlAction;
  onClose: () => void;
  onSuccess: (message: string) => void;
  onUnauthorized: () => void;
  onConflict: () => void;
}) {
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const destructive = action === 'deactivate';
  const dialogRef = useRef<HTMLElement>(null);
  const primaryActionRef = useRef<HTMLButtonElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const focusTarget = destructive ? confirmationRef.current : primaryActionRef.current;
    const frame = window.requestAnimationFrame(() => focusTarget?.focus());
    const handleKeyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) {
        event.preventDefault();
        dialogRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialogRef.current.contains(active))) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && (active === last || !dialogRef.current.contains(active))) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener('keydown', handleKeyboard);
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyboard);
    };
  }, [busy, destructive, onClose]);

  const copy = action === 'suspend'
    ? { eyebrow: 'SUSPEND ACCOUNT', title: '계정을 정지할까요?', description: '사용자의 로그인과 서비스 이용을 중지합니다. 정지 해제로 다시 이용할 수 있습니다.', button: '계정 정지', success: '계정이 정지되었습니다.' }
    : action === 'unsuspend'
      ? { eyebrow: 'RESTORE ACCESS', title: '정지를 해제할까요?', description: '사용자가 즉시 다시 로그인하고 MemoryPal을 이용할 수 있습니다.', button: '정지 해제', success: '계정 정지가 해제되었습니다.' }
      : { eyebrow: 'DEACTIVATE ACCOUNT', title: '계정을 삭제(비활성화)할까요?', description: '정지와 달리 되돌릴 수 없는 상태입니다. 로그인과 서비스 이용은 영구 차단되며 데이터는 운영 보존·삭제 정책에 따라 처리됩니다.', button: '계정 삭제(비활성화)', success: '계정이 비활성화되었습니다.' };

  async function submit() {
    if (busy) return;
    if (destructive && confirmation !== 'DEACTIVATE') {
      setError('확인란에 DEACTIVATE를 정확히 입력해 주세요.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      if (action === 'suspend') {
        await adminApi.suspendUser(token, target.user_id, target.status_version);
      } else if (action === 'unsuspend') {
        await adminApi.unsuspendUser(token, target.user_id, target.status_version);
      } else {
        await adminApi.deactivateUser(token, target.user_id, target.status_version);
      }
      onSuccess(copy.success);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        onUnauthorized();
        return;
      }
      if (cause instanceof ApiError && cause.status === 409) {
        onConflict();
        return;
      }
      setError(cause instanceof Error ? cause.message : '계정 상태를 변경하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="user-dialog-layer" role="dialog" aria-modal="true" aria-labelledby="user-control-title">
      <button className="user-dialog-scrim" disabled={busy} onClick={onClose} aria-label="계정 제어 창 닫기" />
      <section className={`user-dialog ${destructive ? 'destructive' : ''}`} ref={dialogRef} tabIndex={-1}>
        <header>
          <div className={`dialog-icon ${destructive ? 'danger' : action === 'unsuspend' ? 'success' : 'warning'}`}>
            {destructive ? <Trash2 size={20} /> : action === 'unsuspend' ? <UserRoundCheck size={20} /> : <Ban size={20} />}
          </div>
          <button className="icon-button" disabled={busy} onClick={onClose} aria-label="계정 제어 창 닫기"><X size={19} /></button>
        </header>
        <p className="section-kicker">{copy.eyebrow}</p>
        <h2 id="user-control-title">{copy.title}</h2>
        <p className="dialog-description">{copy.description}</p>
        <div className="dialog-user">
          <div className="avatar tiny">U</div>
          <div><strong>사용자 {compactId(target.user_id, 6)}</strong><code>{target.user_id}</code></div>
          <AccountStatusBadge status={target.account_status || 'active'} />
        </div>
        {destructive && (
          <div className="irreversible-note"><CircleAlert size={18} /><div><strong>정지 해제와 다른 비가역 작업입니다</strong><span>데이터를 즉시 hard delete하는 작업이 아니라 로그인·API 이용을 영구 비활성화합니다. 실행 후에는 이 화면에서 계정을 복구할 수 없습니다.</span></div></div>
        )}
        {destructive && (
          <label className="dialog-field confirmation-field"><span>최종 확인</span><input ref={confirmationRef} autoComplete="off" value={confirmation} onChange={(event) => { setConfirmation(event.target.value); setError(''); }} placeholder="DEACTIVATE 입력" /></label>
        )}
        {error && <div className="dialog-error" role="alert"><CircleAlert size={16} /><span>{error}</span></div>}
        <div className="dialog-actions">
          <button className="dialog-cancel" disabled={busy} onClick={onClose}>취소</button>
          <button ref={primaryActionRef} className={destructive ? 'dialog-danger' : action === 'unsuspend' ? 'dialog-success' : 'dialog-primary'} disabled={busy || (destructive && confirmation !== 'DEACTIVATE')} onClick={() => void submit()}>
            {busy ? <><LoaderCircle className="spin" size={16} />처리 중</> : copy.button}
          </button>
        </div>
      </section>
    </div>
  );
}

function UsersPage({ result, loading, token, search, pageNumber, canGoPrevious, canGoNext, onPrevious, onNext, onChanged, onUnauthorized }: {
  result: ListResult<UserMetric>;
  loading: boolean;
  token: string;
  search: string;
  pageNumber: number;
  canGoPrevious: boolean;
  canGoNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onChanged: () => void;
  onUnauthorized: () => void;
}) {
  const [dialog, setDialog] = useState<{ target: UserMetric; action: UserControlAction; trigger: HTMLButtonElement } | null>(null);
  const [notice, setNotice] = useState<{ type: 'success' | 'warning'; message: string } | null>(null);

  const restoreTrigger = (trigger: HTMLButtonElement | undefined) => {
    window.requestAnimationFrame(() => {
      if (trigger?.isConnected) trigger.focus();
    });
  };

  const closeDialog = () => {
    const trigger = dialog?.trigger;
    setDialog(null);
    restoreTrigger(trigger);
  };

  const completeAction = (message: string) => {
    const trigger = dialog?.trigger;
    setDialog(null);
    setNotice({ type: 'success', message });
    restoreTrigger(trigger);
    onChanged();
  };

  const handleConflict = () => {
    const trigger = dialog?.trigger;
    setDialog(null);
    setNotice({ type: 'warning', message: '다른 관리자가 먼저 상태를 변경했습니다. 최신 목록으로 갱신했습니다.' });
    restoreTrigger(trigger);
    onChanged();
  };

  const normalizedSearch = search.trim().toLowerCase();
  const visibleItems = normalizedSearch
    ? result.items.filter((item) => item.user_id.toLowerCase().includes(normalizedSearch))
    : result.items;

  return (
    <article className="panel data-panel">
      <header className="panel-heading table-heading"><div><p className="section-kicker">AGGREGATED VIEW</p><h3>사용자별 이용 지표</h3><p>사용자 메시지와 이메일 원문을 제외한 집계 결과입니다.</p></div><span className="record-count">{pageNumber}페이지 · {formatNumber(visibleItems.length)}명</span></header>
      {notice && <div className={`user-action-notice ${notice.type}`} role={notice.type === 'warning' ? 'alert' : 'status'} aria-live="polite">{notice.type === 'warning' ? <CircleAlert size={17} /> : <CheckCircle2 size={17} />}<span>{notice.message}</span><button onClick={() => setNotice(null)} aria-label="안내 메시지 닫기"><X size={15} /></button></div>}
      {loading ? <LoadingRows /> : visibleItems.length ? (
        <div className="table-scroll"><table className="users-table">
          <thead><tr><th>사용자</th><th>계정 상태</th><th>세션</th><th>메시지</th><th>기억</th><th>트랜잭션</th><th>실패</th><th>성공률</th><th>최근 활동</th><th>계정 제어</th></tr></thead>
          <tbody>{visibleItems.map((item) => {
            const accountStatus = item.account_status || 'active';
            const changedAt = accountStatus === 'suspended' ? item.suspended_at : accountStatus === 'deactivated' ? item.deactivated_at : item.status_changed_at;
            return <tr key={item.user_id} className={accountStatus === 'deactivated' ? 'deactivated-row' : ''}>
            <td><div className="user-cell"><div className="avatar tiny">U</div><div><strong>사용자 {compactId(item.user_id, 5)}</strong><code>{compactId(item.user_id)}</code></div></div></td>
            <td><div className="account-state-cell"><AccountStatusBadge status={accountStatus} />{changedAt && <small>{formatDate(changedAt)}</small>}</div></td>
            <td>{formatNumber(item.session_count)}</td><td>{formatNumber(item.message_count)}</td><td>{formatNumber(item.memory_count)}</td><td><strong>{formatNumber(item.transaction_count)}</strong></td><td className="danger-text">{formatNumber(item.failed_count)}</td>
            <td><div className="rate-cell"><div><i style={{ width: `${Math.min(100, Math.max(0, item.transaction_count ? (item.transaction_count - item.failed_count) / item.transaction_count * 100 : 0))}%` }} /></div><span>{formatPercent(item.transaction_count ? (item.transaction_count - item.failed_count) / item.transaction_count * 100 : 0)}</span></div></td>
            <td className="nowrap"><span className="muted-cell">{formatDate(item.last_seen_at)}</span></td>
            <td><div className="account-actions">
              {item.protected ? <span className="protected-account"><ShieldCheck size={13} />보호된 관리자</span> : <>
                {accountStatus === 'active' && <button className="account-action suspend" onClick={(event) => setDialog({ target: item, action: 'suspend', trigger: event.currentTarget })}><Ban size={13} />계정 정지</button>}
                {accountStatus === 'suspended' && <button className="account-action restore" onClick={(event) => setDialog({ target: item, action: 'unsuspend', trigger: event.currentTarget })}><UserRoundCheck size={13} />정지 해제</button>}
                {accountStatus !== 'deactivated' && <button className="account-action deactivate" onClick={(event) => setDialog({ target: item, action: 'deactivate', trigger: event.currentTarget })}><Trash2 size={13} />삭제(비활성화)</button>}
                {accountStatus === 'deactivated' && <span className="actions-disabled">조작 불가</span>}
              </>}
            </div></td>
          </tr>})}</tbody>
        </table></div>
      ) : <EmptyState title={normalizedSearch ? '현재 페이지에서 일치하는 사용자가 없습니다' : '조건에 맞는 사용자가 없습니다'} description={normalizedSearch ? '검색은 현재 페이지의 익명 사용자 ID에만 적용됩니다.' : '상태나 기간 필터를 변경해 보세요.'} />}
      <nav className="cursor-pagination" aria-label="사용자 목록 페이지 이동">
        <button disabled={!canGoPrevious || loading} onClick={onPrevious}><ChevronLeft size={15} />이전</button>
        <span><strong>{pageNumber}</strong> 페이지</span>
        <button disabled={!canGoNext || loading} onClick={onNext}>다음<ChevronRight size={15} /></button>
      </nav>
      {dialog && <UserControlDialog token={token} target={dialog.target} action={dialog.action} onClose={closeDialog} onSuccess={completeAction} onUnauthorized={onUnauthorized} onConflict={handleConflict} />}
    </article>
  );
}

function CorrelationDrawer({ id, detail, loading, onClose }: { id: string; detail: CorrelationDetail | null; loading: boolean; onClose: () => void }) {
  const timeline = useMemo(() => {
    if (!detail) return [];
    return [
      ...detail.transactions.map((event) => ({ type: 'event' as const, at: event.occurred_at, status: event.status, title: event.http_path || event.event_type, subtitle: `${event.http_method || 'EVENT'} · ${formatLatency(event.latency_ms)}` })),
      ...detail.operations.map((operation) => ({ type: 'operation' as const, at: operation.updated_at, status: operation.status, title: operation.operation_type, subtitle: `진행률 ${operation.progress_percent}% · v${operation.version}` })),
    ].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  }, [detail]);
  return (
    <div className="drawer-layer" role="dialog" aria-modal="true" aria-label="Correlation 상세">
      <button className="drawer-scrim" onClick={onClose} aria-label="상세 닫기" />
      <aside className="drawer">
        <header><div><p className="section-kicker">CORRELATION TRACE</p><h2>요청 흐름 상세</h2></div><button className="icon-button" onClick={onClose} aria-label="상세 닫기"><X size={20} /></button></header>
        <div className="correlation-id"><Fingerprint size={17} /><code>{id}</code></div>
        <div className="privacy-note"><ShieldCheck size={17} /><p><strong>민감 정보 보호됨</strong><span>요청·응답 본문, 토큰, 음성 데이터는 이 추적에 포함되지 않습니다.</span></p></div>
        {loading ? <LoadingRows /> : timeline.length ? <div className="timeline">
          {timeline.map((item, index) => <div className="timeline-item" key={`${item.type}-${item.at}-${index}`}>
            <div className={`timeline-dot ${statusTone(item.status)}`}><i /></div>
            <div className="timeline-card"><div><StatusBadge status={item.status} /><time>{formatDate(item.at)}</time></div><strong>{item.title}</strong><p>{item.subtitle}</p></div>
          </div>)}
        </div> : <EmptyState title="추적 이벤트가 없습니다" />}
      </aside>
    </div>
  );
}

function App() {
  const [token, setToken] = useState<string | null>(() => sessionStore.get());
  const [user, setUser] = useState<AdminUser | null>(null);
  const [booting, setBooting] = useState(Boolean(token));
  const [page, setPage] = useState<Page>('overview');
  const [range, setRange] = useState<RangeKey>('24h');
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [now, setNow] = useState(Date.now());
  const [refreshKey, setRefreshKey] = useState(0);
  const [overview, setOverview] = useState(EMPTY_OVERVIEW);
  const [transactions, setTransactions] = useState<ListResult<TransactionEvent>>({ items: [], total: 0 });
  const [operations, setOperations] = useState<ListResult<OperationState>>({ items: [], total: 0 });
  const [users, setUsers] = useState<ListResult<UserMetric>>({ items: [], total: 0 });
  const [userCursor, setUserCursor] = useState<string>();
  const [userCursorHistory, setUserCursorHistory] = useState<Array<string | null>>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('memorypal.admin.theme') !== 'light');
  const [correlationId, setCorrelationId] = useState('');
  const [correlation, setCorrelation] = useState<CorrelationDetail | null>(null);
  const [correlationLoading, setCorrelationLoading] = useState(false);
  const latestRequest = useRef(0);

  const period = useMemo(() => periodFor(range, now), [range, now]);
  const requestSearch = page === 'users' ? '' : appliedSearch;

  const unauthorized = useCallback(() => {
    sessionStore.clear();
    setToken(null);
    setUser(null);
    setBooting(false);
  }, []);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    adminApi.me(token, controller.signal).then(setUser).catch((reason) => {
      if (reason instanceof DOMException && reason.name === 'AbortError') return;
      unauthorized();
    }).finally(() => setBooting(false));
    return () => controller.abort();
  }, [token, unauthorized]);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('memorypal.admin.theme', dark ? 'dark' : 'light');
  }, [dark]);

  useEffect(() => {
    const timer = window.setTimeout(() => setAppliedSearch(search.trim()), 350);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!token || !user) return;
    const refresh = () => {
      if (document.visibilityState === 'visible') {
        setNow(Date.now());
        setRefreshKey((value) => value + 1);
      }
    };
    const timer = window.setInterval(refresh, 30_000);
    const visibility = () => { if (document.visibilityState === 'visible') refresh(); };
    document.addEventListener('visibilitychange', visibility);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', visibility); };
  }, [token, user]);

  useEffect(() => {
    if (!token || !user) return;
    const controller = new AbortController();
    const requestId = ++latestRequest.current;
    setLoading(true);
    setRefreshing(true);
    setError('');
    const requestStatus = normalizeStatus(page, status);
    const filters = { from: period.from, to: period.to, status: requestStatus, search: requestSearch || undefined, limit: 200 };
    const pageRequest = page === 'transactions'
      ? adminApi.transactions(token, filters, controller.signal).then(setTransactions)
      : page === 'operations'
        ? adminApi.operations(token, filters, controller.signal).then(setOperations)
        : page === 'users'
          ? adminApi.users(token, period.from, period.to, requestStatus, userCursor, controller.signal).then(setUsers)
          : Promise.resolve();
    Promise.all([adminApi.overview(token, period.from, period.to, controller.signal).then(setOverview), pageRequest])
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return;
        if (reason instanceof ApiError && reason.status === 401) { unauthorized(); return; }
        setError(reason instanceof Error ? reason.message : '운영 데이터를 불러오지 못했습니다.');
      })
      .finally(() => {
        if (requestId === latestRequest.current) { setLoading(false); setRefreshing(false); }
      });
    return () => controller.abort();
  }, [token, user, page, period.from, period.to, status, requestSearch, userCursor, refreshKey, unauthorized]);

  useEffect(() => {
    if (!token || !correlationId) { setCorrelation(null); return; }
    const controller = new AbortController();
    setCorrelationLoading(true);
    adminApi.correlation(token, correlationId, period.from, period.to, controller.signal).then(setCorrelation).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(reason instanceof Error ? reason.message : '요청 흐름을 불러오지 못했습니다.');
    }).finally(() => setCorrelationLoading(false));
    return () => controller.abort();
  }, [token, correlationId, period.from, period.to]);

  async function logout() {
    const current = token;
    unauthorized();
    if (current) await adminApi.logout(current).catch(() => undefined);
  }

  function refresh() {
    setNow(Date.now());
    setRefreshKey((value) => value + 1);
  }

  function resetUserPagination() {
    setUserCursor(undefined);
    setUserCursorHistory([]);
  }

  function changePage(nextPage: Page) {
    setPage(nextPage);
    setStatus('');
    setSearch('');
    resetUserPagination();
  }

  function changeRange(nextRange: RangeKey) {
    setRange(nextRange);
    resetUserPagination();
  }

  function changeStatus(nextStatus: string) {
    setStatus(nextStatus);
    if (page === 'users') resetUserPagination();
  }

  function nextUserPage() {
    if (!users.next_cursor) return;
    setUserCursorHistory((history) => [...history, userCursor ?? null]);
    setUserCursor(users.next_cursor);
  }

  function previousUserPage() {
    if (!userCursorHistory.length) return;
    const previous = userCursorHistory[userCursorHistory.length - 1];
    setUserCursorHistory((history) => history.slice(0, -1));
    setUserCursor(previous ?? undefined);
  }

  if (booting) return <div className="boot-screen"><div className="brand-mark"><span>M</span></div><LoaderCircle className="spin" size={22} /><span>관리자 권한 확인 중</span></div>;
  if (!token || !user) return <LoginView onLogin={(nextToken, nextUser) => { setToken(nextToken); setUser(nextUser); }} />;

  const meta = PAGE_META[page];
  return (
    <div className="admin-shell">
      <Sidebar page={page} onPage={changePage} user={user} onLogout={logout} open={mobileNav} onClose={() => setMobileNav(false)} health={error ? 'delayed' : refreshing ? 'syncing' : 'current'} />
      <main className="content">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="메뉴 열기"><Menu size={21} /></button>
          <div className="page-title"><p className="eyebrow">{meta.eyebrow}</p><h1>{meta.title}</h1></div>
          <div className="top-actions">
            <div className="last-updated"><i className={refreshing ? 'pulse' : ''} /><span>{refreshing ? '동기화 중' : `${formatDate(overview.generated_at || new Date(now).toISOString(), false)} 갱신`}</span></div>
            <button className="icon-button" onClick={() => setDark((value) => !value)} aria-label={dark ? '밝은 화면' : '어두운 화면'}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
            <button className="icon-button" onClick={refresh} disabled={refreshing} aria-label="새로고침"><RefreshCcw className={refreshing ? 'spin' : ''} size={18} /></button>
          </div>
        </header>

        <section className="filterbar" aria-label="데이터 필터">
          <div className="filter-icon"><ListFilter size={17} /></div>
          <label><span>조회 기간</span><select value={range} onChange={(event) => changeRange(event.target.value as RangeKey)}>{Object.entries(RANGE_LABELS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
          <label><span>상태</span><select value={status} onChange={(event) => changeStatus(event.target.value)}><option value="">전체 상태</option>{Object.entries(page === 'users' ? ACCOUNT_STATUS_LABELS : STATUS_LABELS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
          <label className="search-filter"><span>{page === 'users' ? '현재 페이지 검색' : '빠른 검색'}</span><div><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={page === 'users' ? '현재 페이지의 사용자 ID 검색' : '사용자 또는 correlation ID'} />{search && <button onClick={() => setSearch('')} aria-label="검색어 지우기"><X size={14} /></button>}</div></label>
          <div className="filter-summary"><Clock3 size={15} /><span>{RANGE_LABELS[range]}</span></div>
        </section>

        {error && <div className="error-banner" role="alert"><CircleAlert size={18} /><span>{error}</span><button onClick={() => setError('')} aria-label="오류 닫기"><X size={16} /></button></div>}

        <div className="page-body">
          {page === 'overview' && <OverviewPage overview={overview} />}
          {page === 'transactions' && <TransactionsPage result={transactions} loading={loading} onCorrelation={setCorrelationId} />}
          {page === 'operations' && <OperationsPage result={operations} loading={loading} onCorrelation={setCorrelationId} />}
          {page === 'users' && <UsersPage result={users} loading={loading} token={token} search={appliedSearch} pageNumber={userCursorHistory.length + 1} canGoPrevious={userCursorHistory.length > 0} canGoNext={Boolean(users.next_cursor)} onPrevious={previousUserPage} onNext={nextUserPage} onChanged={refresh} onUnauthorized={unauthorized} />}
        </div>
        <footer className="content-footer"><span>MemoryPal Operations Console</span><span><ShieldCheck size={14} /> 개인정보 최소 수집 원칙 적용</span></footer>
      </main>
      {correlationId && <CorrelationDrawer id={correlationId} detail={correlation} loading={correlationLoading} onClose={() => setCorrelationId('')} />}
    </div>
  );
}

export default App;
