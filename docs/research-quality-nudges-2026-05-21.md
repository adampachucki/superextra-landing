# Research-quality nudges - revised plan

Date: 2026-05-21  
Revised: 2026-05-23 after `816affc`, model-owned intake, and the committed
dynamic-specialist minimum changes

## What this is

Prompt-level changes to lift report structure, venue/brand framing, website
coverage, public-recognition coverage, and competitor framing.

This revision replaces the original six-nudge plan. The direction is still
valid, but recent commits changed the operating surface:

- `8738e24` shipped source-variety and source-reliability nudges.
- `97e94dd` fixed a re-dispatch regression from that shipment and unified
  `Evidence Notes` around category-first source groups with inline access
  labels: `read`, `provider`, and `signal`.
- `8b9ad13` added selected-focus handling for target venue, site/area focus,
  and broader market questions. `context_enricher` can now build site/area
  context without inventing a target restaurant, and `research_lead` now briefs
  specialists on active scope.
- `9fb384a` / `c7c354a` added the first direct clarification path and stricter
  branch ambiguity rules. `10452d0` through `816affc` then replaced that
  pre-router/place-resolver design with model-owned intake in
  `functions/intake-agent.js`. Intake can ask concise clarification questions,
  call Google Places Text Search to validate or disambiguate restaurants,
  persist candidate options, and start Agent Engine with a standalone
  `researchQuestion` plus optional selected `placeContext`.
- `8b9ad13` / `c7c354a` also landed the nearby-vs-broader-benchmark separation
  in `context_enricher.md` and `research_lead.md`.
- `9f3ca19` tightened visible thought-summary wording across prompt files. Plan
  edits should not loosen it or add progress examples that use bullets,
  tables, citations, source lists, tool names, agent names, or implementation
  labels.
- `c39879e` kept responsive markdown-table rendering and added raw-HTML
  escaping. Report-table guidance should mean markdown tables only, not custom
  HTML tables or HTML-based formatting.
- `2eee297` and `cf6c475` relaxed Research Lead dynamic-researcher usage from
  mandatory to conditional. The Lead now requires at least two specialists for
  every research report, and a dynamic researcher can count when its brief owns
  a distinct deeper angle or evidence surface. Do not reintroduce an always-run
  dynamic pass or a hard "two non-dynamic specialists" minimum.
- `social_analyst` remains a structured-provider specialist for TripAdvisor,
  Facebook, and Instagram. Its SerpAPI tool is for URL discovery, not general
  platform-presence research.
- `context_enricher` remains Google Places-only. It does not have
  `google_search` or `url_context`.

The revised plan therefore keeps the root quality goals but moves work to the
right owners and avoids new evidence-label conventions or tool expansion.

## Why now

We compared the same prompt across Superextra, Claude, ChatGPT, and Gemini:

> analyze online presence and marketing efforts of Umami (Prenzlauer Berg) -
> which platforms they use, which they don't, how popular they are vs
> competitors

Observed gap:

- Superextra had stronger investigative texture: named PR agency, celebrity
  launch signals, dated review-moderation evidence, cross-source operational
  disconnects, review velocity, owner-response rates, and a clear TripAdvisor
  decline call.
- Claude had stronger structure and coverage density: multi-account Instagram
  inventory, per-location TripAdvisor breakdown, competitor table, tech-stack
  and website-feature inventory, awards, and explicit "not visible / not used"
  findings.

The goal is to close the structure and coverage gap without weakening
Superextra's source-grounded research behavior.

## Current constraints that shape the fix

- `report_writer.md` already preserves detail and can render markdown tables,
  but tables receive much less prompt surface than charts.
- `marketing_brand.md` already owns web presence, search presence,
  platform presence, public ads, PR, and brand positioning. It is the correct
  owner for website feature inventory, public recognition, and visible channel
  absences.
- `research_lead.md` owns specialist selection, source-category expectations,
  and whether a second round is needed. After `97e94dd`, do not add wording
  that directly tells the Lead to re-dispatch only for missing source-category
  labels; the existing focused-extra-round rule already governs that.
