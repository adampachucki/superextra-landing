#!/usr/bin/env bash
set -euo pipefail

STRIPE_BIN="${STRIPE_BIN:-$HOME/.local/bin/stripe}"
FIREBASE_BIN="${FIREBASE_BIN:-}"
PROJECT_ID="${PROJECT_ID:-superextra-site}"
PRODUCT_ID="${PRODUCT_ID:-prod_UbDrqGnvat3kdR}"
PRICE_ID="${PRICE_ID:-price_1Tc1Q3LDP1TXNXw1oupHUuYX}"
LOOKUP_KEY="${LOOKUP_KEY:-superextra_unlimited_monthly}"
WEBHOOK_URL="${WEBHOOK_URL:-https://agent.superextra.ai/api/billing/webhook}"
RETURN_URL="${RETURN_URL:-https://agent.superextra.ai/chat}"

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
	read -rsp "Stripe live secret/restricted write key: " STRIPE_API_KEY
	echo
fi

if [[ ! "$STRIPE_API_KEY" =~ ^(sk_live|rk_live)_ ]]; then
	echo "Expected a live Stripe key beginning with sk_live_ or rk_live_." >&2
	exit 1
fi

api_raw() {
	STRIPE_API_KEY="$STRIPE_API_KEY" "$STRIPE_BIN" "$@" --live
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

event_args=()
for event in "${EVENTS[@]}"; do
	event_args+=(--enabled-events "$event")
done

echo "Verifying product..."
api_checked products retrieve "$PRODUCT_ID" >/dev/null

echo "Configuring multi-currency price..."
price_out="$(api_raw prices update "$PRICE_ID" \
	-d 'currency_options[eur][unit_amount]=900' \
	-d 'currency_options[eur][tax_behavior]=inclusive' \
	-d 'currency_options[pln][unit_amount]=1900' \
	-d 'currency_options[pln][tax_behavior]=inclusive')"

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
		--description 'Superextra billing webhook' \
		"${event_args[@]}" >/dev/null
	echo "Webhook endpoint already existed and was updated: $webhook_id"
	echo "Existing webhook secrets are not retrievable from Stripe; STRIPE_WEBHOOK_SECRET was not changed."
else
	webhook_out="$(api_checked webhook_endpoints create \
		--url "$WEBHOOK_URL" \
		--description 'Superextra billing webhook' \
		"${event_args[@]}")"
	webhook_id="$(jq -r '.id' <<<"$webhook_out")"
	webhook_secret="$(jq -r '.secret' <<<"$webhook_out")"
	set_firebase_secret STRIPE_WEBHOOK_SECRET "$webhook_secret"
	echo "Webhook endpoint created: $webhook_id"
	echo "Firebase secret STRIPE_WEBHOOK_SECRET set."
fi

set_firebase_secret STRIPE_SECRET_KEY "$STRIPE_API_KEY"
echo "Firebase secret STRIPE_SECRET_KEY set."

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

echo "Stripe live setup complete."
