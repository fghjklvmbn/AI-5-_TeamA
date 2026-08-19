# MemoryPal scale data stack

This production-shaped local profile starts PostgreSQL 16 with pgvector and a
persistent Redis instance. The Gateway now has both SQLite and PostgreSQL
adapters: SQLite remains the zero-infrastructure development fallback, while
`MEMORYPAL_DATABASE_URL` selects the pooled PostgreSQL adapter. Redis mode moves
long portrait work into a separately managed worker process.

## What is included

- PostgreSQL + `vector`, `citext`, and `pgcrypto`
- Separate `memorypal_gateway`, `memorypal_archive`, `memorypal_vectors`,
  `memorypal_ops`, and `memorypal_meta` schemas
- Dimension-specific 768- and 384-value vector tables with HNSW cosine indexes
- Redis AOF persistence, a named ACL user stored as a password hash, disabled
  default user, health check, and `noeviction` policy suitable for job state
- Versioned SQL runner and migration ledger
- Operational state, metadata-only audit events, and transactional outbox tables
- Redis Stream task/event delivery with leases, retry, deduplication, and a GPU lock
- Admin-ready transaction and operation aggregate views without conversation bodies

The Compose file binds database ports to `127.0.0.1`, so they are available to
Windows host processes without being exposed to the LAN. Production services
should communicate on a private container network and remove host port mappings.

## Windows local setup

Requirements: Docker Desktop with the Compose v2 command and Linux containers.
Run the following from the repository root in PowerShell:

```powershell
Copy-Item .env.scale.example .env.scale
```

Generate two different URL-safe secrets. Run the snippet twice and place each
result in the matching password field in `.env.scale`:

```powershell
$bytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
-join ($bytes | ForEach-Object { $_.ToString('x2') })
```

Fill both intentionally blank `PASSWORD` values and replace every
`__URL_ENCODED...__` placeholder. With the hex secrets generated above, the
same value is already URL-safe. Compose fails closed while either password is
blank. The real `.env.scale` is ignored by Git; the example contains no working
credentials.

Start the data services and wait for them to become healthy:

```powershell
docker compose --env-file .env.scale -f docker-compose.scale.yml up -d postgres redis
docker compose --env-file .env.scale -f docker-compose.scale.yml ps
```

Apply pending migrations. The one-shot runner waits for PostgreSQL health and
records each applied filename plus its SHA-256 checksum in
`memorypal_meta.schema_migrations`. Each migration and its ledger insert commit
in one transaction; changing an applied file causes the runner to fail closed.
The same job applies Gateway, Archive, and scale migrations with distinct
version prefixes:

Archive migration filenames use consecutive integer prefixes beginning at
`1` (for example, `6_add_retention_index.sql`). Both the Python runner and the
Compose job sort those prefixes numerically and reject gaps, duplicates, zero
prefixes, and malformed names before applying any Archive migration.
Applied migration files are immutable and must never be renamed or deleted;
the runners reject both checksum drift and ledger entries with no source file
before running pending DDL.

```powershell
docker compose --env-file .env.scale -f docker-compose.scale.yml --profile tools run --rm migrate
```

Local endpoints are PostgreSQL `127.0.0.1:5433` and Redis `127.0.0.1:6380` by
default. Change the host-side ports in `.env.scale` if they are already in use.
Port 5433 deliberately avoids the common Archive PostgreSQL port 5432.

Stop containers while preserving data:

```powershell
docker compose --env-file .env.scale -f docker-compose.scale.yml down
```

Named volumes retain PostgreSQL and Redis data. `down --volumes` permanently
deletes both stores and should only be used for an intentional local reset.
Bootstrap scripts under `postgres/init` run only when PostgreSQL creates an
empty data volume; normal schema changes must be new migration files.

## Gateway migration and cutover

The runtime schema is installed only by the migration command above. Gateway
startup validates the required relations and migration checksums but never runs
DDL. Before enabling `MEMORYPAL_DATABASE_URL`, start the current Gateway once in
SQLite mode so its local compatibility migrations create every required source
table, then stop it. Keep the Gateway stopped during the one-time copy:

