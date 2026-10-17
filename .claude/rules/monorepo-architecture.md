# Monorepo architecture

This is a two-app Compose monorepo. Keep ownership and dependency direction as they are.

## Ownership

- `apps/web` — Next.js UI. Browser talks to the API via `NEXT_PUBLIC_API_BASE_URL`.
- `apps/api` — FastAPI HTTP surface, Celery tasks, SQLAlchemy models, Alembic. Shared package for api and worker.
- `docker-compose.yml` — local development runtime: web, api, worker, postgres, redis.
- `compose.production.yml` — production runtime behind Nginx, with web and API bound to loopback and dependencies kept private.
- `docs/` — human runbooks. Not a place for application code.
- `.github/workflows/` — CI. Do not add product behavior here.

## Direction

- Web → HTTP → API. Never web → Python imports, and never API → Next.js modules.
- API → postgres / redis through settings. PostgreSQL and Redis stay on the Compose network.
- Worker → same `apps/api` package and Redis broker. Do not create a second worker app.
- Config and secrets enter through env / `app.core.config`. Document local variables in `.env.example` and production variables in `.env.production.example`; never commit actual secrets.

## Where code goes

- HTTP: `apps/api/app/api/`
- Orchestration: `apps/api/app/services/`
- Persistence: `apps/api/app/repositories/` (only when there is a real query or write)
- Tasks: `apps/api/app/tasks/`
- UI: `apps/web/app/`
- Local infrastructure: `docker-compose.yml`.
- Production infrastructure: `compose.production.yml` and `docs/production.md`. Follow the applicable task and runbook; do not assume a local-only change applies in production.

Do not add a third app, a shared TypeScript/Python package, or a new Compose service unless the approved plan requires it.
