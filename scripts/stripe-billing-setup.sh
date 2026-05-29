#!/usr/bin/env bash
set -euo pipefail

STRIPE_BIN="${STRIPE_BIN:-$HOME/.local/bin/stripe}"
FIREBASE_BIN="${FIREBASE_BIN:-}"
PROJECT_ID="${PROJECT_ID:-superextra-site}"
PRODUCT_NAME="${PRODUCT_NAME:-Superextra Pro}"
PRODUCT_DESCRIPTION="${PRODUCT_DESCRIPTION:-Superextra Pro monthly subscription}"
LOOKUP_KEY="${LOOKUP_KEY:-superextra_unlimited_monthly}"
RETURN_URL="${RETURN_URL:-https://agent.superextra.ai/chat}"

MODE="${STRIPE_MODE:-live}"
if [[ "${1:-}" == "live" || "${1:-}" == "prod" || "${1:-}" == "production" ]]; then
	MODE="live"
	shift
elif [[ "${1:-}" == "test" || "${1:-}" == "sandbox" ]]; then
	MODE="test"
	shift
fi

case "$MODE" in
	live)
		KEY_PATTERN='^(sk_live|rk_live)_'
		KEY_LABEL="live"
		STRIPE_LIVE_ARG=(--live)
		PRODUCT_ID="${PRODUCT_ID:-${STRIPE_LIVE_PRODUCT_ID:-prod_UbDrqGnvat3kdR}}"
		PRICE_ID="${PRICE_ID:-${STRIPE_LIVE_PRICE_ID:-price_1Tc1Q3LDP1TXNXw1oupHUuYX}}"
		WEBHOOK_URL="${WEBHOOK_URL:-https://agent.superextra.ai/api/billing/webhook}"
		SECRET_KEY_NAME="STRIPE_LIVE_SECRET_KEY"
		WEBHOOK_SECRET_NAME="STRIPE_LIVE_WEBHOOK_SECRET"
		;;
	test)
		KEY_PATTERN='^(sk_test|rk_test)_'
		KEY_LABEL="test"
		STRIPE_LIVE_ARG=()
		PRODUCT_ID="${PRODUCT_ID:-${STRIPE_TEST_PRODUCT_ID:-prod_UbJujQUWXTjqwh}}"
		PRICE_ID="${PRICE_ID:-${STRIPE_TEST_PRICE_ID:-price_1Tc7H0LDP1TXNXw1JCTZgIey}}"
		WEBHOOK_URL="${WEBHOOK_URL:-https://agent.superextra.ai/api/billing/test/webhook}"
		SECRET_KEY_NAME="STRIPE_TEST_SECRET_KEY"
		WEBHOOK_SECRET_NAME="STRIPE_TEST_WEBHOOK_SECRET"
		;;
	*)
		echo "Usage: $0 [live|test]" >&2
		exit 1
		;;
esac

EVENTS=(
	checkout.session.completed
	customer.subscription.updated
	customer.subscription.deleted
	invoice.paid
	invoice.payment_failed
)

require() {
	command -v "$1" >/dev/null || {
		echo "Missing required command: $1" >&2
		exit 1
	}
}

require jq

if [[ -z "$FIREBASE_BIN" ]]; then
	if command -v firebase >/dev/null; then
		FIREBASE_BIN="$(command -v firebase)"
	elif compgen -G "$HOME/.nvm/versions/node/*/bin/firebase" >/dev/null; then
		FIREBASE_BIN="$(ls -t "$HOME"/.nvm/versions/node/*/bin/firebase | head -n 1)"
	else
		echo "Missing required command: firebase" >&2
		exit 1
	fi
fi

if [[ ! -x "$STRIPE_BIN" ]]; then
	echo "Stripe CLI not found at $STRIPE_BIN" >&2
	exit 1
fi

if [[ ! -x "$FIREBASE_BIN" ]]; then
	echo "Firebase CLI is not executable at $FIREBASE_BIN" >&2
	exit 1
fi

if [[ -z "${STRIPE_API_KEY:-}" ]]; then
	read -rsp "Stripe ${KEY_LABEL} secret/restricted write key: " STRIPE_API_KEY
	echo
fi

if [[ ! "$STRIPE_API_KEY" =~ $KEY_PATTERN ]]; then
	echo "Expected a ${KEY_LABEL} Stripe key." >&2
	exit 1
fi

api_raw() {
	STRIPE_API_KEY="$STRIPE_API_KEY" "$STRIPE_BIN" "$@" "${STRIPE_LIVE_ARG[@]}"
}

