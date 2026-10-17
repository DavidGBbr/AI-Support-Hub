#!/bin/sh
# Stop. Lists the checks that match the changed files. Never blocks.
# It does not run them: containers may be down. The list mirrors CONTRIBUTING.md.
root=${CLAUDE_PROJECT_DIR:-$(pwd)}
cd "$root" 2>/dev/null || exit 0
changed=$(git status --porcelain 2>/dev/null | sed 's/^...//')
[ -n "$changed" ] || exit 0

has() { printf '%s\n' "$changed" | grep -Eq "$1"; }
out=""
add() { out="$out
  $1"; }

has '^apps/web/' && add "web:       (cd apps/web && pnpm lint && pnpm typecheck && pnpm format:check)"
has '^apps/api/' && add "api:       (cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run pytest)"
has '^apps/api/(alembic/|app/models)' && add "migration: docker compose exec api alembic upgrade head"
has '^(docker-compose|compose\.production|\.env\.|.*Dockerfile)' && add "compose:   docker compose config   (pytest does not cover Compose or env files)"
has '^(README|CONTRIBUTING|docs/)' && add "docs:      reread changed commands and URLs"
[ -n "$out" ] || exit 0

echo "verify-on-stop: files changed. Checks that match, not run by this hook:$out" >&2
exit 1