- `research_lead.md` already asks briefs to state whether active scope is a
  target venue, site/area focus, or broader market question, and to avoid
  forcing venue-bound review/social analysis for area/site prompts.
- `research_lead.md` treats dynamic researchers as conditional deepening, not a
  required stage. Quality nudges should improve the assigned evidence surfaces
  first and leave dynamic usage to the Lead's sufficiency check.
- `functions/intake-agent.js` now owns fast pre-research conversation,
  clarification, Google Places lookup for typed place answers, candidate
  memory, and construction of the standalone research question passed to Agent
  Engine. Agent prompts should not duplicate that intake responsibility.
- `specialist_base.md` already has the access-tier convention:
  `read` = URL Context inspected, `provider` = structured tool returned data,
  `signal` = search/grounding snippet only. Do not introduce `[snippet-only]`
  or `[unverified]` as a competing convention.
- Visible thought summaries now have a strict concise format. Do not add
  prompt text that encourages progress bullets, source lists, citations,
  internal labels, or mini-reports in live progress.
- `context_enricher.md` builds Places context only. It should not perform web
  research, and `search_restaurants` is Places Text Search, not general web
  search.
- `context_enricher.md` already separates nearby direct alternatives from
  broader named/category-leading comparables and records ambiguous same-brand
  or same-chain lookups without choosing by prominence, rating, review count,
  or result order.
- `social_analyst.md` is intentionally narrow: structured TripAdvisor,
  Facebook, and Instagram page/profile data. Broad channel discovery belongs
  to `marketing_brand`; delivery/menu details belong to `menu_pricing`;
  qualitative comments belong to `guest_intelligence`.

## Revised changes

### 1. Make tables a first-class report shape

**Owner**: `agent/superextra_agent/instructions/report_writer.md`

Strengthen the existing table line near Report Shape. Keep it directional, not
a schema, and do not add a duplicate table rule:

> Prefer markdown tables for multi-entity, multi-metric comparisons when they
> preserve detail more clearly than prose. Use prose when the comparison is
> mostly explanatory or causal.

Why: the UI already supports responsive markdown tables, and raw HTML is now
escaped by the markdown renderer. The writer already uses charts only when
numeric data benefits from visualization. This gives markdown tables equal
legitimacy without adding table-trigger heuristics or custom HTML output.

Tests:

- Update the report-writer instruction-provider test to assert the table line
  renders.
- No UI test required; markdown table rendering is already covered.

### 2. Move brand/group context to the Research Lead and marketing surface

**Owners**:

- `agent/superextra_agent/instructions/research_lead.md`
- `agent/superextra_agent/instructions/marketing_brand.md`

Do not relax `context_enricher` into web research.

Add a small Lead briefing rule, scoped to verified targets or evidence-backed
brand findings:

> If evidence suggests a verified target venue is part of a multi-location
> brand or group, brief relevant specialists to separate location-level facts
> from brand-level activity. Treat the group as context when it changes
> marketing, platform, reputation, pricing, or competitor interpretation.

Add a marketing-brand evidence cue:

> Check whether the venue appears to operate as one location of a wider brand
> or group. If so, separate brand-level marketing assets from location-specific
> evidence.

Why: chain/group membership is often a web and brand-context question, not a
Places-enrichment question. Moving it to the Lead and marketing surface keeps
the Places stage clean and gives downstream specialists the correct framing
when the evidence supports it.

Guardrail: this must not weaken intake or branch-ambiguity handling. A chain or
brand name plus broad geography is not enough branch-level scope for
branch-proximity questions. Do not use brand/group context wording to make
specialists pick a branch that intake, the router, or the enricher left
ambiguous.

Tests:

- Assert the Lead prompt contains the brand/group briefing rule.
- Assert `marketing_brand` renders the brand-vs-location evidence cue.

### 3. Replace broad `social_analyst` platform probing with marketing-owned channel visibility

**Owner**: `agent/superextra_agent/instructions/marketing_brand.md`

