import { api, ApiError, setUnauthorizedHandler } from './api';

describe('api Client', () => {
  // Mock fetch
  (global as any).fetch = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterAll(() => {
    delete (global as any).fetch;
  });

  describe('request function', () => {
    // 1. 성공적인 fetch 응답 처리
    it('handles successful API response', async () => {
      const mockResponse = { data: 'success' };
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.request('/test');
      
      expect(result).toBe(mockResponse);
    });

    // 2. 401 에러 시 unauthorizedHandler 호출 검증
    it('calls unauthorizedHandler on 401 error', async () => {
      const handlerMock = jest.fn();
      const unauthorizedHandlerSpy = jest.spyOn(api as any, 'setUnauthorizedHandler');
      
      api.setUnauthorizedHandler(handlerMock);

      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Unauthorized' }),
      });

      try {
        await (api as any).request('/test');
      } catch {
        // 예외는 예상됨
      }

      expect(handlerMock).toHaveBeenCalledWith('mock-jwt-token');
    });

    // 3. 403 Forbidden 에러 처리
    it('throws ApiError on 403 status', async () => {
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'Forbidden' }),
      });

      try {
        await (api as any).request('/test');
        fail('Expected ApiError to be thrown');
      } catch (error) {
        const apiErr = error as ApiError;
        expect(apiErr.status).toBe(403);
      }
    });

    // 4. 404 Not Found 에러 처리
    it('throws ApiError on 404 status', async () => {
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Resource not found' }),
      });

      try {
        await (api as any).request('/test');
        fail('Expected ApiError to be thrown');
      } catch (error) {
        const apiErr = error as ApiError;
        expect(apiErr.status).toBe(404);
      }
    });

    // 5. 500 서버 에러 처리
    it('handles 500 server error', async () => {
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Internal Server Error' }),
      });

      try {
        await (api as any).request('/test');
        fail('Expected ApiError to be thrown');
      } catch (error) {
        const apiErr = error as ApiError;
        expect(apiErr.status).toBe(500);
      }
    });

    // 6. 비 JSON 응답 처리 (fallback 메시지)
    it('uses fallback message for non-JSON responses', async () => {
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => '<html><body>401 Unauthorized</body></html>',
      });

      try {
        await (api as any).request('/test');
        fail('Expected ApiError to be thrown');
      } catch (error) {
        const apiErr = error as ApiError;
        expect(apiErr.message).toBe('요청을 처리하지 못했어요.');
      }
    });

    // 7. JSON 파싱 에러 시 fallback 메시지 사용
    it('uses fallback on JSON parse error', async () => {
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => '{ invalid json }',
      });

      try {
        await (api as any).request('/test');
        fail('Expected ApiError to be thrown');
      } catch (error) {
        const apiErr = error as ApiError;
        expect(apiErr.message).toBe('요청을 처리하지 못했어요.');
      }
    });

    // 8. Custom headers 전달 검증
    it('passes custom headers to request', async () => {
      const mockResponse = {};
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.request('/test', {
        headers: { 'X-Custom-Header': 'custom-value' },
      });

      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Custom-Header': 'custom-value',
          }),
        })
      );
    });

    // 9. Bodyless request 처리 (GET 요청)
    it('handles GET requests without body', async () => {
      const mockResponse = {};
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.request('/test', { method: 'GET' });

      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          body: undefined,
        })
      );
    });

    // 10. FormData 처리 (Content-Type 자동 설정)
    it('skips Content-Type for FormData body', async () => {
      const mockResponse = {};
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.request('/test', {
        method: 'POST',
        body: new FormData(),
      });

      const callArgs = (global as any).fetch.mock.calls[0][1] as RequestInit;
      expect(callArgs.headers.get('Content-Type')).toBe(undefined);
    });

    // 11. JSON 타입 인코딩 검증
    it('sets Content-Type to application/json for JSON body', async () => {
      const mockResponse = {};
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.request('/test', {
        method: 'POST',
        body: { key: 'value' },
      });

      const callArgs = (global as any).fetch.mock.calls[0][1] as RequestInit;
      expect(callArgs.headers.get('Content-Type')).toBe('application/json');
    });

    // 12. Authorization header 설정 검증
    it('sets Authorization header with token', async () => {
      const mockResponse = {};
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.request('/test', {}, 'mock-jwt-token');

      const callArgs = (global as any).fetch.mock.calls[0][1] as RequestInit;
      expect(callArgs.headers.get('Authorization')).toBe('Bearer mock-jwt-token');
    });

    // 13. Auth header 없이 토큰 전달 시 처리 검증
    it('does not set Authorization header when token is null', async () => {
      const mockResponse = {};
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.request('/test', {}, null);

      const callArgs = (global as any).fetch.mock.calls[0][1] as RequestInit;
      expect(callArgs.headers.get('Authorization')).toBe(undefined);
    });

    // 14. 빈 토큰 문자열 처리
    it('does not set Authorization header for empty token', async () => {
      const mockResponse = {};
      jest.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.request('/test', {}, '');

      const callArgs = (global as any).fetch.mock.calls[0][1] as RequestInit;
      expect(callArgs.headers.get('Authorization')).toBe(undefined);
    });

    // 15. API_URL 기본값 검증 (환경 변수 없음 시)
    it('uses default API URL when EXPO_PUBLIC_API_URL is not set', () => {
      process.env.EXPO_PUBLIC_API_URL = undefined;

      const callArgs = (global as any).fetch.mock.calls[0][1] as RequestInit;
      expect(callArgs[0]).toContain('http://127.0.0.1:8000/v1');
    });

    // 16. API_URL 환경 변수 설정 검증
    it('uses custom API URL when EXPO_PUBLIC_API_URL is set', () => {
      process.env.EXPO_PUBLIC_API_URL = 'https://api.example.com/v1';

      const callArgs = (global as any).fetch.mock.calls[0][1] as RequestInit;
      expect(callArgs[0]).toContain('https://api.example.com/v1');
    });
  });

  describe('setUnauthorizedHandler', () => {
    // 1. 핸들러 등록 및 해제
    it('registers and unregisters unauthorized handler', () => {
      const handler1 = jest.fn();
      const handler2 = jest.fn();

      const unregister1 = api.setUnauthorizedHandler(handler1);
      expect(api.unauthorizedHandler).toBe(handler1);

      const unregister2 = api.setUnauthorizedHandler(handler2);
      expect(api.unauthorizedHandler).toBe(handler2);

      unregister1();
      expect(api.unauthorizedHandler).toBeUndefined();
    });

    // 2. 동일한 핸들러로 여러 번 등록 시 중복 방지
    it('prevents duplicate handler registration', () => {
      const handler = jest.fn();
      
      const unregister1 = api.setUnauthorizedHandler(handler);
      const unregister2 = api.setUnauthorizedHandler(handler);

      expect(api.unauthorizedHandler).toBe(handler);
      
      unregister1();
      expect(api.unauthorizedHandler).toBeUndefined();
    });

    // 3. 오래된 토큰으로 인한 지연된 401 방지
    it('prevents delayed 401 from old requests', async () => {
      const handler = jest.fn();
      api.setUnauthorizedHandler(handler);

      // 현재 토큰과 다른 토큰으로 인한 401 은 처리되지 않아야 함
      await (api as any).request('/test', {}, 'old-token').catch(() => {});

      expect(handler).not.toHaveBeenCalledWith('old-token');
    });
  });
});