import { formatApiError, createErrorState, classifyError } from './errorMessages';

describe('errorMessages Utilities', () => {
  describe('formatApiError', () => {
    // 1. 간단한 문자열 에러 메시지 처리
    it('handles simple string error message', () => {
      const result = formatApiError('이메일 형식이 올바르지 않습니다.', 'fallback');
      
      expect(result).toBe('이메일 형식이 올바르지 않습니다.');
    });

    // 2. 빈 문자열 처리 (fallback 사용)
    it('uses fallback when string is empty', () => {
      const result = formatApiError('', 'fallback');
      
      expect(result).toBe('fallback');
    });

    // 3. 공백만 있는 문자열 처리
    it('trims whitespace from string error message', () => {
      const result = formatApiError('   ', 'fallback');
      
      expect(result).toBe('fallback');
    });

    // 4. FastAPI 배열 기반 에러 파싱 (validation errors)
    it('parses FastAPI validation array errors', () => {
      const apiErrors = [
        { loc: ['body', 'email'], msg: '이메일 형식이 올바르지 않습니다.', type: 'value_error' },
        { loc: ['body', 'password'], msg: '비밀번호는 최소 8 자여야 합니다.', type: 'value_error' },
      ];
      
      const result = formatApiError(apiErrors, 'fallback');
      
      expect(result).toContain('이메일 형식이 올바르지 않습니다.');
      expect(result).toContain('비밀번호는 최소 8 자여야 합니다.');
    });

    // 5. FastAPI 단일 에러 파싱
    it('parses single FastAPI error object', () => {
      const apiError = {
        detail: '이메일은 필수 항목입니다.',
      };
      
      const result = formatApiError(apiError, 'fallback');
      
      expect(result).toBe('이메일은 필수 항목입니다.');
    });

    // 6. FastAPI message 필드 파싱
    it('parses FastAPI message field when available', () => {
      const apiError = {
        message: '계정이 일시중지되었습니다.',
      };
      
      const result = formatApiError(apiError, 'fallback');
      
      expect(result).toBe('계정이 일시중지되었습니다.');
    });

    // 7. GraphQL 에러 파싱 (errors 배열)
    it('parses GraphQL error array', () => {
      const graphqlErrors = [
        { message: 'Invalid input', locations: [{ line: 1, column: 2 }] },
        { message: 'Field required', locations: [{ line: 1, column: 5 }] },
      ];
      
      const result = formatApiError(graphqlErrors, 'fallback');
      
      expect(result).toContain('Invalid input');
      expect(result).toContain('Field required');
    });

    // 8. GraphQL 단일 에러 파싱
    it('parses single GraphQL error object', () => {
      const graphqlError = {
        message: 'Unauthorized access.',
        errors: [{ message: 'You are not authorized.' }],
      };
      
      const result = formatApiError(graphqlError, 'fallback');
      
      expect(result).toContain('You are not authorized.');
    });

    // 9. Mixed nested 에러 파싱
    it('handles nested error structure', () => {
      const mixedError = [
        { loc: ['body', 'email'], msg: '이메일 필수' },
        { message: 'API 에러 메시지' },
      ];
      
      const result = formatApiError(mixedError, 'fallback');
      
      expect(result).toContain('이메일 필수');
    });

    // 10. Fallback 메시지 기본값 검증
    it('uses default fallback when no custom fallback provided', () => {
      const result = formatApiError(null, undefined);
      
      expect(result).toBe('요청을 처리하지 못했어요.');
    });

    // 11. null 값 처리
    it('handles null error gracefully', () => {
      const result = formatApiError(null, 'fallback');
      
      expect(result).toBe('fallback');
    });

    // 12. undefined 값 처리
    it('handles undefined error gracefully', () => {
      const result = formatApiError(undefined, 'fallback');
      
      expect(result).toBe('fallback');
    });

    // 13. 숫자 타입 에러 처리 (edge case)
    it('handles number type error gracefully', () => {
      const result = formatApiError(404 as unknown as string, 'fallback');
      
      expect(result).toBe('404');
    });

    // 14. 객체 내 message 필드 우선순우 검증
    it('prioritizes message field over detail', () => {
      const errorObj = {
        detail: '상세 메시지',
        message: '사용자 메시지',
      };
      
      const result = formatApiError(errorObj, 'fallback');
      
      expect(result).toBe('사용자 메시지');
    });

    // 15. Empty array 처리
    it('handles empty error array gracefully', () => {
      const result = formatApiError([], 'fallback');
      
      expect(result).toBe('fallback');
    });
  });

  describe('createErrorState', () => {
    // 1. 기본 에러 상태 생성
    it('creates error state by default', () => {
      const state = createErrorState('에러 발생!', 'error');
      
      expect(state.type).toBe('error');
      expect(state.message).toBe('에러 발생!');
    });

    // 2. warning 타입 에러 상태 생성
    it('creates warning state correctly', () => {
      const state = createErrorState('타임아웃 발생', 'warning');
      
      expect(state.type).toBe('warning');
    });

    // 3. info 타입 에러 상태 생성
    it('creates info state correctly', () => {
      const state = createErrorState('정보: 작업이 완료되었습니다.', 'info');
      
      expect(state.type).toBe('info');
    });

    // 4. message 파싱 검증
    it('formats message through formatApiError', () => {
      const fastapiErrors = [
        { loc: ['body', 'password'], msg: '비밀번호가 너무 짧습니다.' },
      ];
      
      const state = createErrorState(fastapiErrors);
      
      expect(state.message).toContain('비밀번호가 너무 짧습니다.');
    });

    // 5. default type fallback 검증
    it('uses error type when not specified', () => {
      const state = createErrorState('테스트 에러');
      
      expect(state.type).toBe('error');
    });
  });

  describe('classifyError', () => {
    // 1. 401 인증 에러 - critical
    it('classifies 401 as critical', () => {
      const result = classifyError('401 Unauthorized: Invalid token');
      
      expect(result).toBe('critical');
    });

    // 2. Forbidden 에러 - critical
    it('classifies forbidden as critical', () => {
      const result = classifyError('Access forbidden: insufficient permissions');
      
      expect(result).toBe('critical');
    });

    // 3. 비밀번호 관련 에러 - critical
    it('classifies invalid password as critical', () => {
      const result = classifyError('Invalid password provided');
      
      expect(result).toBe('critical');
    });

    // 4. 계정 삭제 메시지 - critical
    it('classifies account deleted as critical', () => {
      const result = classifyError('Account has been deleted and cannot be recovered.');
      
      expect(result).toBe('critical');
    });

    // 5. Rate Limit 에러 - warning
    it('classifies rate limit as warning', () => {
      const result = classifyError('Rate limit exceeded. Please retry after 60 seconds.');
      
      expect(result).toBe('warning');
    });

    // 6. Timeout 에러 - warning
    it('classifies timeout as warning', () => {
      const result = classifyError('Request timed out after 30 seconds.');
      
      expect(result).toBe('warning');
    });

    // 7. 네트워크 에러 - warning
    it('classifies network error as warning', () => {
      const result = classifyError('Network connection lost.');
      
      expect(result).toBe('warning');
    });

    // 8. Retry 관련 에러 - warning
    it('classifies retry as warning', () => {
      const result = classifyError('Operation needs to be retried.');
      
      expect(result).toBe('warning');
    });

    // 9. 일반 정보 메시지 - info
    it('classifies general information as info', () => {
      const result = classifyError('작업이 완료되었습니다.');
      
      expect(result).toBe('info');
    });

    // 10. 한글 메시지 처리 - critical
    it('handles Korean messages with critical keywords', () => {
      const result = classifyError('비밀번호가 일치하지 않습니다.');
      
      expect(result).toBe('critical');
    });

    // 11. 혼합 문자 메시지 처리
    it('handles mixed language messages', () => {
      const result = classifyError('Error: Password is too short (최소 8 자)');
      
      // 'Error' 가 포함되어 있으므로 일반 info 로 분류되지만, 
      // 실제 로직에서는 하위 키워드 우선순우가 있음
      expect(result).toBe('info');
    });

    // 12. 숫자만 있는 에러 코드 - info (기본 처리)
    it('handles numeric error codes as info', () => {
      const result = classifyError('500');
      
      expect(result).toBe('info');
    });

    // 13. 공백만 있는 메시지 - info
    it('handles whitespace-only message as info', () => {
      const result = classifyError('   ');
      
      expect(result).toBe('info');
    });

    // 14. Empty string 처리 - info
    it('handles empty string as info', () => {
      const result = classifyError('');
      
      expect(result).toBe('info');
    });

    // 15. Null/undefined 처리
    it('handles null message gracefully', () => {
      const result = classifyError(null as unknown as string);
      
      expect(result).toBe('info');
    });
  });
});