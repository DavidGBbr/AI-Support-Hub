# Add document ingestion, transactional outbox, and pgvector search

## Problem

The support API needs searchable PDF/TXT/Markdown knowledge-base content. Publishing ingestion directly after saving an upload can strand a document if the API exits between commit and Celery publication.

## Scope

- Persist the document and a unique outbox intent atomically; upload returns HTTP 202 without contacting the broker.
- Add migration 0003 with retry scheduling, publication/completion timestamps, due-event index, and recovery of legacy pending/dispatch-failed uploads.
- Add an independent PostgreSQL-polling dispatcher with SKIP LOCKED, durable backoff, bounded broker connection time, and recovery after a crash before/after publication.
- Deliver at least once with a stable event ID. Ingestion locks/deduplicates that event and commits READY, chunks, and processed_at together. Use late Celery acknowledgement and worker-loss rejection.
- Include the outbox service and persistent Redis AOF storage in development and production Compose.
- Preserve extraction/embedding/search behavior, safe PDF errors, Celery registration, and the frontend ESLint/pnpm fixes. Align the existing HNSW index with SQLAlchemy metadata.

## Verification

- [x] Full backend suite: 37 passed, zero skipped; one Starlette/AnyIO deprecation warning.
- [x] Eleven outbox cases cover atomic upload/rollback, restart recovery, broker backoff, crashes before/after publication, competing dispatchers, concurrent duplicate consumers, atomic completion rollback, worker crash/redelivery, and cold publisher initialization.
- [x] PostgreSQL 16 / pgvector 0.8.7 integration tests and migration 0003 applied to the isolated test database.
- [x] Separate empty-database upgrade, legacy backfill assertions, downgrade preserving documents, re-upgrade, and Alembic metadata comparison.
- [x] uv lock --check, Ruff lint/format checks, and dispatcher CLI --once.
- [x] Frontend frozen-lockfile install, lint, TypeScript, and formatting with pnpm 10.11.1 (unchanged frontend since validation).
- [x] Development and production Compose configurations validate; production validation uses example interpolation with service env-file resolution disabled.
- [x] Backend images rebuilt and deployed locally; migration 0003 applied to the existing database; real API/Redis/Celery/outbox ingestion and search passed with a temporary deterministic embeddings HTTP stub.
- [x] Real dispatcher SIGKILL after Redis publish and before database commit: restart caused duplicate delivery with the same event ID, one embedding request, one chunk, and READY. Fault injection and synthetic records/provider were removed; normal API/worker/outbox remain running.
- [ ] Web image rebuild and a real OpenAI request with a configured API key.
- [x] Changes ported onto main in an actual Git checkout; staged diff reviewed and checked for whitespace/secrets.
- [ ] Remote CI and review approvals confirmed on the pull request.

## Migration / configuration

Quiesce uploads and drain legacy workers before rollout. Build API/worker/outbox, start PostgreSQL/Redis, and apply alembic upgrade head before starting the new outbox/API/worker. Keep document storage shared and configure OPENAI_API_KEY for real embeddings. Preserve Redis and PostgreSQL volumes. No additional application environment variable is required.

Migration 0003 backfills PENDING documents and FAILED uploads with the old safe queue-failure reason; other statuses are not automatically replayed. Downgrade removes outbox history while retaining documents/chunks and requires stopping/draining dispatch first. Downgrade 0002 destroys ingestion data.

## Documentation and limitations

Architecture and validation notes document the delivery contract, rollout, monitoring, and rollback. Delivery is at least once; completion in PostgreSQL is idempotent per event. Provider calls can repeat after an interrupted attempt. Redis redelivery after worker loss may wait for its visibility timeout. The dispatcher must stay running and the referenced shared files must remain available. A crash before the upload transaction commits can leave an unreferenced file.

The validated changes were transferred into a separate Git checkout on feat/document-ingestion-outbox, based on main. Remote CI and review results are tracked on the pull request.

Local deployment evidence and cleanup results: [outbox-local-e2e-report.json](outbox-local-e2e-report.json).
