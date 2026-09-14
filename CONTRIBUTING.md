# Contributing

## Prerequisites

Docker and Docker Compose are required. Node.js 22 / pnpm and Python 3.12 / uv are optional host tools for faster lint and test loops.

## Branch and pull request workflow

1. Create a branch from `main`.
2. Keep the change inside the documented scope. This repository is a small monorepo: `apps/web` is the Next.js app, `apps/api` is the shared FastAPI and Celery package.
3. Open a pull request with the template. Fill in problem, scope, verification, migration/configuration, and documentation.
4. Wait for the `CI` GitHub Actions workflow to finish. It runs web install/lint/typecheck and API uv sync, Ruff, and Pytest.

## Local checks before you push

From the repository root, after `cp .env.example .env`:

```bash
docker compose up --build -d
( cd apps/api && uv run pytest )
( cd apps/api && uv run ruff check . )
( cd apps/api && uv run ruff format --check . )
( cd apps/web && pnpm lint )
( cd apps/web && pnpm typecheck )
( cd apps/web && pnpm format:check )
docker compose exec api alembic upgrade head
```

## Branch protection

A repository administrator should require the `CI` workflow and at least one review before merging to `main`. This is a GitHub repository setting; the workflow cannot enable it by itself.

## Out of scope

Do not add product authentication, workspaces, document ingestion, RAG, embeddings, chat, Stripe, Sentry, Nginx/SSL, or VPS deployment on this foundation card.
