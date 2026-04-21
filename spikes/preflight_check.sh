#!/usr/bin/env bash
# Pre-flight verification for pipeline-decoupling implementation.
# Run before starting any phase. Green = proceed. Red = fix it first.
#
# Usage:  bash spikes/preflight_check.sh
# Exit:   0 on all-green, 1 if anything critical is missing.

set -u

GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRITICAL_FAILS=0
WARNINGS=0

ok()   { printf "  ${GREEN}✓${RESET}  %s\n" "$1"; }
fail() { printf "  ${RED}✗${RESET}  %s\n" "$1"; CRITICAL_FAILS=$((CRITICAL_FAILS+1)); }
warn() { printf "  ${YELLOW}!${RESET}  %s\n" "$1"; WARNINGS=$((WARNINGS+1)); }
section() { printf "\n${YELLOW}== %s ==${RESET}\n" "$1"; }

section "CLI tools"
command -v gcloud >/dev/null 2>&1 && ok "gcloud installed" || fail "gcloud not installed"
command -v firebase >/dev/null 2>&1 && ok "firebase CLI installed" || warn "firebase CLI not installed (needed for rules deploy + emulator tests)"
command -v node >/dev/null 2>&1 && ok "node $(node --version)" || fail "node not installed"
command -v npm >/dev/null 2>&1 && ok "npm installed" || fail "npm not installed"
[ -x "$REPO_ROOT/agent/.venv/bin/python" ] && ok "agent venv present" || fail "agent venv missing (cd agent && python -m venv .venv && .venv/bin/pip install -r requirements.txt)"

section "gcloud project & auth"
ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null)"
if [ "$ACTIVE_PROJECT" = "superextra-site" ]; then
  ok "gcloud project = superextra-site"
else
  warn "gcloud project is '$ACTIVE_PROJECT' (expected superextra-site; run: gcloud config set project superextra-site)"
fi

# ADC check: must have cloud-platform scope for Agent Engine / Vertex calls
ADC_FILE="$HOME/.config/gcloud/application_default_credentials.json"
LEGACY_ADC="$(find "$HOME/.config/gcloud/legacy_credentials" -name adc.json 2>/dev/null | head -1 || true)"

if [ -f "$ADC_FILE" ]; then
  ok "ADC file present at default path"
elif [ -n "$LEGACY_ADC" ]; then
  warn "no ADC at default path, but legacy creds exist → export GOOGLE_APPLICATION_CREDENTIALS=$LEGACY_ADC"
else
  fail "no ADC configured — run: gcloud auth application-default login --scopes=openid,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/cloud-platform"
fi

# Scope check — use whichever ADC resolves (env var OR default path OR metadata).
# Python's google.auth.default() handles all three correctly.
TOKEN=""
if [ -x "$REPO_ROOT/agent/.venv/bin/python" ]; then
  TOKEN="$("$REPO_ROOT/agent/.venv/bin/python" -c "
import google.auth, google.auth.transport.requests
try:
    creds, _ = google.auth.default()
    creds.refresh(google.auth.transport.requests.Request())
    print(creds.token or '')
except Exception:
    print('')
" 2>/dev/null)"
fi

if [ -n "$TOKEN" ]; then
  TOKENINFO="$(curl -s "https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=$TOKEN" 2>/dev/null || true)"
  if echo "$TOKENINFO" | grep -q "cloud-platform"; then
    ok "ADC has cloud-platform scope"
  else
    fail "ADC missing cloud-platform scope → see docs/pipeline-decoupling-spike-results.md finding A.2"
  fi
else
  fail "cannot obtain access token — check gcloud auth or GOOGLE_APPLICATION_CREDENTIALS"
fi

section "Python deps in agent venv"
PYTHON="$REPO_ROOT/agent/.venv/bin/python"
if [ -x "$PYTHON" ]; then
  # Worker (Phase 3) uses google.cloud.firestore directly; no firebase-admin
  # and no google-cloud-tasks (enqueuing lives in the Node Cloud Function).
  for pkg in google.adk google.cloud.firestore fastapi uvicorn; do
    if "$PYTHON" -c "import $pkg" 2>/dev/null; then
      ok "python can import $pkg"
    else
      fail "python cannot import $pkg (pip install -r agent/requirements.txt + google-cloud-firestore + google-cloud-tasks)"
    fi
  done
fi

section "Live API access"
if [ -n "$TOKEN" ]; then
  # Agent Engine session list (just hit the endpoint, expect 200 or 404/403 but not auth-scope)
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/superextra-site/locations/us-central1/reasoningEngines/2746721333428617216" 2>/dev/null || echo "000")
  case "$HTTP_CODE" in
    200|404) ok "Agent Engine reachable (HTTP $HTTP_CODE)" ;;
    403) fail "Agent Engine: 403 — check IAM + ADC scope" ;;
    *)   warn "Agent Engine returned HTTP $HTTP_CODE (unexpected but not blocking)" ;;
  esac

  # Firestore reachable
  FS_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "https://firestore.googleapis.com/v1/projects/superextra-site/databases/(default)/documents/sessions?pageSize=1" 2>/dev/null || echo "000")
  case "$FS_CODE" in
    200) ok "Firestore reachable" ;;
    403) fail "Firestore: 403 — ADC likely needs cloud-platform scope" ;;
    *)   warn "Firestore returned HTTP $FS_CODE" ;;
  esac

  # Cloud Tasks service enabled
  TASKS_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "https://cloudtasks.googleapis.com/v2/projects/superextra-site/locations/us-central1/queues?pageSize=1" 2>/dev/null || echo "000")
  case "$TASKS_CODE" in
    200) ok "Cloud Tasks API enabled" ;;
    403) fail "Cloud Tasks API: 403 — gcloud services enable cloudtasks.googleapis.com" ;;
    *)   warn "Cloud Tasks returned HTTP $TASKS_CODE" ;;
  esac
fi

section "Expected Firestore composite indexes (Phase 1 scope — may not exist yet)"
# Simple substring match over gcloud output — robust enough and doesn't need jq
IDX_LIST="$(gcloud firestore indexes composite list --project=superextra-site --format='value(fields[].fieldPath)' 2>/dev/null || true)"
if echo "$IDX_LIST" | grep -qE "userId.*runId.*attempt.*seqInAttempt"; then
  ok "events (userId, runId, attempt, seqInAttempt) index exists"
else
  warn "events composite index missing (will be created by firebase deploy in Phase 1)"
fi

section "Existing test suites (to confirm baseline)"
if [ -d "$REPO_ROOT/node_modules" ]; then
  ok "npm deps installed"
else
  warn "npm install not run (run: npm install)"
fi

section "Summary"
if [ "$CRITICAL_FAILS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
  printf "${GREEN}ALL GREEN — safe to proceed with implementation.${RESET}\n"
  exit 0
elif [ "$CRITICAL_FAILS" -eq 0 ]; then
  printf "${YELLOW}Warnings only ($WARNINGS) — review above, but you can proceed.${RESET}\n"
  exit 0
else
  printf "${RED}$CRITICAL_FAILS critical failures — fix before starting implementation.${RESET}\n"
  exit 1
fi
