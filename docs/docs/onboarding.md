# Onboarding diagnostics

Use this note when Compose is up and something still looks wrong. The README remains the first-time setup source.

## Expected URLs

- Web diagnostics: http://localhost:3000
- API liveness: http://localhost:8000/health
- API dependencies: http://localhost:8000/health/dependencies
- Worker dispatch: `POST http://localhost:8000/diagnostics/worker`
- Worker status: `GET http://localhost:8000/diagnostics/worker/{task_id}`
- Swagger: http://localhost:8000/docs
- OpenAPI: http://localhost:8000/openapi.json

## How to read the responses

1. `/health` must return `{"status":"ok"}` while the API process is up, even if PostgreSQL or Redis is down.
2. `/health/dependencies` returns `postgres` and `redis` as `ok` or `error`. Any `error` is HTTP 503.
3. `POST /diagnostics/worker` returns a `task_id` immediately. It must not wait for the worker.
4. Poll the worker status URL until `state` is `SUCCESS` and `result.task` is `test_worker`.

## Common failures

- Browser cannot reach the API: `NEXT_PUBLIC_API_BASE_URL` must be `http://localhost:8000` on the host, not `http://api:8000`.
- Dependencies 503 with postgres error: wait for `postgres` healthy, then rerun. Confirm the API uses host `postgres`, not `localhost`.
- Worker stays `PENDING`: the `worker` container is not running or cannot reach Redis at `redis:6379`.

## What this baseline does not include

Authentication, workspaces, document ingestion, RAG, embeddings, chat, Stripe, Sentry, Nginx/SSL, and VPS deployment are out of scope.