api_checked() {
	local out
	out="$(api_raw "$@")"
	if jq -e '.error' >/dev/null <<<"$out"; then
		jq -r '.error.message' <<<"$out" >&2
		return 1
	fi
	printf '%s\n' "$out"
}

set_firebase_secret() {
	local name="$1"
	local value="$2"
	printf '%s' "$value" | "$FIREBASE_BIN" --project "$PROJECT_ID" functions:secrets:set "$name" --data-file - --force >/dev/null
}

firebase_secret_has_value() {
	local name="$1"
	command -v gcloud >/dev/null &&
		gcloud secrets versions access latest --secret="$name" --project="$PROJECT_ID" >/dev/null 2>&1
}

copy_firebase_secret() {
	local from="$1"
	local to="$2"
	local value
	value="$(gcloud secrets versions access latest --secret="$from" --project="$PROJECT_ID")"
	set_firebase_secret "$to" "$value"
}

event_args=()
for event in "${EVENTS[@]}"; do
	event_args+=(--enabled-events "$event")
done

echo "Configuring ${MODE} Stripe billing..."

if [[ -n "$PRODUCT_ID" ]]; then
	if ! api_checked products retrieve "$PRODUCT_ID" >/dev/null; then
		PRODUCT_ID=""
	fi
fi

if [[ -z "$PRODUCT_ID" ]]; then
	PRODUCT_ID="$(api_checked products list --limit 100 |
		jq -r --arg name "$PRODUCT_NAME" '.data[] | select(.name == $name and .active == true) | .id' |
		head -n 1)"
fi

if [[ -z "$PRODUCT_ID" ]]; then
	echo "Creating product..."
	PRODUCT_ID="$(api_checked products create \
		--name "$PRODUCT_NAME" \
		--description "$PRODUCT_DESCRIPTION" \
		--tax-code txcd_10103001 \
		--statement-descriptor SUPEREXTRA |
		jq -r '.id')"
else
	echo "Verifying product..."
	api_checked products update "$PRODUCT_ID" \
		--name "$PRODUCT_NAME" \
		--description "$PRODUCT_DESCRIPTION" \
		--tax-code txcd_10103001 \
		--statement-descriptor SUPEREXTRA >/dev/null
fi

if [[ -z "$PRICE_ID" ]]; then
	PRICE_ID="$(api_checked prices list --lookup-keys "$LOOKUP_KEY" --active true --limit 10 |
		jq -r '.data[0].id // empty')"
fi

echo "Configuring multi-currency price..."
if [[ -n "$PRICE_ID" ]]; then
	price_out="$(api_raw prices update "$PRICE_ID" \
		-d 'currency_options[eur][unit_amount]=900' \
		-d 'currency_options[eur][tax_behavior]=inclusive' \
		-d 'currency_options[gbp][unit_amount]=900' \
		-d 'currency_options[gbp][tax_behavior]=inclusive' \
		-d 'currency_options[pln][unit_amount]=1900' \
		-d 'currency_options[pln][tax_behavior]=inclusive')"
else
	price_out='{"error": {"message": "missing price"}}'
fi

if jq -e '.error' >/dev/null <<<"$price_out"; then
	echo "Existing price could not be updated; creating replacement price."
	price_out="$(api_checked prices create \
		--currency usd \
		--unit-amount 900 \
		--product "$PRODUCT_ID" \
		--recurring.interval month \
		--tax-behavior inclusive \
		--lookup-key "$LOOKUP_KEY" \
		--transfer-lookup-key true \
		-d 'currency_options[eur][unit_amount]=900' \
		-d 'currency_options[eur][tax_behavior]=inclusive' \
		-d 'currency_options[gbp][unit_amount]=900' \
		-d 'currency_options[gbp][tax_behavior]=inclusive' \
		-d 'currency_options[pln][unit_amount]=1900' \
		-d 'currency_options[pln][tax_behavior]=inclusive')"
	PRICE_ID="$(jq -r '.id' <<<"$price_out")"
	api_checked products update "$PRODUCT_ID" --default-price "$PRICE_ID" >/dev/null
else
	PRICE_ID="$(jq -r '.id' <<<"$price_out")"
fi

api_checked prices retrieve "$PRICE_ID" -e currency_options | jq '{id,lookup_key,currency,unit_amount,tax_behavior,currency_options}'

echo "Configuring Customer Portal..."
portal_id="$(api_checked billing_portal configurations list --limit 100 |
	jq -r '.data[] | select(.is_default == true) | .id' |
	head -n 1)"

