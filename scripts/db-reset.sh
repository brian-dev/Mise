#!/usr/bin/env bash
#
# Reset the local dev database to a pristine state: drop all data and re-apply
# migrations + seed. Use after manual/exploratory testing that committed rows
# (curl, scripts/seed_demo.py) to keep the dev DB uncluttered (see CLAUDE.md →
# Testing). Automated tests roll back and never need this.
#
#   ./scripts/db-reset.sh        (or: pnpm db:reset)
#
set -euo pipefail

if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
export PATH="$HOME/.local/share/supabase:$PATH"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v supabase >/dev/null 2>&1 || {
  echo "✗ supabase CLI not found — see docs/CHECKPOINT.md"; exit 1
}

echo "▶ Resetting local database (migrations + seed)…"
supabase db reset
echo "✓ Dev database reset to a fresh seeded state."
