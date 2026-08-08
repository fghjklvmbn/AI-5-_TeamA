import type { ApiErrorMessage } from '../types';

/**
 * API 에러 메시지를 사용자 친화적으로 포맷팅합니다.
 */
export function formatApiError(detail: unknown, fallback: string = '요청을 처리하지 못했어요.'): string {
  // 문자열인 경우 그대로 반환
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  // 배열인 경우 (FastAPI validation errors)
  if (Array.isArray(detail)) {
    const messages: string[] = [];
    
    for (const item of detail) {
      if (!item || typeof item !== 'object') continue;
      
      const value = item as { loc?: unknown[]; msg?: unknown };
      
      if (typeof value.msg === 'string') {
        const field = Array.isArray(value.loc) ? value.loc.at(-1) : undefined;
        const fieldName = typeof field === 'string' ? field.replace(/_/g, ' ') : '';
        messages.push(`${fieldName}: ${value.msg}`);
      }
    }

    if (messages.length) {
      return messages.join('\n');
    }
  }

  // 객체인 경우 (GraphQL error 등)
  if (detail && typeof detail === 'object') {
    const value = detail as { message?: unknown; errors?: unknown };
    
    if (typeof value.message === 'string' && value.message.trim()) {
      return value.message;
    }

    if (value.errors && Array.isArray(value.errors)) {
      for (const error of value.errors) {
        if (error && typeof error === 'object' && typeof error.message === 'string') {
          messages.push(error.message);
        }
      }
      if (messages.length) return messages.join('\n');
    }
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
export function classifyError(message: string): 'critical' | 'warning' | 'info' {
  const lower = message.toLowerCase();
  
  // 치명적 에러 패턴
  if (
    lower.includes('401') || 
    lower.includes('forbidden') || 
    lower.includes('invalid password') ||
    lower.includes('account deleted')
  ) {
    return 'critical';
  }

  // 주의할 에러 패턴
  if (
    lower.includes('rate limit') ||
    lower.includes('timeout') ||
    lower.includes('network') ||
    lower.includes('retry')
  ) {
    return 'warning';
  }

  // 정보성 메세지
  return 'info';
}
