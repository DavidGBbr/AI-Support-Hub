#!/bin/sh
# PreToolUse (Edit|Write|Bash). Blocks secrets from entering tracked files or commits.
# Needs only POSIX sh and grep. Exit 2 blocks the tool call.
payload=$(cat | tr '\134' '/')

block() {
  echo "guard-secrets: $1" >&2
  exit 2
}

# Private keys and well-known token shapes in any written content.
if printf '%s' "$payload" | grep -Eq 'BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}'; then
  block "the content looks like a private key or access token. Keep it in the git-ignored .env or .env.production on the host, and use REPLACE_WITH_* placeholders in tracked files."
fi

# Writes into server-only key folders.
if printf '%s' "$payload" | grep -Eq '"file_path"[[:space:]]*:[[:space:]]*"[^"]*/\.ssh/'; then
  block "files under .ssh/ hold host keys and are git-ignored. Do not create them from the repository."
fi

# Staging git-ignored secret paths, with or without -f.
if printf '%s' "$payload" | grep -Eq 'git[[:space:]]+add[^;&|]*([[:space:]/"]\.env(\.production)?([[:space:]"]|$)|\.ssh/|backups/)'; then
  block "this git add stages .env, .env.production, .ssh/ or backups/. These paths are git-ignored on purpose. Stage the *.example templates instead."
fi
exit 0
