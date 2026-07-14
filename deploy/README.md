# MemoryPal deployment routes

The deployed public prefix is `/api_memoripal`. Although the project name is
MemoryPal, this existing DNS path spelling must be used consistently.

## Request flow

```text
Web/mobile client
  -> https://developark.duckdns.org/api_memoripal/gateway/v1
  -> gateway on 192.168.2.75:8000
     -> STT     192.168.2.75:8001
     -> TTS     192.168.2.75:8003
     -> archive 192.168.2.75:8004
     -> LLM     192.168.2.41:1234/v1
```

Clients should call only the gateway. The service-specific public routes are
retained for diagnostics and existing tools, not for normal frontend traffic.

## DNS nginx server

Copy the locations from `nginx/memorypal.conf.example` into the HTTPS
`server` block, then run `nginx -t` and reload nginx. The gateway location is:

```nginx
location /api_memoripal/gateway/ {
    proxy_pass http://192.168.2.75:8000/;
}
```

The trailing slashes are intentional: nginx strips the public prefix before
forwarding `/v1/...` to FastAPI.

## Gateway host

Copy the repository-root `.env.example` to `.env`, set a long random JWT
secret and the real database URL there, then start the gateway from `backend/gateway`:

```powershell
python -m memorypal_api
```

The production `MEMORYPAL_ROOT_PATH=/api_memoripal/gateway` keeps Swagger and
OpenAPI URLs correct behind the reverse proxy. Internal service URLs use the
LAN directly to avoid an unnecessary DNS/TLS round trip.

## Frontend

Set the production API URL to:

```text
EXPO_PUBLIC_API_URL=https://developark.duckdns.org/api_memoripal/gateway/v1
```

Expo's `experiments.baseUrl` is `/api_memoripal/main`, so exported JavaScript
and assets also work when the site is hosted below that path.

For a production static export alternative:

```powershell
cd frontend
npm run build:web
npm run serve:web
```

The current nginx `main` upstream is port 8081, which serves the production
export with `npm run serve:web:proxy`. Do not expose `expo start --web` below
this public subpath: its root-relative bundle and HMR entrypoint conflict with
the proxy prefix and can terminate Metro when an external browser connects.
The production export does not require `/hot` or `/message` WebSockets.

## Public audio URLs

When archive and TTS return audio URLs, start them with these environment
variables so browsers receive HTTPS URLs instead of private LAN paths:

```powershell
$env:MEMORYPAL_ARCHIVE_PUBLIC_URL='https://developark.duckdns.org/api_memoripal/archive'
$env:MEMORYPAL_TTS_PUBLIC_URL='https://developark.duckdns.org/api_memoripal/tts'
```
