# AI Support Hub

Local development baseline for a Next.js web app, a FastAPI API, PostgreSQL with pgvector, Redis, and a Celery worker.

This repository does not include authentication, workspaces, document ingestion, RAG, embeddings, chat, Stripe, or Sentry.

Local Compose is development-only. Production deploy, Nginx, TLS, backup, and rollback are documented in [docs/production.md](docs/production.md).

## Prerequisites

Required:

- Git
- Docker
- Docker Compose

Optional host tools, only for faster lint/test loops outside containers:

- Node.js 22 and pnpm 10
- Python 3.12 and uv

## Setup

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Start every service:

   ```bash
   docker compose up --build
   ```

3. Open http://localhost:3000. The page loads API dependency diagnostics and shows loading, success, or failure.

PostgreSQL and Redis stay on the Compose network. They are not published to the host.

## Service URLs

| What | URL |
| --- | --- |
| Web diagnostics page | http://localhost:3000 |
| API liveness | http://localhost:8000/health |
| API PostgreSQL + Redis check | http://localhost:8000/health/dependencies |
| Swagger | http://localhost:8000/docs |
| OpenAPI | http://localhost:8000/openapi.json |

Worker round trip:

```bash
curl -s -X POST http://localhost:8000/diagnostics/worker
curl -s http://localhost:8000/diagnostics/worker/TASK_ID
```

Replace `TASK_ID` with the `task_id` from the POST response. Repeat the GET until `state` is `SUCCESS`. The HTTP request must return immediately; it does not wait for the worker.

## Folder ownership

- `apps/web` — Next.js App Router TypeScript app
- `apps/api` — shared FastAPI and Celery Python package, SQLAlchemy, Alembic
- `docker-compose.yml` — local source of truth for web, api, worker, postgres, and redis
- `compose.production.yml` — VPS topology with loopback web/API ports and no source mounts
- `docs/onboarding.md` — local diagnostic URLs and failure reading
- `docs/production.md` — production deploy, verification, backup, and rollback

Internal container URLs use Compose DNS names (`postgres`, `redis`, `api`). The browser cannot use those names. Compose sets `NEXT_PUBLIC_API_BASE_URL` from `API_PORT` and API CORS from `WEB_PORT`. For host-only `pnpm`/`uv` runs, keep `NEXT_PUBLIC_API_BASE_URL` aligned with `API_PORT` and `CORS_ORIGINS` aligned with `WEB_PORT`.

## Commands

| Task | Command |
| --- | --- |
| Start stack | `docker compose up --build` |
| Stop stack | `docker compose down` |
| Follow logs | `docker compose logs -f` |
| Backend tests | `cd apps/api && uv run pytest` |
| Frontend typecheck | `cd apps/web && pnpm typecheck` |
| Backend lint | `cd apps/api && uv run ruff check .` |
| Frontend lint | `cd apps/web && pnpm lint` |
| Backend format | `cd apps/api && uv run ruff format .` |
| Frontend format | `cd apps/web && pnpm format` |
| Backend format check | `cd apps/api && uv run ruff format --check .` |
| Frontend format check | `cd apps/web && pnpm format:check` |
| Apply migrations | `docker compose exec api alembic upgrade head` |

Migrations run inside the API container because PostgreSQL is not published to the host.

## Health semantics

- `GET /health` is process liveness only.
- `GET /health/dependencies` checks PostgreSQL and Redis. A failed dependency returns HTTP 503 with `postgres` and `redis` set to `ok` or `error`.
- `POST /diagnostics/worker` queues `test_worker` and returns `task_id`.
- `GET /diagnostics/worker/{task_id}` returns Celery `state` and `result`.

## Git workflow

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests run `.github/workflows/ci.yml`.

A repository administrator should require that CI workflow and a review before merging to `main`. GitHub branch protection is a manual repository setting.

## Production

Do not run `docker-compose.yml` on the public VPS. That file mounts source, uses `pnpm dev` / Uvicorn `--reload`, and publishes web/API on all interfaces.

Production uses `compose.production.yml` behind host Nginx. Web and API bind to `127.0.0.1` only. PostgreSQL and Redis stay on the Docker network.

Operator runbook: [docs/production.md](docs/production.md).

## Troubleshooting

- Copy `.env.example` to `.env` before `docker compose up`.
- If you change `WEB_PORT` or `API_PORT`, Compose updates CORS and the browser API URL. Also update `CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` in `.env` if you run the API or web on the host.
- If the web page fails to reach the API, confirm the browser is calling `http://localhost:<API_PORT>`. Do not set the API URL to `http://api:8000`.
- If dependencies return 503, wait until `postgres` and `redis` are healthy: `docker compose ps`.
- If the worker stays `PENDING`, confirm the `worker` service is running and Redis is healthy.
- PostgreSQL image is `pgvector/pgvector:pg16` so the later vector extension is available. This baseline does not create RAG tables.
- More diagnosis steps: [docs/onboarding.md](docs/onboarding.md).
