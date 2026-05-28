#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STRIPE_MODE=test exec "$SCRIPT_DIR/stripe-billing-setup.sh" "$@"
