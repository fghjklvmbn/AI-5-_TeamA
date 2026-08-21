import type { ApiErrorMessage } from '../types';

/**
 * API 에러 메시지를 사용자 친화적으로 포맷팅합니다.
 */
export function formatApiError(detail: unknown, fallback: string = '요청을 처리하지 못했어요.'): string {
  // 문자열인 경우 그대로 반환
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }

  if (typeof detail === 'number' || typeof detail === 'boolean') return String(detail);

  // 배열인 경우 (FastAPI validation errors)
  if (Array.isArray(detail)) {
    const messages: string[] = [];
    
    for (const item of detail) {
      if (!item || typeof item !== 'object') continue;
      
      const value = item as { loc?: unknown[]; msg?: unknown; message?: unknown };
      
      if (typeof value.msg === 'string') {
        const field = Array.isArray(value.loc) ? value.loc.at(-1) : undefined;
        const fieldName = typeof field === 'string' ? field.replace(/_/g, ' ') : '';
        messages.push(`${fieldName}: ${value.msg}`);
      } else if (typeof value.message === 'string' && value.message.trim()) {
        messages.push(value.message.trim());
      }
    }

    if (messages.length) {
      return messages.join('\n');
    }
  }

  // 객체인 경우 (GraphQL error 등)
  if (detail && typeof detail === 'object') {
    const value = detail as { detail?: unknown; message?: unknown; msg?: unknown; errors?: unknown };

    if (value.errors && Array.isArray(value.errors)) {
      const messages: string[] = [];
      for (const error of value.errors) {
        if (error && typeof error === 'object') {
          const nested = error as { message?: unknown };
          if (typeof nested.message === 'string') messages.push(nested.message);
        }
      }
      if (messages.length) return messages.join('\n');
    }

    if (typeof value.message === 'string' && value.message.trim()) return value.message.trim();
    if (typeof value.detail === 'string' && value.detail.trim()) return value.detail.trim();
    if (typeof value.msg === 'string' && value.msg.trim()) return value.msg.trim();
  }

  // 기본 fallback 메시지 반환
  return fallback;
}

/**
 * 에러 상태를 사용자 친화적인 메시지로 변환합니다.
 */
export interface ErrorState {
  message: string;
  type: 'error' | 'warning' | 'info';
}

export function createErrorState(detail: unknown, type: ErrorState['type'] = 'error'): ErrorState {
  const formattedMessage = formatApiError(detail);
  
  return {
    message: formattedMessage,
    type,
  };
}

/**
 * 에러 메시지를 심각도별로 분류합니다.
 */
export function classifyError(message: unknown): 'critical' | 'warning' | 'info' {
  if (typeof message !== 'string') return 'info';
  const lower = message.toLowerCase();
  
  // 치명적 에러 패턴
  if (
    lower.includes('401') || 
    lower.includes('forbidden') || 
    lower.includes('invalid password') ||
    lower.includes('account deleted') ||
    lower.includes('account has been deleted') ||
    lower.includes('비밀번호가 일치하지')
  ) {
    return 'critical';
  }

  // 주의할 에러 패턴
  if (
    lower.includes('rate limit') ||
    lower.includes('timeout') ||
    lower.includes('timed out') ||
    lower.includes('network') ||
    lower.includes('retry') ||
    lower.includes('retried')
  ) {
    return 'warning';
  }

  // 정보성 메세지
  return 'info';
}
