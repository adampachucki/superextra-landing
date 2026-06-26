# Superextra — Paid campaign log

Running record of every paid campaign: what we ran, the targeting, the messaging,
and how it did. Update it whenever a campaign is created, changed, launched, paused,
or reviewed. Copy ↔ voice lives in [copy-guidelines.md](./copy-guidelines.md); the
editable creatives live in the ad studio at **`/brand/ads`** (PIN-gated), sourced from
`src/lib/brand/ads-data.ts`.

## Accounts & assets (shared across campaigns)

| Thing               | Value                                                                                                 |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| Meta ad account     | **Superextra** · `4510724902549637` · currency **PLN**                                                |
| Business            | Superextra · `4454026098257773`                                                                       |
| Facebook Page       | Superextra · `1133463516519928`                                                                       |
| Instagram account   | **none attached yet** — ads are FB-only until one is linked                                           |
| Pixel / dataset     | **Superextra Pixel** · `2061038364814901` · conversion event **`Lead`** (fires on access-form submit) |
| Landing destination | `https://agent.superextra.ai/` (the access/"Book a demo" form)                                        |

## Active campaigns

| Campaign                                   | ID               | Objective                    | Budget      | Targeting                                                                                                      | Status                                | Launched   |
| ------------------------------------------ | ---------------- | ---------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------- | ---------- |
| US Traffic — restaurants                   | `52549482610363` | Traffic · Landing Page Views | 100 PLN/day | US, 25–64, FB+IG (no Audience Network)                                                                         | **LIVE**                              | 2026-06-23 |
| US Leads — restaurants                     | `52548746445163` | Leads (website)              | 100 PLN/day | US broad                                                                                                       | **PAUSED** (cold pixel → no delivery) | 2026-06-22 |
| US Operators — restaurants (Traffic · LPV) | `52553900564763` | Traffic · Landing Page Views | 30 PLN/day  | US, 25+, FB Feed only, Advantage+ **off** — **operator layer (Page Admins + interests) to add in Ads Manager** | **PAUSED** (built, not launched)      | —          |

---

## Campaign 1 — US Leads — restaurants

- **Created:** 2026-06-22 · **Launched:** 2026-06-22 · **Status:** LIVE (campaign + ad set + 4 ads ACTIVE; ads in Meta review / `IN_PROCESS`)
- **Goal:** lead/sign-up — drive US restaurant operators to the access form.
- **Campaign** `52548746445163` — objective `OUTCOME_LEADS`, AUCTION, **CBO** daily **100 PLN** (`10000` grosze), bid `LOWEST_COST_WITHOUT_CAP`, special ad categories none.
- **Ad set** `52548746545363` "US restaurants — broad":
  - Optimization: `OFFSITE_CONVERSIONS` → pixel `2061038364814901`, event **`LEAD`** (website conversions, not on-platform lead forms).
  - Targeting: **US**, Advantage+ Audience on (broad — the pixel finds leads), age default, automatic placements.
  - Billing: impressions. Destination: website.
- **Destination + tracking:** `agent.superextra.ai/` with `utm_source=meta · utm_medium=paid_social · utm_campaign=us_leads_restaurants · utm_content={a|b|c|d}` (PostHog attributes via `campaign.ts`).
- **Creative look:** all four on the **colour** background (Indigo → Violet · rich, circular glows), 1080×1080, hosted at `agent.superextra.ai/ads/ad-{a..d}.jpg`.
- **CTA:** **Try Now** (Meta rejected "Get Started" for this objective; swap to Book Now / Request Time / Apply Now if preferred).

### Ads (messaging)

