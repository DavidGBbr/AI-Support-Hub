# AI Support Hub

Local development baseline for a Next.js web app, a FastAPI API, PostgreSQL with pgvector, Redis, and a Celery worker.

This repository does not include authentication, workspaces, document ingestion, RAG, embeddings, chat, Stripe, Sentry, Nginx/SSL, or VPS deployment.

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
- `docs/onboarding.md` — diagnostic URLs and failure reading

Internal container URLs use Compose DNS names (`postgres`, `redis`, `api`). The browser cannot use those names. `NEXT_PUBLIC_API_BASE_URL` must stay a host URL such as `http://localhost:8000`.

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

## Troubleshooting

- Copy `.env.example` to `.env` before `docker compose up`.
- If the web page fails to reach the API, confirm `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`. Do not set it to `http://api:8000`.
- If dependencies return 503, wait until `postgres` and `redis` are healthy: `docker compose ps`.
- If the worker stays `PENDING`, confirm the `worker` service is running and Redis is healthy.
- PostgreSQL image is `pgvector/pgvector:pg16` so the later vector extension is available. This baseline does not create RAG tables.
- More diagnosis steps: [docs/onboarding.md](docs/onboarding.md).
