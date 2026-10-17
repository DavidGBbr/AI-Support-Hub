#!/bin/sh
# PreToolUse (Bash). Blocks irreversible git commands. Exit 2 blocks the call.
payload=$(cat | tr '\134' '/')

case "$payload" in
  *git*) ;;
  *) exit 0 ;;
esac

block() {
  echo "guard-git: $1" >&2
  exit 2
}

has() { printf '%s' "$payload" | grep -Eq -e "$1"; }

has 'git[[:space:]]+push[^;&|]*(--force|[[:space:]]-f)([[:space:]"]|$)' &&
  block "force push is blocked. Use --force-with-lease on your own feature branch from a terminal if you really need it."
has 'git[[:space:]]+push[^;&|]*[[:space:]:/](main|master)([[:space:]"]|$)' &&
  block "do not push to main. Push your branch and open a pull request."
has 'git[[:space:]]+reset[[:space:]]+--hard' &&
  block "git reset --hard discards local work. Commit or run git stash push -u -m <tag> first, then reset from a terminal yourself."
has '--no-verify' &&
  block "--no-verify skips hooks. Fix the failing hook instead."

# A bare push while standing on main.
if has 'git[[:space:]]+push'; then
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  case "$branch" in
    main|master) block "you are on $branch. Create a branch first: git switch -c <name>." ;;
  esac
fi
exit 0
