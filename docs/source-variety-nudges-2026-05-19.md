# Source variety and reliability — proposed nudges

Date: 2026-05-19 (revised 2026-05-21 after Codex review)

## The problem in one paragraph

Specialists end up leaning on a small handful of sources — typically Google Maps plus one or two local news portals — even when better, more official sources exist. Two things drive this: the agent doesn't have a clearly named set of source families to reach for, and the prompts don't currently push it to _diversify_ the sources it actually uses in a report. The result is research that looks thin and reads as if the agent only opened a couple of tabs.

## What we'll change

Four prompt edits, no code change. They work as a chain: name the source families, ask the Lead to push them into briefs, gate the answer on variety, and add an observability hook so the variety check is actually enforceable. A fifth code-level change is sketched at the end as a follow-up.

**Tools available today**: public-web specialists (the ones answering open research questions — `market_landscape`, `guest_intelligence`, `menu_pricing`, `marketing_brand`, `location_traffic`, `operations`, `revenue_sales`, dynamic researchers) use Gemini-native Google Search plus URL Context — the latter lets the model open a page and read its contents. Two specialists have narrower, structured-provider toolsets:

- `review_analyst`: `search_serpapi` (used to find a TripAdvisor URL for the venue and to read TripAdvisor profile facts that appear in the SerpAPI snippet — rating, ranking, total review count), `get_tripadvisor_reviews(url)`, `get_google_reviews`.
- `social_analyst`: `search_serpapi`, `url_context` (used only to verify a discovered URL belongs to the right venue), `fetch_tripadvisor_page`, `fetch_facebook_page`, `fetch_facebook_posts`, `fetch_instagram_profile`.

The variety rule below applies to public-web specialists only — structured-provider specialists already have a narrow, prescribed source surface and shouldn't be asked to span "three categories." Note that `social_analyst` has `url_context`, but its body file scopes that tool to URL verification, not to open public-web reading.

---

## Change 1 — Rewrite `market_source_profiles.md`

**What this file is**: a single markdown file that gets injected into the Research Lead's prompt at the start of every research session. The Lead reads it and uses it to decide which source families to ask specialists to investigate.

### What's there today

The file has a "Source Order" list (six tiers: direct tools → official → venue-owned → local firsthand → public platforms → industry reports) followed by one big table with four columns per market: _Official and primary · Platforms to try · Jobs and costs · Local qualitative_.

Industry research bodies that _are_ in the file today (UKHospitality, National Restaurant Association, DEHOGA) sit awkwardly inside the "Jobs and costs" column, so they're easy for the Lead to overlook when the question is about benchmarking or trends. Food bloggers and review sites are lumped into a vague "Local qualitative" bucket. There's no statement that variety is required.

### What changes

Restructure into **eight named categories** so industry research and review sites are visible as their own buckets, not buried:

1. Official & statistical
2. Industry research & benchmarks
3. Restaurant review sites & critics
4. Food bloggers & community
5. Local press
6. Delivery & reservation
7. Jobs, wages & costs
8. Currency & language

Per market (PL, UK, US, DE), give **2–3 named seeds per category**. Two to three is the sweet spot — enough to give the model search vocabulary without it treating the list as a closed set. Above that, the model starts overfitting to the named entities.

Add seeds the current file lacks. UK industry research is a gap today: CGA, MCA Insight, Lumina Intelligence belong here. US industry research should add Technomic and the Toast Restaurant Industry Report alongside the NRA. PL needs PIH and Horecanet. DE needs Allegra and gv-praxis alongside DEHOGA.

Add a short header to the file that says, in plain language: these are seeds, not a checklist, and the report needs to draw from the categories the Lead briefs.

### From / to

**Today**, the relevant header of the file reads:

> Use this as source guidance, not a checklist. Source availability changes by city and by tool access. Mention only sources actually checked.

**Proposed**, the new header reads:

> Lists are **search seeds**, not a closed set and not a checklist. Use them to spark queries; discover comparable local sources when better ones exist.
>
> **Source variety matters.** For public-web research, draw from the source categories the Lead names in the brief. If a category turned up nothing material, say so.
>
> Cite only sources whose content was actually inspected via URL Context this turn. Do not cite a named source you did not open.

### Why

