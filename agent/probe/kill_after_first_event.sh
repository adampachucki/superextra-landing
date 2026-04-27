#!/usr/bin/env bash
# Observe-then-kill wrapper for Test 1 / Test 3b.
#
# Usage: ./kill_after_first_event.sh <flavour> <sid> [--message "go"]
#
# Flow:
#   1. Launches run_probe.py in background.
#   2. Waits for the first event marker file (proves the runtime started).
#   3. Writes caller_killed_at marker doc to Firestore.
#   4. kill -9's the harness.

set -euo pipefail

FLAVOUR="${1:?flavour required (lifecycle|event_shape)}"
SID="${2:?sid required}"
shift 2
EXTRA_ARGS=("$@")

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MARKERS_DIR="/tmp/probe_markers"
mkdir -p "$MARKERS_DIR"

# Clean any prior markers for this sid
rm -f "${MARKERS_DIR}/${SID}".*

echo "[kill] launching harness flavour=${FLAVOUR} sid=${SID}"
cd "$REPO_ROOT/agent"
PYTHONPATH=.. .venv/bin/python -m agent.probe.run_probe \
  --flavour "$FLAVOUR" --sid "$SID" "${EXTRA_ARGS[@]}" &
HARNESS_PID=$!
echo "[kill] harness pid=${HARNESS_PID}"

# Wait for the first event marker — this proves the runtime is actually
# executing the agent (not just spinning up).
echo "[kill] waiting for first event marker..."
DEADLINE=$(( $(date +%s) + 600 ))
while [[ ! -f "${MARKERS_DIR}/${SID}.event.1" ]]; do
  if ! kill -0 "$HARNESS_PID" 2>/dev/null; then
    echo "[kill] harness died before first event"
    exit 1
  fi
  if [[ $(date +%s) -gt $DEADLINE ]]; then
    echo "[kill] timeout waiting for first event"
    kill -9 "$HARNESS_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 2
done
echo "[kill] first event observed — proceeding to kill"

# Read the real (auto-generated) sid that Agent Runtime created.
REAL_SID=$(cat "${MARKERS_DIR}/${SID}.real_sid")
echo "[kill] real_sid (Firestore lookup key): ${REAL_SID}"

# Write caller_killed_at marker to Firestore via gcloud-authed Python.
PYTHONPATH=.. .venv/bin/python -c "
from google.cloud import firestore
import os, time
fs = firestore.Client(project=os.environ.get('GOOGLE_CLOUD_PROJECT', 'superextra-site'))
ref = fs.collection('probe_runs').document('${REAL_SID}').collection('markers').document('caller_killed_at')
ref.set({'ts': firestore.SERVER_TIMESTAMP, 'wall_time': time.time()})
print('[kill] caller_killed_at marker written for real_sid=${REAL_SID}')
"

# Now kill the harness.
kill -9 "$HARNESS_PID" 2>/dev/null && echo "[kill] sent SIGKILL to ${HARNESS_PID}" || echo "[kill] harness already exited"

# Cleanup wait so the watcher can begin polling.
wait "$HARNESS_PID" 2>/dev/null || true
echo "[kill] done"
