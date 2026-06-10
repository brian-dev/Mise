#!/usr/bin/env bash
#
# One command to run Mise locally: container runtime -> Supabase -> deps ->
# AI service (:8000) + web client (:3000). Ctrl-C stops the dev servers.
#
#   ./scripts/dev.sh        (or: pnpm dev)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Make the toolchains resolvable in a non-login shell.
if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
export PATH="$HOME/.local/share/supabase:$PATH"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "✗ missing tool: $1"
    echo "  First-time toolchain setup is documented in docs/CHECKPOINT.md."
    exit 1
  }
}
need colima
need supabase
need uv
need pnpm

echo "▶ Container runtime (Colima)…"
colima status >/dev/null 2>&1 || colima start --vm-type vz

echo "▶ Supabase local stack…"
if ! supabase status >/dev/null 2>&1; then
  supabase start
fi

echo "▶ JS dependencies (pnpm)…"
pnpm install

echo "▶ Python dependencies (uv)…"
(cd apps/ai-service && uv sync)

if [ ! -f apps/ai-service/.env ] || ! grep -Eq '^ANTHROPIC_API_KEY=.+' apps/ai-service/.env; then
  echo "⚠  No ANTHROPIC_API_KEY in apps/ai-service/.env."
  echo "   Everything works except 'Generate' (which calls Claude)."
  echo "   Add a key: cp apps/ai-service/.env.example apps/ai-service/.env  then edit it."
fi

if [ "${MISE_TEST_MODE:-}" = "true" ]; then
  echo "⚠  TEST MODE — /v1/test/* hooks are exposed (seed/reset). For E2E only."
fi

echo
echo "▶ Starting AI service (http://localhost:8000) + web (http://localhost:3000)…"
echo "  Open http://localhost:3000 — Ctrl-C to stop."
echo
exec pnpm exec turbo run dev --filter @mise/web --filter @mise/ai-service
