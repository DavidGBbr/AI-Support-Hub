## Problem

<!-- What is broken or missing? -->

## Scope

<!-- What files or services does this change? -->

## Verification

- [ ] `docker compose up --build` still starts web, api, worker, postgres, and redis
- [ ] Relevant pnpm / uv / docker compose checks ran locally
- [ ] New or updated tests cover the change

## Migration / configuration

- [ ] No migration required, or `docker compose exec api alembic upgrade head` was run
- [ ] `.env.example` was updated if a new variable is required

## Documentation

- [ ] README or `docs/onboarding.md` updated if URLs, commands, or troubleshooting changed
