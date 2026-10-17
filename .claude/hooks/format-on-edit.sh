#!/bin/sh
# PostToolUse (Edit|Write). Formats the edited file with the repo's own formatter.
# Skips quietly when the host tool or its dependencies are missing. Never blocks.
# Windows paths arrive JSON-escaped (C:\\Users\\...), so squeeze the doubled slashes.
payload=$(cat | tr '\134' '/')
file=$(printf '%s' "$payload" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 | tr -s '/')
[ -n "$file" ] || exit 0

root=${CLAUDE_PROJECT_DIR:-$(pwd)}
root=$(printf '%s' "$root" | tr '\134' '/' | tr -s '/')
rel=${file#"$root"/}
[ -f "$root/$rel" ] || exit 0

warn() { echo "format-on-edit: $1" >&2; exit 1; }

case "$rel" in
  apps/web/*.ts|apps/web/*.tsx|apps/web/*.js|apps/web/*.jsx|apps/web/*.mjs|apps/web/*.json|apps/web/*.css)
    command -v pnpm >/dev/null 2>&1 || exit 0
    [ -d "$root/apps/web/node_modules" ] || exit 0
    (cd "$root/apps/web" && pnpm exec prettier --write "${rel#apps/web/}" >/dev/null 2>&1) ||
      warn "prettier failed on $rel. Run: cd apps/web && pnpm format"
    ;;
  apps/api/*.py)
    command -v uv >/dev/null 2>&1 || exit 0
    [ -d "$root/apps/api/.venv" ] || exit 0
    (cd "$root/apps/api" && uv run --no-sync ruff format "${rel#apps/api/}" >/dev/null 2>&1) ||
      warn "ruff format failed on $rel. Run: cd apps/api && uv run ruff format ."
    ;;
esac
exit 0
