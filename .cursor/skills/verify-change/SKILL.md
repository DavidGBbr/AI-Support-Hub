---
name: verify-change
description: Use when finishing a code change, before claiming done, opening a PR, or saying tests passed; when choosing lint, typecheck, pytest, Ruff, Alembic, or Compose commands; after edits to apps/web, apps/api, Alembic, docker-compose, env files, CI, or operational docs; or when told CI will catch it, tests feel fine, skip formatters, or unit tests are enough.
---

# verify-change

Map the real diff to existing commands. User hurry is not a skip list.

## 1. Map files → checks

From `git diff` (not from memory):

| Touched | Run (from that app / repo root) |
| --- | --- |
| `apps/web/**` | `pnpm lint`, `pnpm typecheck`, `pnpm format:check` in `apps/web` |
| `apps/api/**` Python (not only a revision file) | `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` in `apps/api` |
| Alembic / models / schema | Also apply or report `docker compose exec api alembic upgrade head` |
| Compose, Dockerfiles, `.env.example` | Read the diff; `docker compose config` and/or start only if those files changed. Pytest does not verify Compose. |
| README / `docs/` / CONTRIBUTING command or URL changes | Re-read the page. Do not run the VPS runbook unless ops files changed. |

Do not run unrelated suites to look busy. Do not skip a mapped check because CI will catch it, tests felt fine this morning, or the user asked to hurry.

## 2. Inspect the diff

Before done, scan for: scope creep, duplication, new dependencies, new env vars without `.env.example`, migrations without an upgrade note, missing docs when behavior / contract / commands / ops changed.

## 3. Report

List each command, cwd, exit status. List skipped checks with why (stack not running, tool missing). Never invent passing output. Never claim done with a red suite. A check not executed is "not run," not green.

If a mapped command cannot run, still do not declare the change verified.
