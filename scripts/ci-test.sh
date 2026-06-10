#!/bin/bash
# Canonical test runner — `npm run test:all` and the CI test job both run
# this script, so local verification and CI cannot drift.
#
# Prerequisites (see scripts/bootstrap.sh): root + functions node_modules in
# sync with their lockfiles, agent Python deps installed (agent/.venv locally;
# system pip in CI), and Java 21+ for the Firestore rules emulator.
set -euo pipefail
cd "$(dirname "$0")/.."

# `command -v java` is not enough: macOS ships a stub /usr/bin/java that
# exists but exits non-zero when no JRE is installed.
if ! java -version >/dev/null 2>&1; then
  echo "ERROR: Java 21+ is required for the Firestore rules emulator (npm run test:rules)." >&2
  echo "  macOS: brew install --cask temurin@21" >&2
  exit 1
fi

echo "== Prettier + ESLint =="
npm run format:check
npx eslint .

echo "== svelte-check =="
npm run check

echo "== Vitest =="
npm run test:unit -- --run

echo "== Firestore rules emulator =="
npm run test:rules

echo "== Cloud Functions tests =="
(cd functions && npm test)

echo "== Agent lint (ruff) =="
if [ -x agent/.venv/bin/ruff ]; then
  (cd agent && .venv/bin/ruff check .)
else
  (cd agent && ruff check .)
fi

echo "== Agent tests =="
if [ -x agent/.venv/bin/pytest ]; then
  (cd agent && PYTHONPATH=. .venv/bin/pytest tests/)
else
  (cd agent && PYTHONPATH=. pytest tests/)
fi

echo "All suites passed."
