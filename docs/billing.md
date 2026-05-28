# Billing

Superextra has two Stripe billing surfaces:

- Live billing: `/api/billing/checkout`, `/api/billing/portal`, `/api/billing/webhook`
- Test billing: `/api/billing/test/checkout`, `/api/billing/test/portal`, `/api/billing/test/webhook`

The live surface writes `users/{uid}.billing`, `users/{uid}.plan`, and `stripeEvents`.
The test surface writes `users/{uid}.billingTest`, `users/{uid}.planTest`, and
`stripeTestEvents`. Test subscriptions never grant production quota.

## Browser Switch

Live mode is the default:

```text
https://agent.superextra.ai/chat?billingMode=live
```

Test mode persists in the browser until switched back:

```text
https://agent.superextra.ai/chat?billingMode=test
```

In test mode, Checkout uses Stripe test mode and the billing UI reads
`billingTest`/`planTest`. Use Stripe's successful card:

```text
4242 4242 4242 4242
```

## Access Control

Test billing endpoints require either:

- Firebase custom claim `billingTester=true` or `admin=true`
- A verified email matching `BILLING_TEST_ALLOWED_EMAILS`

`BILLING_TEST_ALLOWED_EMAILS` accepts comma- or whitespace-separated entries.
Exact emails and wildcard domains are supported, for example:

```text
BILLING_TEST_ALLOWED_EMAILS=ap@superextra.ai,*@superextra.ai
```

## Stripe Setup

Configure live Stripe:

```bash
scripts/stripe-live-setup.sh
```

Configure Stripe test mode:

```bash
scripts/stripe-test-setup.sh
```

Both scripts configure the product, monthly multi-currency price, Customer
Portal, webhook endpoint, Firebase function secrets, and Polish Stripe Tax
registration for the selected Stripe mode.

## Smoke Test

After deploying Functions and agent hosting, run:

```bash
GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site node scripts/billing-mode-smoke.mjs
```

The smoke creates a disposable verified `@superextra.ai` Firebase user, creates
one test Checkout Session and one live Checkout Session, verifies test EUR
pricing and live PLN pricing, verifies Customer Portal creation in both modes,
then deletes the disposable Stripe customers and Firebase user. It does not
submit a card or charge money.

Secrets used by the deployed functions:

- `STRIPE_LIVE_SECRET_KEY`
- `STRIPE_LIVE_WEBHOOK_SECRET`
- `STRIPE_TEST_SECRET_KEY`
- `STRIPE_TEST_WEBHOOK_SECRET`

Legacy `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are not used by the
mode-split billing functions.