The categories make the source surface visible, so the Lead has concrete families to push into briefs. The variety statement is deliberately scoped to "the categories the Lead names" rather than a hard "at least three" — that scopes the rule correctly (structured-provider specialists are exempt because their briefs won't name three public-web categories) and removes the fixed-minimum framing that the model could hand-wave past.

The "cite only what you inspected" line is the most important guardrail. Without it, the agent occasionally name-drops sources it never actually opened, because the named seeds are sitting right there in the prompt. Citation hallucination is a measured failure mode of deep-research agents — naming sources without ensuring they get read makes it worse.

---

## Change 2 — Add a source-variety line to `research_lead.md`

**What this file is**: the prompt for the Research Lead, the agent that plans the research and writes the brief each specialist receives.

### What's there today

The Specialist Briefs section lists what to include in each brief: the user question, target, evidence surface, causes, counter-signals, boundaries, market-source expectations. The wording around source expectations is currently tucked into the Boundaries bullet:

> Boundaries: what not to cover and relevant market-source expectations.

That's all the source guidance the Lead pushes into specialist briefs today. It's vague — "relevant market-source expectations" could mean anything, and in practice the specialist often interprets it as "use whatever Google surfaces first."

### What changes

Add one line under the existing brief checklist that explicitly tells the Lead to name source categories in each brief:

> When briefing a public-web specialist, name 2–3 specific source categories the brief should hit, calibrated to the question. For benchmarking, sizing, or regulation questions: official statistics + industry research + named press. For sentiment, openings, closures, or concept questions: review sites + food bloggers + local press. Source seeds are starting points — encourage the specialist to start with broad queries and discover comparable sources.

The "public-web specialist" qualifier matters — structured-provider specialists (`review_analyst`, `social_analyst`) don't need this; their tools define their source surface.

### From / to

**Today**, the Specialist Briefs section ends with:

> - Any table or comparison needs for this task.
>
> Frame briefs as investigation. Do not ask specialists to confirm the user's premise.

**Proposed**, one line is added between those two:

> - Any table or comparison needs for this task.
> - **Source-category expectations (public-web specialists)**: name 2–3 categories the brief should hit (e.g., "official statistics + industry research + named press"). Source seeds are starting points; encourage broad queries first and discovery of comparable sources.
>
> Frame briefs as investigation. Do not ask specialists to confirm the user's premise.

### Why

This is the bridge between the source profile (which the Lead reads) and the specialist (which acts on the brief). Without this line, the new source profile sits in the Lead's context but doesn't reach the specialist as a specific instruction. With it, every public-web brief carries a concrete "go look in these three categories" instruction — turning the Lead from a passive reader of the profile into an active dispatcher of source expectations.

---

## Change 3 — Add a variety check to the Lead's Sufficiency Check

**What this is**: a checklist the Lead runs at the end of research to decide whether the evidence is good enough to write the report, or whether one more focused round is needed.

### What's there today

The Sufficiency Check section has ten bullets covering things like: did premise tests get tested, did at least two specialists cover distinct surfaces, are claims backed by read pages, what counter-signals exist, what source gaps remain. There's nothing about source _variety_ — a public-web specialist that returned a report based entirely on Google Maps and one local site passes the current checks as long as its core surface is covered.

### What changes

Add one bullet to the Sufficiency Check:

> - For public-web evidence surfaces: did material evidence span the source categories named in each brief, or are missing categories stated?

If the answer is "missing categories not stated," the Lead runs a focused extra round with a brief that names the missing categories explicitly.

This is the key observability fix Codex flagged. The check works only because of Change 4 — the specialist labels each source with its category in `Evidence Notes`, so the Lead can mechanically read the labels rather than having to infer category from domain. Without the labels, the model could hand-wave the check by claiming variety without showing it.

### From / to

**Today**, the Sufficiency Check bullets include:

> - What source gaps, stale evidence, weak sources, or access failures should be stated?
> - Has at least one dynamic researcher deepened a material cause, trend, reason, relationship, mechanism, or target implication?

**Proposed**, one bullet is inserted between them:

> - What source gaps, stale evidence, weak sources, or access failures should be stated?
> - **For public-web evidence surfaces: did material evidence span the source categories named in each brief, or are missing categories stated?** If missing categories are material, run a focused extra round with a brief that names them.
> - Has at least one dynamic researcher deepened a material cause, trend, reason, relationship, mechanism, or target implication?

### Why

This is the enforcement loop. The category-naming in Change 2 is a pre-flight expectation. Change 3 is the post-flight gate. Without it, a public-web specialist that returns Google-Maps-only evidence still passes through to the report writer, and the rest of the changes don't bite. With it — combined with the Evidence Notes labels from Change 4 — the Lead has a mechanical, observable reason to re-dispatch.

The bullet is scoped to public-web surfaces so it doesn't misfire on `review_analyst` or `social_analyst`, which have their own evidence surfaces shaped by their tools. The "named in each brief" framing keeps the check tied to what the Lead actually asked for, instead of imposing a global "three categories" rule that wouldn't apply uniformly.

---

## Change 4 — Sharpen `specialist_base.md` and add source-category labels

**What this file is**: `specialist_base.md` — the universal contract that every specialist inherits.

### What's there today

Inside the Process section, two lines currently set the default source preference:

> - Prefer primary or official sources for numbers, laws, wages, business facts, and demographics.
> - Prefer local firsthand sources for local sentiment, openings, closures, neighborhood dynamics, and weak signals.

Both lines use "Prefer" — which is soft. "Prefer X" leaves the specialist plenty of room to use whatever's at the top of the Google results and call it good enough. Neither line names what "primary or official" or "local firsthand" actually look like.

The file also has an `Evidence Notes` section the specialist fills in at the end of every report. It already asks for "Sources read," "Structured provider data," "Search or grounding-only signals," "Evidence gaps," and "Key claims" — but doesn't ask the specialist to label which _category_ (from the eight in the source profile) each source falls into.

### What changes

**Two edits**, in the same file.

**4a. Replace lines 29–30** with three sharper lines:

> - When the brief involves numbers, sizing, benchmarks, regulation, or structural claims, **lead with official statistical offices, trade associations, and industry research/trade press**. Named seeds in the brief are search vocabulary, not a closed set.
> - When the brief involves sentiment, openings, closures, or concept reception, **lead with named review sites, named critics, and food bloggers**. A report drawn from Google Maps plus one local outlet is too narrow — when material public sources exist, draw from the categories the Lead briefed.
> - **Cite only sources whose content was inspected via URL Context or a structured provider tool this turn.** Do not name a source you did not open.

**4b. Add to the Evidence Notes checklist** (in the same file):

> - **Source category**: for each material source listed under "Sources read" or "Structured provider data," label which source category it belongs to (e.g., _official & statistical_, _industry research_, _review site_, _food blogger_, _local press_, _delivery platform_, _social platform_).

The labeling is universal — every specialist uses it — but the _variety check_ in `research_lead.md` (Change 3) only fires for public-web specialists. Structured-provider specialists just label what they cite (e.g., "TripAdvisor URL — review platform") so the Lead can read the surface at a glance; they aren't held to a multi-category bar.

### From / to

**Today** (lines 29–30):

> - Prefer primary or official sources for numbers, laws, wages, business facts, and demographics.
> - Prefer local firsthand sources for local sentiment, openings, closures, neighborhood dynamics, and weak signals.

**Today** (Evidence Notes section, lines ~100–106):

> - Sources read: pages, articles, listings, reports, menus, PDFs, or forum threads whose content was available. Name the source and URL when available.
> - Structured provider data: Google Places, Google Reviews, TripAdvisor, delivery-platform, or other tool-backed records used as evidence. Include provider/place IDs when they are the only stable reference.
> - Search or grounding-only signals: useful results, snippets, or source metadata that were discovered but not read. Use these as weaker context, not as full evidence.
> - Evidence gaps: relevant pages that were blocked, stale, ambiguous, snippet-only, unavailable, or contradicted by read material.
> - Key claims: for important findings, state whether the basis is read page content, structured provider data, search/grounding signal, estimate, or inference.

**Proposed** — the three sharper lines replace 29–30, and one new bullet is added to Evidence Notes:

> - Source category: for each material source under "Sources read" or "Structured provider data," label which source category it belongs to.

### Why

The sharpened "lead with…" lines name the source categories explicitly so the specialist has a concrete target. The named failure pattern in the second line is a deliberate diagnostic — evidence on positive-vs-negative framing is mixed (Anthropic and Google generally prefer positive framing, but warnings can work when paired with the desired behavior). The phrase appears once in the runtime prompt, not in multiple prompts, so priming risk is limited.

The Evidence Notes label is the load-bearing piece. It turns the sufficiency check (Change 3) from a soft self-assessment the model could hand-wave past into a mechanical inspection — the Lead can read the labels and see whether one specialist's evidence collapsed to a single category. This is the observability hook that makes the rest of the chain actually enforceable.

---

## Change 5 — Per-market injection (follow-up, should ship close behind 1–4)

**What this is**: a code change, not a prompt change. Today, the _full_ `market_source_profiles.md` is injected into every research session — all four markets' sources sit in the Lead's prompt regardless of whether the target restaurant is in Poland or the US.

### Why this becomes more pressing once Change 1 lands

Change 1 expands the file: from a compact four-column table to eight categories × four markets × 2–3 seeds per category — material growth. Until Change 5 lands, every Lead prompt carries all four markets' worth of seeds, and the wrong-market noise increases. The behavioral win from changes 1–4 still applies, but the Lead working on a Berlin question is staring at PL/UK/US seeds too — and can occasionally pull seeds from the wrong market.

The mitigation: keep the per-category seed lists tight (2–3 each, no creep), and ship Change 5 soon after — ideally in the next agent shipment, not as a long-term follow-up.

### What it would look like

Detect the target restaurant's country from the Google Places `addressComponents` field (which returns ISO codes like `PL`, `GB`, `US`, `DE`). Store it in session state. When building the Lead's prompt, load only the relevant market's section plus a small "global" block (Statista, Euromonitor, Michelin). Markets outside PL/UK/US/DE get a structure-only fallback — the eight categories, no named seeds.

### Prerequisites

`addressComponents` is not in the current `DETAIL_FIELDS` request in `places_tools.py` — the Places client doesn't ask for it today, so it isn't in the cached place record. Three concrete code changes:

1. `places_tools.py:33` — add `addressComponents` to the `DETAIL_FIELDS` list.
2. `place_state.py:upsert_google_place` — extract the country code (the `addressComponents` entry whose `types` contains `"country"` → `shortText`) and store it as `country_code` on the place record. Do _not_ write `target_market` here — `upsert_google_place` runs for competitors too.
3. `place_state.py:set_original_target_once` — when target identity is first established, copy `country_code` from the target's record into `state["target_market"]`. Single-write, target-scoped.

Then in `agent.py`, the Research Lead instruction provider reads `ctx.state.get("target_market")` and slices the profile via a small `market_profiles.profile_for(market)` helper that returns market-block + global-block (or fallback-block + global-block if unknown).

---

## A known limitation worth naming

The "cite only what was opened" guardrail (Changes 1 and 4) is a _prompt-level_ rule about what the specialist writes in its report prose. It does not change what shows up in the source-drawer pills the user sees. Source pills today are accumulated from grounding/search metadata into turn-level sources regardless of whether the page was actually opened via URL Context — that's product plumbing (`firestore_events.py`, `ChatThread.svelte`) and lives outside this plan.

What this means practically: after these changes, the specialist's _prose_ should stop name-dropping unopened sources, but the _source drawer_ may still surface a wider set of pills than the specialist actually inspected. If that gap matters for the product story, it's a separate fix to the source-pill pipeline.

---

## What happens after these ship

If 1–4 land and work as intended, specialist reports should look different in two visible ways. First, they'll cite more _kinds_ of sources — official statistics alongside trade press alongside review sites, rather than three Google Maps URLs and one local news article. Second, the Evidence Notes section in each specialist report should show a labeled mix of source categories — which is what makes the Lead's sufficiency check enforceable rather than aspirational.

If reports still look thin after these changes, the most likely cause is the model not actually opening enough URLs via URL Context — that's a search-tool-usage issue, not a source-list issue, and is a separate fix. The variety-and-reliability lever lives in the prompt; the depth-of-reading lever lives in tool prompting and is already addressed in `specialist_base.md`'s Search And Source Reading section.

---

## Files that change

- `agent/superextra_agent/instructions/market_source_profiles.md` — full rewrite to eight categories, 2–3 seeds per category per market, new header.
- `agent/superextra_agent/instructions/research_lead.md` — one line added to Specialist Briefs, one bullet added to Sufficiency Check.
- `agent/superextra_agent/instructions/specialist_base.md` — two lines (29–30) replaced with three; one bullet added to Evidence Notes.

No code changes for 1–4. Change 5 would touch `places_tools.py`, `place_state.py`, and `agent.py` and would land in a separate shipment.

## Tests worth adding when 1–4 ship

- Instruction provider test: assert the new content lands in the rendered Research Lead prompt — the eight category headers, the new "Source-category expectations (public-web specialists)" brief bullet, and the new "For public-web evidence surfaces" sufficiency-check bullet. (Format-correctness of `_research_lead_instruction` is already covered by existing tests.)
- Specialist base test: assert `specialist_base.md` renders the three sharper "lead with…" / "cite only what you inspected" lines and the new Evidence Notes "Source category" bullet.
- Smoke test: run one PL and one UK research session, check that each public-web specialist's Evidence Notes labels at least three distinct source categories when material public sources exist.
