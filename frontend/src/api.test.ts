import { ApiError, api, setUnauthorizedHandler } from './api';

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

describe('public API client', () => {
  beforeEach(() => {
    (global.fetch as jest.Mock).mockReset();
  });

  it('serializes login through the public endpoint', async () => {
    const payload = { access_token: 'token', user: { id: 'u1' } };
    (global.fetch as jest.Mock).mockResolvedValue(response(payload));

    await expect(api.login('test@test.com', 'password')).resolves.toBe(payload);
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ email: 'test@test.com', password: 'password' });
  });

  it('adds authorization and JSON headers to authenticated calls', async () => {
    (global.fetch as jest.Mock).mockResolvedValue(response([]));

    await api.sessions('jwt-token');
    const [, init] = (global.fetch as jest.Mock).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer jwt-token');
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('notifies the auth boundary and throws ApiError on an authenticated 401', async () => {
    const onUnauthorized = jest.fn();
    const unregister = setUnauthorizedHandler(onUnauthorized);
    (global.fetch as jest.Mock).mockResolvedValue(response({ detail: 'expired' }, 401));

    await expect(api.sessions('expired-token')).rejects.toEqual(
      expect.objectContaining<ApiError>({ name: 'ApiError', message: 'expired', status: 401 }),
    );
    expect(onUnauthorized).toHaveBeenCalledWith('expired-token');
    unregister();
  });

  it('uses a friendly fallback when an error body is not JSON', async () => {
    const failed = response(undefined, 503) as Response & { json: jest.Mock };
    failed.json.mockRejectedValue(new Error('invalid json'));
    (global.fetch as jest.Mock).mockResolvedValue(failed);

    await expect(api.sessions('token')).rejects.toEqual(
      expect.objectContaining({ message: '요청을 처리하지 못했어요.', status: 503 }),
    );
  });

  it('only sends a user-selected model for the none persona', async () => {
    (global.fetch as jest.Mock).mockResolvedValue(response({}));
    await api.chat('token', 'hello', undefined, undefined, false, false, 'none', false, false, undefined, 'model.gguf');
    const [, noneInit] = (global.fetch as jest.Mock).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(noneInit.body)).model_key).toBe('model.gguf');

    (global.fetch as jest.Mock).mockResolvedValue(response({}));
    await api.chat('token', 'hello', undefined, undefined, false, false, 'default', false, false, undefined, 'model.gguf');
    const [, defaultInit] = (global.fetch as jest.Mock).mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(defaultInit.body)).model_key).toBeUndefined();
  });
});
