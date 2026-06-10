# Messaging direction

How we talk about Superextra in ads, on the landing page, and in product copy. The specific ad creatives evolve weekly; the principles below are the constants.

## Core positioning

Superextra is an AI consultant for every restaurant. It synthesizes competitor, pricing, guest, delivery, and market signals into operator-ready answers about the four decisions that move the business:

1. **Where to open** (next venue, expansion, lease)
2. **How to price** (menu, drinks, promos, what to charge)
3. **When to hire** (staffing decisions, capacity for what's coming)
4. **What's shifting** around them (neighborhood pulse, market changes, who opened/closed)

Every campaign anchors to one of these four pillars. We don't run "general AI consultant" copy.

## The whitespace we own

Competitive ad analysis across ~150 active US restaurant-tech ads in May 2026: **no vendor is running paid creative on outward-looking intelligence.** Owner.com owns inward diagnostic (your own website's SEO), MarginEdge owns inward cost intelligence (your invoices), Toast IQ Grow owns marketing automation (your campaigns), Popmenu owns conversion (your menu page). Nobody owns _"what are my neighbors doing — and what should I do about it?"_

That's our lane. Every hook should reinforce it.

## Tone and voice

- Operator-to-operator. We talk like someone who's run a restaurant, not someone who sells software to restaurants.
- Specific over generic. _"The 4 brunch spots within 3 blocks of you"_ beats _"your local competitors"_. _"$3.40 average price increase last quarter"_ beats _"market pricing trends"_.
- Verbatim operator language. After the first 10 founder calls, hook copy should pull phrases directly from transcripts. Not paraphrased.
- AI is the engine, not the headline. We lead with the outcome (the answer), not with the technology that produces it. "AI" appears in the second line, not the first.
- Apple-style minimalism — no exclamation points, no superlatives, no fake urgency.
- "You/your" appears in ad copy because that's what ads need; we keep product copy product-focused as per brand guidelines.

## Hook pillars

Every campaign creative belongs to one of these four. The first two are likely strongest because they're the most concrete decisions an operator makes weekly.

### Pillar 1 — How to price

The most testable pillar. Pricing decisions are made monthly or weekly, the answer is checkable, and the "did we leave money on the table" feeling is universal.

Example directions:

- _"Are 4 brunch spots near you priced higher than yours? Find out in 30 seconds."_
- _"Your competitors raised prices this quarter. Did you?"_
- Anti-MarginEdge framing: _"MarginEdge tells you your costs. Superextra tells you what to charge."_

This pillar produces the most testable single-input experience: an operator types their restaurant, gets a real competitor pricing comparison, sees the value immediately.

### Pillar 2 — What's shifting around them

The clearest whitespace claim. Nobody else runs ads framed as "neighborhood pulse for operators."

Example directions:

- _"3 new restaurants opened within 5 blocks of you this month. Want to know which ones — and which two closed?"_
- _"What's changing on your block?"_
- _"Who in your zip code just opened, closed, or pivoted?"_

Visual: map-pin, neighborhood-feeling, very local.

### Pillar 3 — Where to open

Highest-intent, smallest audience. Operators thinking about expansion are a fraction of the total, but they're the most willing to engage with a real consultant.

Example directions:

- _"Open your next location with data, not gut."_
- _"Sign the lease only after you know these 5 things about the block."_
- _"The hardest decision in restaurant ownership. Free to ask Superextra."_

Best used in week 3–4 once we have a working core hook to fund this narrower one.

### Pillar 4 — When to hire

Timing-sensitive. Staffing decisions are weekly. Strongest when paired with neighborhood-pulse signal ("demand on your block is up 22% this month; are you staffed for it?").

Example directions:

- _"Demand pulse for your block, this month."_
- _"Over- or under-staffed for what's coming? Ask Superextra."_

May be too abstract for cold traffic; better suited to retargeting users who've already run a research.

## What we never say

- **"Bloomberg terminal for restaurants"** — operators don't carry that mental model. No vendor uses it. Buried.
- **Anti-third-party-fees framing** ("stop paying 30%") — Owner.com, ChowNow, and Sauce own this. Saturated.
- **"Free AI diagnostic of your online presence"** — Owner.com's `grader.owner.com` runs daily and owns this lane. Don't enter head-on.
- **"AI does the work for you" / "less busywork"** — Toast IQ Grow and Popmenu live here. Generic, saturated.
- **"All-in-one platform replaces your stack"** — every POS vendor runs this. Generic.
- **"Revolutionize your restaurant"** or any superlative — operator skepticism is the default state.

## Creative formats

The founder is not on camera. The dominant winning format in the category (operator first-person testimonial reel) is unavailable. Next-best formats, all confirmed working in the ad library:

1. **Static text-on-color with chat-bubble framing** — a single operator question rendered as if it's the user's input to Superextra. Clean, instant comprehension, fastest to produce.
2. **Screen-recording reel (9:16, captions burned in)** — the agent producing a real answer to a real question in under 10 seconds. Highest-effort but closest to the dominant video format. No human face needed.
3. **Stat-shock animation** — _"3 new restaurants within 5 blocks. 2 closed. 1 raised prices 14%."_ Numbers carry the creative.
4. **Split-card static for anti-positioning** — _"MarginEdge tells you costs. Superextra tells you what to charge."_ Used sparingly.

Aspect ratios per platform: 1:1 + 4:5 + 9:16 for Meta feed/reels/stories; 1:1 + 16:9 for Reddit.

## Landing surface

Per founder decision: we keep the existing agent page; the prompt area itself is the conversion surface. So messaging principles apply to the prompt area's onboarding:

- **Placeholder text in the prompt** should match the active campaign hook ("e.g., are 4 brunch spots near me priced higher than mine?")
- **Example chips below the prompt** rotate through one example per pillar — clicking pre-populates the prompt and submits
- **First-touch UTM determines which placeholder + chips appear** — a click from the "pricing" creative lands on a pricing-flavored prompt; a click from "neighborhood" lands on a shift-flavored prompt
- **Above-the-fold stat cards** once we have them: _"Restaurants in Austin used Superextra to find a $4.20 pricing gap. Ask yours."_ — real numbers from real operators, rotating like Popmenu's cards
- **Footer trust signals** as detailed in `analytics-implementation.md`

## Operator-language pipeline (do this before scaling spend)

The single most important pre-launch step. Adam Guild's "30% fees" hook at Owner.com wasn't invented — it was what restaurant owners told him three separate times before he believed them. We replicate the same listening loop:

1. Run 10 founder calls with operators from existing network (not paid acquisition). 20 minutes each.
2. Record and transcribe via ElevenLabs (already in stack).
3. Feed transcripts to Claude with a fixed prompt:
   - _Extract the three biggest pain phrases in their literal words_
   - _Extract any pricing/competitor signal they leaked_
   - _Extract any objection to a Superextra-like product_
   - _Produce two new hook variants per pillar in their literal language_
4. Pull the verbatim phrases into the hook backlog (Notion or Airtable, MCP-managed).
5. The first round of ad creative uses these phrases. Not Claude-invented copy. Not founder intuition. Operator words.

Run this loop again every two weeks during the campaign with the next batch of conversations from white-glove track signups.

## Phase 2 — Poland (porting)

When a US hook validates, translation, not reinvention. The semantic shape transfers (pricing, neighborhood, expansion, hiring); the language doesn't. Polish operators respond to:

- Founder voice (Adam is Polish — peer-to-peer beats anything else)
- Specific local examples ("twoja konkurencja na Saskiej Kępie")
- Anti-AI-hype framing ("bez bullshitu o AI, po prostu narzędzie które odpowiada")

The Polish operator-language pipeline runs separately: 10 Polish founder calls, separate transcript pass, separate hook backlog. Don't translate the US verbatim phrases — capture Polish operators' own.

## What gets reviewed weekly

- The hook backlog (Notion/Airtable)
- The bottom 2 creatives in the live Meta set (kill candidates)
- Reddit thread comments on the active promoted post (operator-language signal)
- The cap-hit email gate replies (highest-signal qualitative data we'll get)
