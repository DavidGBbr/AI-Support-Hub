# Agent instructions — AI Support Hub

Provider-agnostic. Read this file first. Cursor rules add area context. Skills run only when their triggers match.

## Product and map

MVP: B2B customer-support SaaS with RAG. Auth, workspaces, knowledge bases, async document processing, cited chat, Stripe, observability, and deploy/rollback. Deadline: 2026-10-21.

This checkout is a small local baseline. Product features above are not in the tree yet. Do not add them unless the approved task says so.

| Area | Owns |
| --- | --- |
| `apps/web` | Next.js App Router TypeScript UI. Talks to the API over HTTP only. |
| `apps/api` | Shared FastAPI + Celery package: routers, services, repositories, SQLAlchemy, Alembic. |
| `docker-compose.yml` | Local web, api, worker, postgres, redis. |
| `docs/` | Onboarding and operator docs. |

Commands, URLs, and runbooks live in `README.md`, `CONTRIBUTING.md`, and `docs/onboarding.md`. Do not copy those runbooks here.

## Instruction order

1. Workspace `AGENT.md` when this repo sits inside davidspace.
2. This file.
3. Cursor rules that match the files you are editing.
4. A project skill when its trigger matches.
5. The approved vault `tasks/<ID>/plan.md` for ticket work.

A more specific source wins on that topic. Do not fork a second copy of the same rule.

## KISS and YAGNI

Ship the smallest complete change that meets the current acceptance criteria.

- Reuse the existing router / service / repository / page / task pattern before adding a layer.
- Do not add generic APIs, base classes, registries, result wrappers, feature flags, fallbacks, new dependencies, or compatibility shims for a requirement that is not in the current plan.
- New complexity needs a current, named need (two concrete call sites, or the plan names the layer). "We will need this later" is not a need.
- If the smallest complete change still requires an architecture or plan change, stop and say so.

## Boundaries

- Web consumes HTTP contracts. It does not import Python modules or share a database session with the API.
- FastAPI routers stay thin: parse, call a service, return. No SQL or Celery internals in the router.
- Services own business rules and orchestration.
- Repositories own persistence. Add a repository when there is a real query or write, not as a default wrapper.
- Celery is for async or long-running work. HTTP handlers must return without waiting on the worker.
- Settings and secrets come from `app.core.config` / env. Do not hardcode secrets.
- Schema changes go through Alembic. HTTP contract changes are explicit (OpenAPI, tests, callers).

## Change bar

- One focused diff. Tests proportional to risk.
- Update docs when behavior, contracts, commands, or operations change.
- If the approved plan cannot be followed, stop. Do not silently expand scope.

## Skills

- `scope-guard` — use when a change starts growing past the plan, or when asked to future-proof, generalize, or add layers that the current criteria do not require.
- `verify-change` — required after code changes, before claiming done. Maps the real diff to the existing web / API / Alembic / Compose / docs checks.
