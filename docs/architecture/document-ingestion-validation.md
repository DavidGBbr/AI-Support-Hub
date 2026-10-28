# Document ingestion validation — 2026-10-28

## Verified locally

- Python 3.12.14; pytest 9.1.1; PostgreSQL 16 / pgvector 0.8.7.
- Full suite: 37 passed, zero skipped, one Starlette/AnyIO deprecation warning.
- Eleven outbox regression cases plus four existing vector-search/reprocessing integration tests.
- Atomic upload and rollback when the intent cannot be inserted.
- Restart after document/intent commit; publication failures remain eligible with safe errors and persistent backoff.
- Crash before publish and after broker acceptance; retry uses the same event and duplicate consumption does not repeat successful processing.
- Competing publishers skip locked rows; concurrent consumers embed once per completed event.
- Completion marker, READY, and chunks commit or roll back together; worker interruption and redelivery recover.
- Publisher starts in a fresh interpreter without circular task imports.
- Alembic upgrade through 0003 on the main test database.
- Separate scratch database: clean upgrade to 0002, seed pending/dispatch-failed/processing-failed/ready documents, upgrade to 0003 and assert backfill, check metadata, downgrade preserving documents, re-upgrade and check again.
- uv lock --check, Ruff lint/format checks, and dispatcher --once.
- Both Compose configurations validate, including outbox and durable Redis. Production interpolation uses .env.production.example and --no-env-resolution; no production secrets file was created.
- Frontend frozen-lockfile install, lint, type generation/TypeScript, and Prettier passed with declared pnpm 10.11.1. No frontend code changed for the outbox.

## Reproduce backend validation (PowerShell)

The dedicated container aisupport-pgvector-tests publishes only 127.0.0.1:54329. Credentials below are test-only.

```powershell
docker start aisupport-pgvector-tests
cd apps/api
$env:POSTGRES_HOST = '127.0.0.1'
$env:POSTGRES_PORT = '54329'
$env:POSTGRES_USER = 'test'
$env:POSTGRES_PASSWORD = 'test'
$env:POSTGRES_DB = 'aisupport_test'
$env:REDIS_HOST = '127.0.0.1'
uv lock --check
uv run alembic upgrade head
uv run alembic check
uv run ruff check .
uv run ruff format --check .
uv run pytest -v -rs
uv run python -m app.services.outbox --once
```

Outbox tests require the migrated integration database and fail rather than silently passing when it is unavailable. Publication is mocked for deterministic failure/crash scenarios, while transactions and locks run against real PostgreSQL. The deterministic regression suite uses fake providers. A separate real Redis/Celery integration exercise is recorded below; OpenAI itself was replaced by a temporary HTTP stub because no API key was configured.

## Reproduce frontend checks

From apps/web:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm format:check
```

ESLint resolves plugins relative to eslint-config-next. pnpm-workspace.yaml explicitly excludes the optional unrs-resolver install script.

## Remaining release checks

The validated source has been transferred into a separate Git checkout on feat/document-ingestion-outbox and its staged diff reviewed. Verify remote CI/review, rebuild the web image, and smoke-test a real OpenAI ingestion/search before production release. Apply the migration and rollout precautions in document-ingestion.md. No production service was deployed during local validation.

## Local deployed end-to-end validation

Migration 0003_document_outbox was applied to the existing local PostgreSQL database, preserving its volume. API, worker, and outbox images were rebuilt from the reviewed source. Redis uses its persistent named volume with appendonly=yes and appendfsync=always. API and worker were recreated with the current source mount rather than the previous project copy.

- Normal path: HTTP upload returned 202; the independent dispatcher published to real Redis; the real Celery worker produced READY, one chunk, and processed_at; HTTP semantic search returned the document.
- Recovery path: stop dispatcher/worker, upload a document, then block only its publication timestamp update using a temporary PostgreSQL trigger. Once the real Redis message existed, SIGKILL the real dispatcher before its commit. Confirm published_at remained null and attempts rolled back to zero. Remove the trigger and restart the dispatcher; two queued deliveries carried the same event ID. Start the worker; verify READY, one chunk, and only one additional embedding request.
- Cleanup: remove the test workspace/documents/files, fault trigger/function, and temporary embedding service. Restore API/worker without the synthetic endpoint/key and restore the dispatcher's unless-stopped restart policy.
- Final state: migration at head, API and PostgreSQL/Redis dependency health OK, Celery inspect ping returned pong, and the real outbox dispatcher is running.

The temporary HTTP service emulated only the external embeddings API; production API, dispatcher, Celery worker, Redis, and PostgreSQL code paths were used. No real OpenAI request was made. A configured OpenAI key is still required for normal document embeddings.

Detailed evidence: [outbox-local-e2e-report.json](outbox-local-e2e-report.json). The document IDs in that report refer to synthetic records removed after validation.