Do not expand `social_analyst` to Wolt, Lieferando, Uber Eats, Yelp,
OpenTable, YouTube, TikTok, LinkedIn, HappyCow, or other platforms. Its current
tool contract is structured TripAdvisor/Facebook/Instagram page data.

Instead, add a marketing-brand process cue:

> For channel visibility, use search and accessible public pages to inventory
> the venue's visible owned, discovery, reservation, delivery, PR, and social
> surfaces. Report channels as checked public signals, not as definitive
> private channel usage. Label search-only findings as `signal` in Evidence
> Notes.

Why: this keeps structured social stats separate from broader marketing
presence. It also reuses the Evidence Notes convention shipped in `97e94dd`
instead of creating a new snippet-label format.

Tests:

- Assert `social_analyst` still does not mention TikTok or broad platform
  probing.
- Assert `marketing_brand` includes channel visibility and `signal` wording.

### 4. Make website feature inventory explicit in marketing_brand

**Owner**: `agent/superextra_agent/instructions/marketing_brand.md`

Add a concise process cue:

> When a primary venue or brand website is available, inspect it. Inventory
> visible owned-funnel features such as booking, ordering, delivery links,
> newsletter, loyalty, gift cards, events, press, blog/news, locations, and
> social links when they are material to the brief. Call out notable absences
> only as "not visible in checked public surfaces."

Why: the original gap was not simply "fetch the website"; it was failure to
turn the website into an operator-useful feature inventory and absence map.
The absence wording prevents overclaiming private/non-public channel usage.

Do not add Jina or `fetch_web_content` to default specialists for this change.
`fetch_web_content` remains a dedicated exact-URL/raw-page tool, and website
fetching improvements are already listed as a deferred stream in
`AUTHORING.md`.

Tests:

- Assert the marketing-brand prompt includes website feature inventory wording.
- Run one live smoke after deployment where the target website is publicly
  readable and check that the final report carries feature presence/absence
  without claiming private non-use.

### 5. Add public-recognition checks to marketing_brand

**Owner**: `agent/superextra_agent/instructions/marketing_brand.md`

Add:

> Check for public recognition when it is relevant to the venue's positioning:
> guide listings, awards, critic recognition, platform badges, and local press
> honors. Mention only recognition actually found in checked public evidence.
> If none is found, omit the section unless absence itself affects the answer.

Why: awards, guides, and badges are brand-positioning and reputation assets.
They are not owned by review analysis unless the signal comes from structured
TripAdvisor/Google review data.

Tests:

- Assert the marketing-brand prompt contains public-recognition wording.
- Include one smoke prompt where known public recognition exists and one where
  it likely does not; the second should not pad the report.

### 6. Reframe competitor selection without adding a second discovery system

**Owners**:

- `agent/superextra_agent/instructions/context_enricher.md`
- `agent/superextra_agent/instructions/research_lead.md`

Status: landed by `8b9ad13` / `c7c354a`. Keep the Places context primarily
local and preserve the existing clarification:

> For competitor context, nearby direct alternatives are primary. Also consider
> search_restaurants for named or category-leading comparables when the user's
> question explicitly needs broader benchmarking. Keep nearby competitors
> separate from broader comparables.

Preserve the existing Lead briefing cue:

> When broader benchmarks matter, keep nearby competitors and destination-level
> comparables separate in specialist briefs and in table requests.

Why: destination restaurants can be meaningful comparables, but mixing them
with the local walking-distance set causes bad framing. The fix is not a new
two-tier discovery architecture; it is explicit separation between local
competitors and broader benchmarks.

Remaining work: no additional prompt change unless smoke tests show the new
wording is not carrying through to specialist briefs or final tables. The
quality-nudge implementation should not duplicate or expand this rule.

Tests:

- Preserve existing assertions that the enricher says "Use Google Places tools
  only", can treat Place IDs as target/site/area focus, separates nearby
  competitors from broader comparables, and does not pick among ambiguous
  same-chain candidates by prominence.
