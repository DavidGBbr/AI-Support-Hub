# Onboarding diagnostics

Use this note when Compose is up and something still looks wrong. The README remains the first-time setup source.

## Expected URLs

- Web diagnostics: http://localhost:3000
- API liveness: http://localhost:8000/health
- API dependencies: http://localhost:8000/health/dependencies
- Worker dispatch: `POST http://localhost:8000/diagnostics/worker`
- Worker status: `GET http://localhost:8000/diagnostics/worker/{task_id}`
- Plan catalog: http://localhost:8000/v1/plans
- Subscription of a workspace: `GET http://localhost:8000/v1/workspaces/{workspace_id}/billing/subscription`
- Stripe webhook: `POST http://localhost:8000/webhooks/stripe`
- Swagger: http://localhost:8000/docs
- OpenAPI: http://localhost:8000/openapi.json

## How to read the responses

1. `/health` must return `{"status":"ok"}` while the API process is up, even if PostgreSQL or Redis is down.
2. `/health/dependencies` returns `postgres` and `redis` as `ok` or `error`. Any `error` is HTTP 503.
3. `POST /diagnostics/worker` returns a `task_id` immediately. It must not wait for the worker.
4. Poll the worker status URL until `state` is `SUCCESS` and `result.task` is `test_worker`.
5. `/v1/plans` is public. The billing routes of a workspace need the bearer token of `BILLING_ADMIN_TOKEN` and answer 401 without it, 404 for a workspace the token does not own, and 503 when no token is configured.

## Stripe in local development

- The API only accepts Stripe test keys. It refuses to start with a live key, so a misconfigured environment can never charge a customer.
- `STRIPE_PRO_PRICE_ID` is the recurring price of the Pro plan. `STRIPE_PRICE_ID` is still accepted as a fallback.
- The webhook secret comes from `stripe listen --forward-to localhost:8000/webhooks/stripe`. The endpoint answers 400 for a payload that is not signed with that secret.
- The webhook stores the event and hands it to the worker. The subscription state changes a moment later, not in the response of the webhook.
- A local database that already ran an older version of the `0002_subscriptions` migration has to be reset: `docker compose down -v && docker compose up -d && docker compose run --rm api alembic upgrade head`.

## Common failures

- Browser cannot reach the API: `NEXT_PUBLIC_API_BASE_URL` must be `http://localhost:8000` on the host, not `http://api:8000`.
- Dependencies 503 with postgres error: wait for `postgres` healthy, then rerun. Confirm the API uses host `postgres`, not `localhost`.
- Worker stays `PENDING`: the `worker` container is not running or cannot reach Redis at `redis:6379`.
- The webhook answers 503: the worker cannot be reached, so the event was stored but not queued. The next delivery of the same event queues it again.

## What this baseline does not include

Authentication, workspaces, document ingestion, RAG, embeddings, chat, Sentry, Nginx/SSL, and VPS deployment are out of scope.
