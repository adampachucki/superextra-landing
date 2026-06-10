#!/bin/bash
# One-shot environment sync for all three runtimes. Safe to re-run; run it
# after every pull that touches a lockfile or requirements file. Stale
# node_modules show up as confusing test failures (missing binaries, missing
# packages), so when tests fail unexpectedly, run this first.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== root npm =="
npm ci --no-audit --no-fund

echo "== functions npm =="
(cd functions && npm ci --no-audit --no-fund)

echo "== agent venv =="
if [ ! -d agent/.venv ]; then
  python3 -m venv agent/.venv
fi
agent/.venv/bin/pip install -q -r agent/requirements-dev.txt

echo "Bootstrap complete. Verify with: npm run test:all"
