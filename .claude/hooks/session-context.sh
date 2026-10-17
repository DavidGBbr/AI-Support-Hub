#!/bin/sh
# SessionStart. Prints a short status block that Claude receives as context.
root=${CLAUDE_PROJECT_DIR:-$(pwd)}
cd "$root" 2>/dev/null || exit 0

echo "AI Support Hub session context"
echo "branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
echo "uncommitted files: $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
[ -f .env ] && echo ".env: present" || echo ".env: missing (cp .env.example .env)"

if command -v docker >/dev/null 2>&1; then
  if command -v timeout >/dev/null 2>&1; then
    running=$(timeout 5 docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' ')
  else
    running=$(docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' ')
  fi
  echo "compose services running: ${running:-0}"
else
  echo "docker: not found"
fi
echo "start with AGENTS.md; checks are listed in CONTRIBUTING.md"
exit 0
