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
blocked at the external Nginx boundary. Gateway-to-STT/TTS requests carry the
server-only `MEMORYPAL_MODEL_SERVICE_TOKEN`; CORS is retained as an additional
browser-origin check and is not treated as authentication. The LLM URL must be
its internal LAN URL, not `/api_memoripal/llm` on the public host.

Gateway, STT, and TTS must receive the exact same
`MEMORYPAL_MODEL_SERVICE_TOKEN`. In independent service deployments inject it
into all three process environments; `*_FILE` is a Gateway/install convenience
and the model servers intentionally accept only the direct process value.
Rotate the token by stopping all three services, updating the secret store, and
starting STT/TTS and Gateway together. Gateway's authenticated
`/v1/internal/ready` plus STT/TTS `/internal/ready` endpoints let the bundled
run script reject any stale process. Nginx returns 404 for the Gateway internal
readiness path, so it remains a LAN-only orchestration endpoint.

Gateway and Archive likewise share a separate
`MEMORYPAL_ARCHIVE_SERVICE_TOKEN`. Configure exactly one of that variable or
`MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE` in each process, using the same value on
both sides. The bundled scripts create profile-specific secret files and check
Archive's authenticated `/internal/ready` endpoint before exposing Gateway.

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

Run `install.cmd` to create ignored secrets under `.runtime/secrets`. For a
managed deployment, inject `MEMORYPAL_JWT_SECRET` and
`MEMORYPAL_MODEL_SERVICE_TOKEN` and `MEMORYPAL_ARCHIVE_SERVICE_TOKEN` from its
secret store instead. Do not put any value in `EXPO_PUBLIC_*` or `VITE_*`, and
keep the corresponding `*_FILE` setting empty whenever a direct value is
injected. Then start the gateway from `backend/gateway`:

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
npm run build:web:project3
```

The commands write `dist-main` and `dist-project3`, respectively, and each
directory contains a deployment manifest. `run.ps1` and `run-sidecar.ps1`
refuse to serve a directory whose manifest belongs to the other profile.

The current nginx `main` upstream is port 8081, which serves the production
export with `npm run serve:web`. Do not expose `expo start --web` below
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

The same profile split applies to the admin console (`dist-main` and
`dist-project3`). Main runs on port 8082; Project3 runs independently on 8084.
`run.cmd` starts the main console together with the other services. Local
health and prefix checks are available at:

```text
http://127.0.0.1:8082/
http://127.0.0.1:8082/api_memoripal/manage/
```

## Public audio URLs

Only browser-readable audio files are public. Archive APIs, STT, TTS synthesis,
LLM, and the test TTS UI are blocked by `nginx/memorypal.conf.example`. When
Archive and TTS return audio URLs, use these environment variables so browsers
receive HTTPS URLs instead of private LAN paths:

```powershell
$env:MEMORYPAL_ARCHIVE_PUBLIC_URL='https://developark.duckdns.org/api_memoripal/archive'
$env:MEMORYPAL_TTS_PUBLIC_URL='https://developark.duckdns.org/api_memoripal/tts'
```

If Archive voice samples live outside the repository's default
`private_voice_uploads`, `voice_uploads`, and TTS `reference_audio` directories,
set `MEMORYPAL_TTS_REFERENCE_AUDIO_ROOTS` on the TTS process to the allowlisted
directories separated by the operating system path separator. Remote reference
URLs and network shares are always rejected.

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
