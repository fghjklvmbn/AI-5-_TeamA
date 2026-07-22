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

## Administrator console

The administrator console is a separate static application served by the
internal MemoryPal host on port `8082`. The reverse proxy for its public path
belongs to the external `developark.duckdns.org` Nginx server, not to an
internal frontend Nginx instance. Use the locations in
`admin-nginx.conf.example`; they forward `/api_memoripal/manage/` to
`192.168.2.75:8082`.

The console calls the Gateway through the same public origin at
`/api_memoripal/gateway/v1/admin/...`. Add the intended login email to the
comma-separated `MEMORYPAL_ADMIN_EMAILS` value in the ignored root `.env`, and
restart the Gateway. An authenticated account without this grant receives
`403 Forbidden`.

`run.cmd` starts the built console together with the other services. Local
health and prefix checks are available at:

```text
http://127.0.0.1:8082/
http://127.0.0.1:8082/api_memoripal/manage/
```

## Public audio URLs

When archive and TTS return audio URLs, start them with these environment
variables so browsers receive HTTPS URLs instead of private LAN paths:

```powershell
$env:MEMORYPAL_ARCHIVE_PUBLIC_URL='https://developark.duckdns.org/api_memoripal/archive'
$env:MEMORYPAL_TTS_PUBLIC_URL='https://developark.duckdns.org/api_memoripal/tts'
```

## LM Studio GPU offload

LM Studio runs on `192.168.2.41:1234`, outside the integrated application host. GPU offload is a model-load setting and cannot be changed by an OpenAI-compatible chat request.

Install the LM Studio CLI on the LLM server once:

```powershell
npx lmstudio install-cli
```

Then use the repository-root helper whenever selecting a persona model:

```powershell
load-llm.cmd default
load-llm.cmd companion
```

The helper unloads other models first for the GTX 1660 SUPER, then loads the selected model with `--gpu max`, an 8192-token context, and a one-hour TTL. To keep another loaded model intentionally, call `deploy/lmstudio/load-memorypal-model.ps1` with `-KeepOtherModels`.