| #                           | Ad ID · Creative ID                   | Image headline                          | Primary text                                                                                                                                                     | Meta headline                      |
| --------------------------- | ------------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **A** · why is it happening | `52548748716563` · `1391486929494205` | Why your restaurant slowed down?        | Sales drop and no one can say why. Superextra shows what changed around you — find the fix before it sticks.                                                     | Know what changed — and why        |
| **B** · the big decisions   | `52548748727963` · `1024668910101372` | AI consultant for every restaurant.     | Where to open. What to serve. When to advertise. Superextra answers the decisions that make or break a restaurant — with live data from the market around you.   | AI consultant for every restaurant |
| **C** · beat the competitor | `52548748736963` · `1642272480166072` | Beat the restaurant next door.          | See how the restaurants near you advertise, what their guests love, and where they're winning. Superextra keeps you one step ahead of the competition next door. | Beat the restaurant next door      |
| **D** · pricing             | `52548748754363` · `1136322958925169` | Your menu. More guests. Better margins. | See every competitor's prices. Set yours to win. Superextra benchmarks your whole menu against the local market in minutes.                                      | Price like you can see the market  |

### Notes / open items

- **Instagram off** — no IG account attached; runs FB-only until one is linked (pick it on the ad in Ads Manager, or attach the IG business account).
- **Fresh pixel** — the `Lead` event has no history; delivery starts slow and sharpens as leads accumulate. Started at 100 PLN/day for this reason.
- CTA "Try Now" stands in for the intended "Get Started" (unsupported by the API here).

### Results (fill in once live)

| Date | Spend | Impr. | Clicks | CTR | Leads | Cost/Lead | Notes            |
| ---- | ----- | ----- | ------ | --- | ----- | --------- | ---------------- |
| —    | —     | —     | —      | —   | —     | —         | not yet launched |

---

## Template — new campaign

```
## Campaign N — <name>
- Created: <date> · Status: <PAUSED/ACTIVE>
- Goal: <one line>
- Campaign <id> — objective <…>, budget <…>, bid <…>
- Ad set <id> "<name>": optimization <…>, targeting <geo/audience/age/placements>, billing <…>
- Destination + tracking: <url> + <UTMs>
- Creative look: <background / size / where hosted>
- CTA: <…>

### Ads (messaging)
| # | Ad ID · Creative ID | Image headline | Primary text | Meta headline |

### Notes / open items
### Results
| Date | Spend | Impr. | Clicks | CTR | Leads | Cost/Lead | Notes |
```

## Campaign 2 — US Traffic — restaurants

