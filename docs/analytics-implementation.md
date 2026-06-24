# Analytics implementation

Plan for measuring Superextra end-to-end: product usage, marketing performance, and the full commercial funnel — **anonymous → signup → activated → retained → paid → churned**. The shape is deliberately small: one managed product-analytics tool (PostHog), its native Stripe connector for revenue, and a thin client event layer on top of the existing Firebase + Stripe stack. No custom warehouse build, no third-party replay, no separate marketing-automation suite.

## What this plan assumes about the product today

This is grounded in the current codebase, not the original validation memo. The memo predates billing and is corrected here where it diverges.

- **One surface.** There is no separate marketing landing page anymore. All paid traffic lands on the agent app (`agent.superextra.ai`); the prompt area itself is the conversion surface. Attribution is therefore **single-origin** — no cross-subdomain cookie/storage problem.
- **Billing is live.** Full Stripe integration exists — multi-market (US/PL/GB/DE/other), live + test modes, a real `BillingModal` → Stripe Checkout, and a freemium model gated by a server-side, configurable quota (`{scope, period, limit}`) in `agent/superextra_agent/quota_gate.py`. The "upgrade" link is a real paid conversion, not an email gate. Source: `functions/billing.js`, `src/lib/billing-state.svelte.ts`, price lookup key `superextra_unlimited_monthly`.
- **First-touch attribution already exists.** `src/lib/campaign.ts` captures `utm_source/medium/campaign/content` + `fbclid` + `rdt_cid` into `localStorage.se_first_touch` (30-day TTL, first-touch semantics), stamped from `+layout.svelte:17`. The remaining work is forwarding it into analytics + the user doc, not building it.
- **No analytics SDK is wired in yet.** Greenfield install.
- **Consent is assumed.** Per the current decision, this plan assumes consent to collect for all surfaces and does not gate initialization behind a cookie banner. (The privacy policy still has to _disclose_ PostHog + the pixels — that's a legal-copy task, not a runtime gate.)

## Stack

| Layer                             | Tool                                                                                                            | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Product analytics                 | **PostHog Cloud EU**, free tier                                                                                 | Autocapture + custom events + funnels + retention + cohorts. 1M events/mo, 5k replays, 1-yr retention, EU-hosted (Frankfurt), RODO-clean for the Polish entity.                                                                                                                                                                                                                                                                                                                                                                |
| **Revenue / paid funnel / churn** | **PostHog Stripe source (webhook sync) + revenue-on-persons**                                                   | Webhook sync of Stripe charges/customers/invoices/subscriptions into PostHog. Revenue lands as properties on persons + the `persons_revenue_analytics` warehouse table → MRR, recurring-revenue churn, revenue by plan/market via HogQL/insights/MCP. **No client code, no BigQuery.** Note: PostHog's _opinionated_ Revenue Analytics dashboard is being removed on/after **June 30 2026** — the source and revenue data stay; we build the two or three insights we need ourselves (or via the MCP), which we'd want anyway. |
| Session replay                    | **On** (PostHog, free 5k/mo)                                                                                    | Low-signal for the funnel but useful for spotting prompt-area friction; zero added complexity once PostHog is initialized.                                                                                                                                                                                                                                                                                                                                                                                                     |
| Attribution glue                  | Existing `se_first_touch` (localStorage) → forwarded into `posthog.identify` + the Firestore user doc at signup | Same UTM + `fbclid` + `rdt_cid` feeds PostHog and (Phase 2) the CAPI payloads.                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Ad conversion APIs                | `conversionsApi` Cloud Function (**Phase 2**)                                                                   | Server-side Meta + Reddit CAPI. Optimizes ad bidding; not needed to answer the usage/funnel/retention questions. Sequenced after the core is live.                                                                                                                                                                                                                                                                                                                                                                             |
| Claude querying                   | PostHog MCP (`mcp.posthog.com/mcp`, OAuth)                                                                      | HogQL, funnels, retention, and Stripe-source management from Claude Code on the VM.                                                                                                                                                                                                                                                                                                                                                                                                                                            |

Rationale: PostHog gets us from "no analytics" to "signup conversion by ad creative, plus MRR and churn" in well under a day. A GCP-native build (Firestore→BigQuery export + Looker Studio) would be two days of plumbing before the first answer — wrong tradeoff. GA4 was rejected: poor UX and an EU-entity RODO posture (Google Signals / data-sharing) we'd rather not own.

## Event taxonomy

The events below cover the funnel end-to-end. The behavioral events live in the client; the money events come from the Stripe connector. Resist adding more until they answer a question the current set can't.

**Core funnel (Phase 1).**

| Event                | Where it fires                                                                                          | Key props                                                                        |
| -------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `$pageview`          | PostHog autocapture                                                                                     | path, utm\_\*, referrer (initial UTM captured automatically on the anon profile) |
| `prompt_focus`       | Genuine prompt engagement: real user focus or first keystroke (programmatic desktop autofocus excluded) | is_first_session                                                                 |
| `prompt_submitted`   | Question submitted                                                                                      | prompt_length, is_first_message, pillar                                          |
| `research_started`   | Agent run begins                                                                                        | session_id, run_id                                                               |
| `research_completed` | Agent returns final report                                                                              | session_id, run_id, duration_ms                                                  |
| `quota_block_hit`    | A turn returns `turnKind === 'quota_block'`                                                             | session_id                                                                       |
| `checkout_started`   | `billing.startCheckout()` fires (`billing-state.svelte.ts`)                                             | market, currency, billing_mode                                                   |
| `signup`             | First-time auth resolves (new Firebase user)                                                            | first*touch*\* props                                                             |
| `return_visit`       | Authed user lands on a new calendar day                                                                 | days_since_signup                                                                |
| `feedback_submitted` | Existing `agentFeedback` function                                                                       | rating, reason, kind, **text** (the freeform comment)                            |

**Gate, engagement & monetization (Phase 1.5).** Added to make the sign-in gate, the prompt pills, and the paid path measurable — each answers a question the core set can't (gate conversion, which topics seed first prompts, free→paid drop-off). Call sites: `auth.svelte.ts`, `LoginForm.svelte`, `/login/+page.svelte`, `TopicPills.svelte`, `billing-state.svelte.ts`, `chat-state.svelte.ts`.

| Event                   | Where it fires                                                           | Key props                                                                 |
| ----------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `login_shown`           | Login modal opens (`auth.openModal`) or the `/login` choice form renders | trigger (landing_submit/navbar/billing_upgrade/billing_portal/login_page) |
| `login_method_selected` | Google button / magic-link submit (intent, before the round-trip)        | method (google/magic_link)                                                |
| `signed_in`             | Every successful sign-in (identify fires first)                          | method, is_new_user                                                       |
| `pill_clicked`          | A prompt suggestion pill is clicked                                      | pill_id, category, position, reshuffled                                   |
| `upgrade_modal_shown`   | Upgrade modal becomes visible (`billing.openUpgrade`)                    | trigger (quota_block/account_menu)                                        |
| `checkout_confirmed`    | Stripe return confirms a paid plan (`confirmCheckout`)                   | market, currency, billing_mode                                            |
| `rate_limited`          | Agent send hits a 429 abuse cap (distinct from `quota_block_hit`)        | reason                                                                    |

`signed_in` is kept alongside `signup`: `signup` is the new-account acquisition event named in the funnels above; `signed_in` adds returning-user success and the auth-method mix. `login_method_selected` minus `signed_in` of the same method measures the magic-link send→never-completed leak and Google-popup abandonment. `checkout_confirmed` is a client funnel-completion milestone only — the Stripe connector remains authoritative for subscription/MRR truth (see "Revenue is not a client event").

**Person properties & super property.** `plan` and `market` are kept current on the PostHog person via `setPersonProperties` from the billing snapshot listener (gated on actual change), so every event can be sliced by plan without per-event props. Every event also carries an `environment` super property (`production`/`development`, from `$app/environment`'s `dev`) — there is one PostHog project, so dev/localhost traffic is filtered out in insights rather than hard-gated, which keeps analytics testable locally.

**Send the full feedback, including the freeform text.** The `agentFeedback` function already stores the comment in a private server-side collection (`functions/index.js:965`) — that stays as the durable record. PostHog gets a _copy_ on the `feedback_submitted` event so a 1-star rating or a complaint can be read next to that person's funnel position, their query history, and their session replay. For an MVP where qualitative signal is the highest-value data we'll get, tying free text to behavior is worth more than the tidiness of keeping it out. (The earlier draft excluded it on privacy grounds; with consent assumed, that objection no longer applies.) The server collection remains the source of truth; HogQL over free text is weak, so treat the PostHog copy as context-while-browsing-a-person, not as the place you run text analysis.

**Revenue is not a client event.** MRR, active subscriptions, recurring-revenue churn, and revenue-by-market come from the **Stripe connector**, which reads Stripe directly. The client `checkout_started` event marks the _funnel step_ (who reached checkout, from which creative); the connector owns the _money truth_. Keeping these separate avoids reconciling client events against Stripe — the connector is authoritative.

To join Stripe revenue back to the behavioral funnel and originating campaign, PostHog stitches a Stripe customer to a PostHog person via a **`posthog_person_distinct_id` metadata field on the Stripe customer** — _not_ by email. We control customer creation in `functions/billing.js` (today the metadata is `firebaseUid`/`app`/`stripeMode`, `billing.js:299`), so add `posthog_person_distinct_id: <firebase uid>` there. Since we `posthog.identify(uid)`, the distinct_id is the Firebase uid and the join is exact. (For customers created before this change, PostHog also resolves the same field from a later charge/subscription/invoice.)

## Identify flow

The merge from anonymous → authed person is the load-bearing piece of attribution. Without it, a Meta click on day 1 and a signup on day 3 look like two unrelated users.

1. Anonymous visitor lands; PostHog assigns a `distinct_id`. Autocapture records UTM + referrer on the anonymous person.
2. Visitor signs in (Google popup or magic link).
3. The auth singleton's `auth.onAuthChange(uid)` (`src/lib/auth.svelte.ts:235`) is the single hook every consumer already uses. On a non-null `uid`, call `posthog.identify(uid, { email, first_touch_source, first_touch_campaign, first_touch_content })`. PostHog merges the anonymous person into the identified one; the whole session history transfers. **On sign-out (`uid === null`), call `posthog.reset()`** so a shared browser doesn't bleed one person's session into the next — this is the matching half of identify and is easy to forget.
4. **New-user (signup) detection:** there is **no Firebase Auth `user.create` blocking function** in this repo (the original memo assumed one). Users are auto-created on their first `agentStream` call. The `trackSignIn()` helper in `auth.svelte.ts` (called from `signInWithGoogle` / `finishMagicLinkSignIn`) **identifies first** — `identify(uid, { email }, firstTouch)` — so the conversion events attach to the Firebase UID and merge anonymous history deterministically rather than racing the `onAuthStateChanged` identify. It then captures `signed_in { method, is_new_user }` for every success, and `signup` only when `getAdditionalUserInfo(result).isNewUser`. Returning sign-ins must not re-fire `signup`.

## Attribution glue (UTM + click-IDs)

Single-origin now, so this is just forwarding what `campaign.ts` already stores.

1. **On landing (done):** `stampFirstTouch()` writes UTM + `fbclid` + `rdt_cid` to `se_first_touch`.
2. **On signup (Phase 1, done):** read `firstTouch()` and pass the fields to `posthog.identify()`.
3. **Persisting `firstTouch` to the user doc is deferred to Phase 2.** `firestore.rules` blocks all client writes to `users/{uid}` (`allow write: if false`), so the first-touch blob can't be written from the browser — and it's only the CAPI payload that needs it on the doc. Phase 2 writes it server-side (in `agentStream`'s user-doc creation, or a small dedicated write) before the conversion fires.

## Revenue, paid conversion, retention, churn

This is the section the original memo couldn't write. With the Stripe connector live:

- **Paid-conversion funnel:** `signup → research_completed → quota_block_hit → checkout_started → (active subscription)`. The final step is read from connector subscription state, segmented by `first_touch_content` to see which creative produces _payers_, not just signups.
- **MRR / revenue churn:** from the synced Stripe data — gross revenue, recurring revenue, MRR per period, and revenue churn (invoice-without-subscription). Built as a couple of HogQL insights (or via the PostHog MCP), since the opinionated native dashboard is sunsetting June 30 2026. The underlying data and `persons_revenue_analytics` table remain.
- **Behavioral retention:** PostHog retention on `research_completed` (the activation event), segmented by signup cohort and `first_touch_content` — "are signups running a second query within 14 days," the memo's headline number.
- **Logo/seat churn:** derived from subscription status transitions (`active`/`trialing` → `canceled`/`unpaid`) in the connector data; queryable via HogQL or the PostHog MCP.

## Session replay

Enabled (PostHog free tier, 5k/mo). It is low-signal for funnel math but cheap insight into prompt-area friction during the MVP — and adds no complexity once PostHog is initialized. Recording is gated by a **project setting** ("Record user sessions"), not client config: the `/flags/` response currently returns `sessionRecording: false`, so toggle it on in PostHog → Settings to start capturing replays.

## Conversion tracking (Meta + Reddit CAPI) — Phase 2

Server-side conversion events keep ad bid-optimization working as client pixels degrade under iOS/ad-blockers. This is the highest-ROI plumbing _for ad spend_ — but it answers no usage/funnel/retention question, so it ships after the core.

Single Cloud Function, `conversionsApi`, triggered by Firestore:

- **`onCreate` on `users/{uid}`** → `CompleteRegistration` (Meta) + `SignUp` (Reddit). **Caveat that drives a Phase-1 decision:** today the user doc is created _lazily_ on the first `agentStream` call (`functions/index.js:573`), not at signup — so a signup-then-bounce user never creates a doc and would be missed. The fix is to make Phase 1 write the `firstTouch` blob (and email) onto `users/{uid}` at signup with `merge`, which creates the doc _at signup_. That single change makes `onCreate` a reliable signup signal **and** guarantees the `firstTouch` fields the CAPI payload needs are already on the doc when the trigger fires. (Alternative: a Firebase Auth user-creation Cloud Function — non-blocking, no blocking function required — but it wouldn't have `firstTouch` yet, so the eager user-doc write is the cleaner single source of truth.)
- **First completed turn** (`onCreate` on `sessions/{sid}/turns/{tid}` where `status == 'complete'` and it's the user's first) → `Lead` to both.

Payload: hashed email (SHA-256), `fbc`/`fbp`/`rdt_cid` (from the user doc's `firstTouch`), IP, UA, and an `event_id` shared with the client pixels for dedup.

**Env vars** (remember `firebase deploy` REPLACES env vars — these go in `functions/.env.superextra-site` before the next deploy or they vanish): `META_PIXEL_ID`, `META_CAPI_TOKEN`, `REDDIT_PIXEL_ID`, `REDDIT_CAPI_TOKEN`.

## Dashboards we actually need

Build once; PostHog emails a daily snapshot to a dedicated inbox.

1. **Signup funnel by `utm_content`** — `$pageview → prompt_submitted → signup → research_completed`. Filter by `utm_source` (Meta vs Reddit). "Which creative converts to a signup that gets value."
2. **Paid funnel by `utm_content`** — `signup → quota_block_hit → checkout_started → active subscription`. "Which creative produces payers."
3. **Retention by signup cohort** — daily retention on `research_completed`, segmented by `first_touch_content`. The headline number: second query within 14 days.
4. **Revenue** — MRR, recurring-revenue churn, revenue by market. A few HogQL insights over the synced Stripe data (or MCP-built), not the sunsetting native dashboard.

## Implementation outline

Phase 1 is ≈half a day and answers most questions. Phase 2 only when spend goes live.

**Phase 1 — core analytics**

1. Create the PostHog Cloud EU project. Session replay on.
2. Install `posthog-js`; initialize in `+layout.svelte` with `api_host: 'https://eu.i.posthog.com'` on app load.
3. Wire `posthog.identify(uid, { …firstTouch })` into the auth-state callback; `posthog.reset()` on sign-out; fire `signup` only on `getAdditionalUserInfo().isNewUser`. (Persisting `firstTouch` to `users/{uid}` is Phase 2 — rules block client writes; see Attribution glue.)
4. Add `prompt_focus`, `prompt_submitted`, `research_started`, `research_completed`, `quota_block_hit`, `checkout_started`, `return_visit` at their call sites. Extend the existing `agentFeedback` path to also `posthog.capture('feedback_submitted', { rating, reason, kind, text })`.
5. Add `posthog_person_distinct_id: <firebase uid>` to Stripe customer metadata in `functions/billing.js`. Connect the PostHog Stripe source (webhook sync).
6. Install the PostHog MCP on the VM (OAuth). Confirm `/mcp` works.
7. Build the four insights/dashboards (HogQL or MCP-built for revenue).

**Phase 2 — ad conversion APIs (when paid spend starts)** 8. Write `functions/conversionsApi.js` (Firestore triggers above). Add the four env vars to `functions/.env.superextra-site`. Add client Meta + Reddit pixels firing the same `event_id`. Deploy.

## What we don't build yet

- **A/B testing** — PostHog has it built in, but a €500 campaign lacks the volume for a meaningful test.
- **BigQuery export** — unnecessary; the Stripe connector + HogQL cover revenue and behavior inside PostHog.
- **Custom attribution modeling** — first-touch UTM is sufficient for hook validation.
- **A separate CRM** — Firestore + Notion (via MCP) covers the signup pipeline and operator-interview notes.

## Footer (Polish entity, US-facing)

Trust signals for US operators, adapted to a Polish operating entity (relevant here because the privacy policy must disclose what we collect):

- Company name + legal form ("Superextra Sp. z o.o.") with NIP and KRS/REGON; registered Polish address; support email on `superextra.ai`.
- **"Built in Poland."** — turns the non-US entity into a brand attribute.
- **Privacy Policy** (RODO, English): names Superextra Sp. z o.o. as controller, states EU data residency ("Google Cloud Frankfurt, PostHog Frankfurt"), and discloses the Meta/Reddit pixels + PostHog.
- **Terms of Service** (English): scopes the freemium tier and paid plans.

Not needed: a US entity, US phone/address, SOC2 badge, or third-party trust badges.
</content>
</invoke>