```powershell
.\stop.cmd
Copy-Item backend\gateway\data\memorypal.db backend\gateway\data\memorypal.pre-postgres.db
```

Set `MEMORYPAL_DATABASE_URL` temporarily in the current terminal (or put the
scale application variables in the root `.env`) and run the idempotent copier:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py `
  --sqlite backend\gateway\data\memorypal.db
```

The tool never modifies SQLite, copies in bounded batches, verifies every
`ON CONFLICT` row against the source, and requires exact per-table target row
counts. Use a freshly migrated empty target schema; unrelated pre-existing rows
fail verification instead of being silently accepted. After it succeeds, put
`MEMORYPAL_DATABASE_URL`, pool/schema values,
`MEMORYPAL_REDIS_URL`, and `MEMORYPAL_TASK_QUEUE_MODE=redis` in the root `.env`.
`run.cmd` then starts the Gateway and the separate portrait worker; `stop.cmd`
stops both. Keep the SQLite copy until login, chat, memory, attachment, portrait,
and restart smoke tests have passed. Do not attempt a live dual-write cutover
without a dedicated change-data-capture design.

The Archive service remains in its isolated `memorypal_archive` schema. Archive
startup performs read-only schema and checksum verification; it never creates
or alters tables. Apply the migration job before starting Archive whenever an
Archive SQL migration is added.

## Gateway-to-Archive service credential

The bundled single-host `run.cmd` workflow creates a cryptographically random
token in the ignored `.runtime/secrets/archive-service-token` file when neither the
process environment nor the root `.env` supplies
`MEMORYPAL_ARCHIVE_SERVICE_TOKEN`. Later bundled starts reuse that local file
and pass the same process-scoped value to Gateway and Archive.

Do not copy or synchronize that runtime file for a scaled deployment. When
Gateway and Archive run independently, on different hosts, or with multiple
replicas, generate one URL-safe secret from at least 48 random bytes, store it
in the deployment secret manager, and inject the exact same non-empty
`MEMORYPAL_ARCHIVE_SERVICE_TOKEN` into every Gateway and Archive instance.
Rotate it as a coordinated credential change so the two services never run
with different values.

The remote embedding model currently yields 768 values while the deterministic
local fallback yields 384. They are stored and indexed in separate tables.
Never calculate similarity across those tables or across incompatible models;
filter by `model_id` within one vector space. A future model change should add a
new dimension-specific table or re-embed data through a controlled migration.

## Event data and retention rules

`user_transaction_events` and `event_outbox` are metadata streams, not content
stores. Never put prompts, user/assistant messages, summaries, document bodies,
audio transcripts, passwords, access tokens, or raw personal fields in their
JSON metadata. Store only allowlisted identifiers, event categories, result
codes, durations, model/version labels, and non-sensitive counters. Consumers
must fetch protected content from its authoritative table after authorization.

Initial B-tree indexes support user/type queries and BRIN indexes support date
range scans with low write amplification. When event volume reaches sustained
multi-million-row ranges, migrate `user_transaction_events` by monthly
`occurred_at` partitions and outbox history by monthly `created_at`
partitions. Test the conversion on a restored backup, create future partitions
ahead of time, retain a default partition during rollout, and expire data by
detaching partitions rather than issuing large deletes.

## Production hardening checklist

- Store credentials in a secret manager; never deploy `.env.scale`.
- Use separate owner, migration, and least-privilege runtime roles.
- Require TLS for PostgreSQL and Redis connections outside a private host.
- Put PgBouncer or equivalent pooling in front of PostgreSQL application traffic.
- Configure backups, point-in-time recovery, restore drills, replicas, and alerts.
- Size Docker/host memory before changing PostgreSQL buffers or Redis limits.
- Keep Redis `noeviction` for queues and alert before memory exhaustion; use
  separate Redis instances/policies for disposable caches.
- Restrict the Redis ACL from `+@all` to the exact commands required by the
  selected queue library before production rollout.
- Run forward-only migrations in CI/CD once per release and monitor lock time.

The concrete state model and future administrator read contracts are documented
in [STATE_MANAGEMENT.md](STATE_MANAGEMENT.md).