- **Created / launched:** 2026-06-23 · **Status:** LIVE
- **Why:** Campaign 1 (conversion-optimized) wouldn't deliver — a brand-new pixel with no `Lead` history gives Meta nothing to optimize toward, so it served 0 over ~24h. This campaign bootstraps **traffic** to drive site visits and accumulate `Lead` pixel events; switch back to lead-optimization once ~30–50 leads of data exist.
- **Campaign** `52549482610363` — `OUTCOME_TRAFFIC`, AUCTION, CBO 100 PLN/day, LOWEST_COST.
- **Ad set** `52549482683163` "US restaurants — LPV": optimization `LANDING_PAGE_VIEWS`; targeting **US, age 25–64, Facebook + Instagram only (Audience Network excluded)**, Advantage+ Audience off (hard age cap), no interest layer (MCP can't add interest IDs — add in Ads Manager for sharper targeting).
- **Ads** (reuse Campaign 1 creatives + copy): A `52549482729763`, B `52549482742563`, C `52549482757963`, D `52549482771563`.
- Same destination + UTMs + creatives as Campaign 1.

### Results (Campaign 2)

| Date                     | Impr. | Reach | Clicks | CTR   | Spend      | Leads | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------ | ----- | ----- | ------ | ----- | ---------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-06-23 (first hours) | 229   | 221   | 2      | 0.87% | 4.32 PLN   | 0     | Delivery started after first-spend hold cleared. Ad **B** (AI consultant / big decisions) leading: 152 impr, both clicks (1.32% CTR). A/C/D trickle delivery so far.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 2026-06-25 (cumulative)  | 4,979 | 4,199 | 164    | 3.29% | 235.61 PLN | 0     | **Wrong-audience verdict.** As delivery scaled, **Ad A** took over — 3.84% CTR, CPC ~1.38 PLN, ~86% of spend (Meta picked the winner; B/C/D starved). But PostHog tells the real story: **125 US landers, ~0s median session, 123/125 bounced, 0 prompt submissions, 0 sign-ups.** 119/125 mobile, all US. Replay analysis = low-intent mobile scrollers, not a copy problem. Root cause: LPV optimization buys the cheapest landers + Advantage+ ignored targeting. → spun up **Campaign 3** to fix the audience. Measure this campaign in PostHog by `utm_campaign=us_leads_restaurants` (the creatives' static tag) or `utm_id=52549482610363` (campaign id, Meta auto-fill). |

## Campaign 3 — US Operators — restaurants (Traffic · LPV)

- **Created:** 2026-06-26 · **Status:** PAUSED (built via MCP; **not launched** — operator targeting must be completed in Ads Manager first, see below).
- **Why:** Campaign 2 (broad Traffic/LPV) spent ~236 PLN over 23–25 Jun and produced **0 prompt submissions / 0 sign-ups** from 125 US landers (~0s median session, 123/125 bounced, 119/125 mobile). Replay + PostHog analysis: the traffic is the **wrong audience** (low-intent mobile scrollers), not a landing-page-copy problem. Two root causes — (1) `LANDING_PAGE_VIEWS` optimization buys the _cheapest_ landers; (2) Meta's default **Advantage+ Audience** treats interest/behaviour targeting as _suggestions_ (2026 — only geo + min age are hard rules), so targeting was never enforced. This campaign isolates budget and creates a real operator-targeting slot.
- **Campaign** `52553900564763` — `OUTCOME_TRAFFIC`, AUCTION, **CBO 30 PLN/day** (`3000` grosze), bid `LOWEST_COST_WITHOUT_CAP`, special ad categories none. **Separate from Campaign 2 on purpose:** Campaign 2 is CBO and would starve a narrow (pricier) ad set by reallocating budget to the cheap broad set — own campaign = protected budget. (Engaged Page Views was the intended optimization but is **not available** on this account — absent from the campaign's `valid_optimization_goals` — so LPV stands.)
- **Ad set** `52553900768963` "Operators — Page Admins + restaurant interests · FB Feed · 25+ · LPV":
  - Optimization `LANDING_PAGE_VIEWS`; billing impressions; destination website.
  - Targeting set via MCP: **US · age 25+ · Advantage+ Audience OFF (hard age cap) · Facebook Feed only** (`publisher_platforms=[facebook]`, `facebook_positions=[feed]`; Audience Network + IG excluded — no IG account attached).
  - **⚠ TO ADD IN ADS MANAGER before launch (MCP can't set interest/behaviour IDs):** Detailed Targeting → Behaviours → Digital Activities → **Facebook Page Admins**, then **Narrow audience (AND)** with restaurant interests (Restaurant management, Foodservice, Toast/Square POS, Nation's Restaurant News, Restaurant Business). **This operator layer is the entire point** — without it the ad set is ~identical to Campaign 2's broad set.
- **Ad** `52553900785163` "A · why is it happening" — reuses creative `1391486929494205` (the Campaign 1/2 variant-A winner). B/C/D dropped (never earned real delivery).
- **Destination + tracking:** `agent.superextra.ai/`. Creatives carry static `utm_campaign=us_leads_restaurants`; Meta auto-fills `utm_id={campaign id}` / `utm_term={adset id}`. **Isolate this campaign in PostHog by `utm_id=52553900564763`** (or adset `utm_term=52553900768963`). If clean separation matters, set a distinct `utm_campaign=us_operators_restaurants` on the ad's link in Ads Manager.
- **Launch gate + how we judge it:** success = **PostHog prompt-submissions, NOT CPC**. Expect CPC ↑ and impressions ↓ vs Campaign 2 — that's correct for a premium narrow audience. Run head-to-head against Campaign 2 (broad) and compare on-site engagement.

### Results (Campaign 3)

| Date | Impr. | Reach | Clicks | CTR | Spend | Prompt submits | Notes                                                                 |
| ---- | ----- | ----- | ------ | --- | ----- | -------------- | --------------------------------------------------------------------- |
| —    | —     | —     | —      | —   | —     | —              | not yet launched (paused; awaiting operator targeting in Ads Manager) |

## Changelog

- **2026-06-22** — Campaign 1 (US Leads — restaurants) built in full, PAUSED. Pixel + 4 colour creatives live.
- **2026-06-22** — **Launched.** Campaign + ad set + 4 ads set ACTIVE (entered Meta review). End-to-end verified on prod: page loads, pixel `PageView` + `Lead` fire, demo form submits, UTMs captured. CTA "Try Now"; Instagram not yet attached (FB-only).
- **2026-06-23** — Campaign 1 delivered **0** over ~24h (cold-pixel conversion optimization). Diagnosed + **paused** it; launched **Campaign 2 (Traffic / Landing Page Views)** with tighter targeting (age 25–64, no Audience Network) to bootstrap delivery and gather `Lead` data. In-place optimization change was blocked by Meta (CBO same-optimization lock + attribution window is immutable after ad-set creation), so a new campaign was the supported path.
- **2026-06-23 (later)** — **Delivery started.** Campaign 2 cleared the new-account first-spend "Preparing" hold and began serving: first ~229 impr / 2 clicks / 4.32 PLN / 0.87% CTR. (Tried the off→on toggle while waiting; it bounced back to "Preparing," confirming it was an account-review hold, not a glitch — it released on Meta's own clock.) Ad B leading early delivery.
- **2026-06-25** — **Campaign 2 reviewed: wrong audience.** Scaled to ~236 PLN / 4,979 impr / 164 clicks / 3.29% CTR; Ad A took over (3.84% CTR). But PostHog: 125 US landers, ~0s median session, 123/125 bounced, **0 prompt submissions / 0 sign-ups**, 119/125 mobile. Replay analysis = low-intent mobile scrollers. Verified Meta 2026 behaviour: Advantage+ treats detailed targeting as suggestions (geo + min age are the only hard rules); "Facebook Page Admins" behaviour still exists. Decision: target restaurant _operators_ via Page-Admin behaviour + interest narrowing, stay on Meta before LinkedIn/Google. No customer list → lookalikes out.
- **2026-06-26** — **Built Campaign 3 (US Operators — restaurants), PAUSED.** New isolated CBO campaign `52553900564763` @ 30 PLN/day, OUTCOME_TRAFFIC; ad set `52553900768963` (US, 25+, Advantage+ off, FB Feed only); ad `52553900785163` reusing variant-A creative. Built via MCP. Engaged Page Views unavailable on this account → LPV. **Operator targeting (Page Admins + restaurant interests) still to be added in Ads Manager — the MCP has no interest-ID endpoint — then launch.** Judge on PostHog prompt-submissions, not CPC.
- **2026-06-26** — **Engaged-visit instrumentation (code, not yet deployed).** Added an `EngagedVisit` Meta-pixel custom event — `trackEngagedVisit()` in `src/lib/meta-pixel.ts`, fired **once per visit** on genuine prompt engagement (focus/keystroke, programmatic autofocus excluded) or example-pill click (`RestaurantPromptComposer.svelte`, `TopicPills.svelte`). Purpose: an "actually engaged" signal to optimize paid-social toward, vs. cheapest page-loaders. Verified in a real browser — fbq sequence `init → PageView → trackCustom EngagedVisit`, fires exactly once across two keystrokes. svelte-check + eslint clean. **Remaining (in order):** (1) deploy to prod; (2) seed a few `EngagedVisit` hits so Meta sees the event; (3) create the **"Engaged Visit" custom conversion** in Events Manager → Custom Conversions (source = Superextra Pixel `2061038364814901`, event = `EngagedVisit`) — **no MCP create tool, UI step**; (4) switch the Operators ad set (`52553900768963`) optimization to that custom conversion **only once it fires ~30–50/wk** — until then keep `LANDING_PAGE_VIEWS` or it cold-pixel-stalls like Campaign 1.
