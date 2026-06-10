# Ads strategy — MVP validation campaign

High-level strategy for the first paid acquisition push. Tactics evolve weekly; this doc captures the durable shape.

## Goal of the spend

Validate **whether independent US restaurant operators (1–4 venues) will click on Superextra, sign up, and run a query that returns real value** — and identify which of the four hook pillars (where to open / how to price / when to hire / what's shifting) pulls hardest. This is a hook-validation budget, not a CAC-measurement budget.

The single number that decides success: **% of signups who run a second query within 14 days**. Above 25% = the proposition is delivering; below 15% = the product isn't worth the click and the hook isn't the bottleneck.

## Why US first

- Largest addressable audience (~412K independents)
- English-native, no localization debt before launch
- Most relevant playbook documented (Owner.com $2M → $40M+ ARR case study)
- Adam's network advantage in Poland is preserved for phase 2 (port the validated hook)

Germany is deferred indefinitely: SOUS just raised €4M in March 2026 targeting the same audience, UWG §7 makes cold channels legally hostile, and AHGZ-tier press placements eat half a budget for a single shot.

## Channels in scope

| Channel                     | In  | Why                                                                                       |
| --------------------------- | --- | ----------------------------------------------------------------------------------------- |
| Meta (Facebook + Instagram) | Yes | Largest reach for independent operators; cheapest creative iteration loop                 |
| Reddit promoted posts       | Yes | Operator-authentic audience in r/restaurateur and r/restaurantowners; cheap honest signal |
| Google Search               | No  | Keyword volume too thin for €500 to teach us anything in 30 days                          |
| LinkedIn                    | No  | 1–4 venue independent operators aren't there; LinkedIn is a chains/F&B-director surface   |
| Cold email                  | No  | Founder constraint: no personal outreach during this phase                                |
| Founder-led DMs             | No  | Same                                                                                      |
| Trade press                 | No  | $3K minimums per slot                                                                     |
| Podcasts                    | No  | 4–8 week attribution tail kills iteration speed                                           |

## Budget allocation — €500 over 30 days

| Bucket                     | Spend | Notes                                                                       |
| -------------------------- | ----- | --------------------------------------------------------------------------- |
| Meta Ads US                | €320  | 4 creatives × 4 weeks; expect 4–12 signups at $30–80 B2B SMB CPL            |
| Reddit promoted post       | €100  | $20/day × 5 days, geo-targeted to 3 cities                                  |
| Reserve for week 3–4 scale | €80   | Reallocate to whichever creative is winning                                 |
| Tools                      | €0    | PostHog/Clarity/MCPs all on free tiers; Cloud Function on existing Firebase |

Total realistic signups at this budget: 10–25. Enough to compare 4 hooks; not enough to estimate CAC with confidence. A follow-on €2–3K against the winning hook is needed before drawing CAC conclusions.

## Targeting

**Meta:**

- US, age 28–58
- Interests: Toast (POS), Resy, OpenTable, 7shifts, MarginEdge, Square for Restaurants — these are operator-side tools, not consumer-side
- Layer: "Small business owners" interest + job-title proxies ("Restaurant Owner", "Chef", "General Manager")
- Geography: **NYC + Austin + Charleston** to start — all three are restaurant-tech-receptive, dense with independents, and have brunch/dinner scenes that make the pricing hook concrete
- Exclude: F&B service workers, broad food enthusiasts, under-25 age bucket
- No lookalike audience yet (no seed list); build one after 50+ signups

**Reddit:**

- r/restaurateur, r/restaurantowners, r/smallbusiness
- Geo: same 3 cities
- Skip r/KitchenConfidential (cooks/chefs, not owners; promotional content gets removed)

## Operating cadence

**Daily 9am** — Claude Code Routine runs the morning digest:

1. Pulls yesterday's Meta + Reddit insights via the MCPs
2. Pulls BigQuery signup funnel data (or Looker Studio scheduled report)
3. Flags CPL changes >30%, dead creatives (CTR < median × 0.5), pages with bounce >70%
4. Drops a 5-bullet TL;DR into Slack/email with pause/dupe/scale recommendations

**End of week 1** — Pause the bottom 2 of 4 creatives. Duplicate the top winner with one variable changed (headline OR visual, never both).

**End of week 2** — Decision point. If at least one creative is converting at <$40 CPL and signups are running first queries, scale that one with the reserve budget. If not, the hook is wrong — pause, run 10 more operator calls, regenerate copy from transcripts, and relaunch with the new language.

**End of week 4** — Final read. Either we have a validated hook to scale into a €2–3K follow-on, or we have evidence the proposition isn't pulling and need to revisit positioning before more spend.

## Pre-launch checklist (week 0)

- Analytics stack live (see `analytics-implementation.md`) — without it, the €500 is wasted
- Footer trust signals — Polish entity, NIP/KRS, RODO privacy policy, EU data residency statement
- Free-tier mechanic — 3 lifetime researches per Google-signed-in account, with a "tell us what you want to research next" CTA at cap-hit
- UTM convention enforced — every ad URL templated with `utm_source / utm_medium / utm_campaign / utm_content`
- MCPs installed in Claude Code on the VM: PostHog/BigQuery query, Meta Ads (official `mcp.facebook.com/ads`), Resend, Notion or Airtable for hook backlog
- First 10 founder calls completed and transcribed (informs creative copy — see `messaging-direction.md`)

## Kill / scale thresholds

**Scale** if any single creative shows:

- Cost-per-signup < $40
- Signup → first query ≥ 40% within 48 hours
- **Second query within 14 days ≥ 25%**
- ≥3 unprompted "what does this cost?" replies via the cap-hit email gate

**Kill / re-think** if after 500 paid clicks:

- Cost-per-signup > $80 across all four creatives (positioning, not channel — fix the hook)
- Landing-page conversion < 1% (proposition isn't legible)
- < 20% of signups ever run a query (product friction or proposition isn't pulling)
- < 1% reply rate to the cap-hit email gate (the free tier isn't producing the conversation we need)

## Phase 2 — Poland (after a US hook validates)

When the US campaign produces one creative at <$40 CPL with second-query retention ≥25%, port that creative to Polish:

- Translate the validated hook, don't rewrite it
- Same landing structure, Polish copy
- System-prompt change so the agent answers in Polish when the question is Polish
- Meta + Google PL targeting; cold email is off the table under PKE 2024
- ~PLN 4,000 (~€950) over 4 weeks

Germany stays deferred until the proposition has revenue signal, not just engagement signal.

## What Claude does

This is the part most founders underuse. Patterns we'll lean on:

- **Daily digest routine** (above) — flags + recommendations, not raw numbers
- **Hook ideation passes** — feed competitor screenshots and operator-call transcripts, ask for 25 hook variants in literal operator language, critique with a "skeptical 12-year veteran" persona
- **Copy generation per concept** — 10 headlines × 10 primary texts × 5 CTAs in one batch, then narrow
- **Operator transcript → new hooks** — the single highest-leverage Claude pattern; weekly, after each new batch of founder calls
- **Natural-language BigQuery queries via MCP** — "show me signup conversion by utm_content over the last 7 days; flag any creative where first-query rate is below 30%"
- **Daily Reddit/X listening** — Claude pulls new posts from r/restaurateur, surfaces any new pain-phrasing patterns that should become hook variants