if [[ -n "$portal_id" ]]; then
	api_checked post "/v1/billing_portal/configurations/$portal_id" \
		-d "default_return_url=$RETURN_URL" >/dev/null
else
	portal_id="$(api_checked post /v1/billing_portal/configurations \
		-d "default_return_url=$RETURN_URL" \
		-d 'features[customer_update][enabled]=true' \
		-d 'features[customer_update][allowed_updates][]=name' \
		-d 'features[customer_update][allowed_updates][]=email' \
		-d 'features[customer_update][allowed_updates][]=address' \
		-d 'features[customer_update][allowed_updates][]=phone' \
		-d 'features[customer_update][allowed_updates][]=tax_id' \
		-d 'features[invoice_history][enabled]=true' \
		-d 'features[payment_method_update][enabled]=true' \
		-d 'features[subscription_cancel][enabled]=true' \
		-d 'features[subscription_cancel][mode]=at_period_end' \
		-d 'features[subscription_cancel][proration_behavior]=none' \
		-d 'features[subscription_cancel][cancellation_reason][enabled]=true' \
		-d 'features[subscription_cancel][cancellation_reason][options][]=too_expensive' \
		-d 'features[subscription_cancel][cancellation_reason][options][]=switched_service' \
		-d 'features[subscription_cancel][cancellation_reason][options][]=unused' \
		-d 'features[subscription_cancel][cancellation_reason][options][]=other' \
		-d 'features[subscription_update][enabled]=false' |
		jq -r '.id')"
fi

echo "Customer Portal configuration: $portal_id"

echo "Configuring webhook endpoint..."
webhook_id="$(api_checked webhook_endpoints list --limit 100 |
	jq -r --arg url "$WEBHOOK_URL" '.data[] | select(.url == $url) | .id' |
	head -n 1)"

if [[ -n "$webhook_id" ]]; then
	api_checked webhook_endpoints update "$webhook_id" \
		--description "Superextra ${MODE} billing webhook" \
		"${event_args[@]}" >/dev/null
	echo "Webhook endpoint already existed and was updated: $webhook_id"
	if firebase_secret_has_value "$WEBHOOK_SECRET_NAME"; then
		echo "Firebase secret ${WEBHOOK_SECRET_NAME} already set."
	elif [[ "$MODE" == "live" ]] && firebase_secret_has_value STRIPE_WEBHOOK_SECRET; then
		copy_firebase_secret STRIPE_WEBHOOK_SECRET "$WEBHOOK_SECRET_NAME"
		echo "Firebase secret ${WEBHOOK_SECRET_NAME} copied from legacy STRIPE_WEBHOOK_SECRET."
	else
		echo "Existing webhook secrets are not retrievable from Stripe." >&2
		echo "Set ${WEBHOOK_SECRET_NAME}, or delete the ${MODE} webhook endpoint and rerun this script." >&2
		exit 1
	fi
else
	webhook_out="$(api_checked webhook_endpoints create \
		--url "$WEBHOOK_URL" \
		--description "Superextra ${MODE} billing webhook" \
		"${event_args[@]}")"
	webhook_id="$(jq -r '.id' <<<"$webhook_out")"
	webhook_secret="$(jq -r '.secret' <<<"$webhook_out")"
	set_firebase_secret "$WEBHOOK_SECRET_NAME" "$webhook_secret"
	echo "Webhook endpoint created: $webhook_id"
	echo "Firebase secret ${WEBHOOK_SECRET_NAME} set."
fi

set_firebase_secret "$SECRET_KEY_NAME" "$STRIPE_API_KEY"
echo "Firebase secret ${SECRET_KEY_NAME} set."

echo "Configuring Polish Stripe Tax registration..."
pl_registration_id="$(api_checked tax registrations list --limit 100 |
	jq -r '.data[] | select(.country == "PL" and (.status == "active" or .status == "scheduled")) | .id' |
	head -n 1)"

if [[ -n "$pl_registration_id" ]]; then
	echo "Polish tax registration already present: $pl_registration_id"
else
	tax_out="$(api_raw tax registrations create \
		--country PL \
		--active-from now \
		--country-options.pl.type standard \
		--country-options.pl.standard.place-of-supply-scheme standard)"
	if jq -e '.error' >/dev/null <<<"$tax_out"; then
		echo "Polish tax registration was not created:"
		jq -r '.error.message' <<<"$tax_out"
		echo "Set the head office address in Stripe Tax settings, then rerun this script."
	else
		pl_registration_id="$(jq -r '.id' <<<"$tax_out")"
		echo "Polish tax registration created: $pl_registration_id"
	fi
fi

echo "Stripe ${MODE} billing setup complete."
