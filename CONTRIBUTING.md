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

## Claude Code hooks

If you use Claude Code, `.claude/settings.json` registers five small hooks. They are POSIX `sh` scripts in `.claude/hooks/` and need no tool beyond Git and `grep`; the formatter and checks are skipped when pnpm or uv are not installed.

- `guard-secrets` blocks writing private keys or tokens and staging `.env`, `.env.production`, `.ssh/` or `backups/`.
- `guard-git` blocks force push, pushing to `main`, `git reset --hard`, and `--no-verify`.
- `format-on-edit` runs Prettier on edited web files and Ruff on edited API files.
- `verify-on-stop` lists the checks above that match your changed files. It does not run them.
- `session-context` prints the branch, `.env` and Compose state at session start.

To turn all of them off for yourself, set `"disableAllHooks": true` in `.claude/settings.local.json`, which is git-ignored.

## Branch protection

A repository administrator should require the `CI` workflow and at least one review before merging to `main`. This is a GitHub repository setting; the workflow cannot enable it by itself.

## Out of scope

Do not add product authentication, workspaces, document ingestion, RAG, embeddings, chat, Stripe, or Sentry on a local-development change. Production Compose, Nginx, and VPS steps belong in `compose.production.yml` and `docs/production.md`.