- Preserve existing assertions that the Lead asks to separate nearby
  competitors from broader benchmarks and does not force venue-bound
  specialists for area/site prompts.
- Preserve intake tests that typed clarification answers can resolve to a
  Place ID, ambiguous candidates are remembered, and the research question
  remains a complete standalone request.

## Implementation order

1. `report_writer.md` table parity, plus Lead table requests for comparison
   briefs when the user explicitly asks "which / vs / compared".
2. `marketing_brand.md` website inventory, channel visibility, public
   recognition, and brand-vs-location wording.
3. `research_lead.md` brand/group briefing only.
4. Preserve the already-landed `context_enricher.md` and `research_lead.md`
   competitor-scope wording; do not rework it unless smoke tests fail.

This order ships the highest-confidence quality improvements first and avoids
touching the most brittle boundary (`context_enricher`) without evidence that
the landed wording fails.

## Verification

### Latest Smoke Result

The 2026-05-23 live smoke found no intake, handoff, Firestore, or terminal
report regression:

- direct no-scope intake clarification completed in under 1 second;
- live intake matrix passed missing-area, area-follow-up, typed-venue,
  ambiguous-branch, remembered-candidate, broad-industry, and selected-place
  cases;
- the full Umami online-presence report completed with sources and covered
  Umami, platforms, competitors, and public-evidence caveats.

Observed gap: the full Umami report did not render a markdown comparison table
even though the prompt explicitly asked which platforms are used / not used and
how popularity compares with competitors. Treat table parity as confirmed
priority work, not optional polish.

Environment issue: `npm run test:evals` failed before assertions because local
ADC still produced Vertex tokens without the `cloud-platform` scope
(`ACCESS_TOKEN_SCOPE_INSUFFICIENT`). Direct scoped-token probes worked, so this
is a VM ADC setup issue, not a router result.

### Static tests

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/test_instruction_providers.py -v`
- Update assertions for every touched prompt.
- Preserve existing assertions that `social_analyst` does not mention TikTok
  and that default public-web specialists use native search + URL Context.
- Preserve the tightened thought-summary contract when touching prompt files.
- Preserve tests that the Lead requires at least two specialists, allows a
  dynamic researcher to count only when it owns a distinct deeper angle or
  evidence surface, and asks whether a dynamic pass would materially improve
  the answer instead of requiring one in every report.
- For intake-sensitive changes, also run
  `cd functions && npm test -- intake-agent.test.js index.test.js`.
- Fix VM ADC scope before relying on `npm run test:evals` as a smoke gate.

### Live smoke prompts

Run against the deployed engine after prompt deployment:

1. Umami Prenzlauer Berg online presence / marketing / platforms vs
   competitors, through the actual intake path, with and without an already
   selected place focus.
2. A single-location venue with a readable website and no obvious awards.
3. A multi-location restaurant group where brand-level social/website activity
   differs from location-level presence.
4. A local competitor-map prompt where nearby competitors and one broader
   destination benchmark should both appear but remain clearly separated.

Check for:

- competitor or platform comparisons rendered as tables when useful;
- website feature inventory and careful "not visible in checked public
  surfaces" absence language;
- recognition only when found in checked public evidence;
- category-first Evidence Notes with `read`, `provider`, and `signal` access
  labels;
- intake preserves the original marketing/platform question when it resolves a
  typed venue or asks the user to choose among candidate branches;
- no hard claims based only on search snippets;
- no `context_enricher` web research or social-analyst broad platform probing.

## Explicit non-goals

- Do not add new tools.
- Do not expose `fetch_web_content` or Jina to default specialists.
- Do not introduce a new `[snippet-only]` labeling convention.
- Do not broaden `social_analyst` beyond structured TripAdvisor, Facebook, and
  Instagram page/profile data.
- Do not make `context_enricher` a web-research agent.
- Do not reintroduce the deleted `pre-router` / `place-resolver` architecture
  or solve intake ambiguity inside downstream research prompts.
- Do not add platform lists, awards lists, chain-size buckets, or table-trigger
  heuristics to universal prompts.
