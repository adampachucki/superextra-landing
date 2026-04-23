# Topic pills hydration-order fix — plan

**File:** `src/lib/components/restaurants/TopicPills.svelte`
**Status:** proposed, not yet implemented
**Date:** 2026-04-23 (revised after review)

## Problem

On a hard refresh of `/agent`, the reshuffle button appears **before** the topic pills, instead of after them. The staggered entrance animation is supposed to cascade left-to-right across six pills and land on the button last. On refresh, that order is broken.

The issue is only visible on hard refresh. Soft client-side navigation from the landing page hides it.

## Root cause

The `/agent` route is prerendered (`src/routes/+layout.ts` has `export const prerender = true`).

`TopicPills.svelte` initializes with:

```ts
let topics = $state<TopicPillItem[]>([]);

onMount(() => {
	topics = pickPills(PILL_POOL, VISIBLE_COUNT, isMobile);
});
```

`onMount` runs only on the client, never during SSR. So the prerendered HTML that ships to the browser contains:

- the container `<div>`
- zero pill buttons (the `{#each topics}` iterates an empty array)
- the shuffle button (rendered unconditionally after the `{#each}`)

Verified in `.svelte-kit/output/prerendered/pages/agent.html`: 1 `shuffle-btn`, 0 `topic-pill`.

CSS animation timers start at element paint time, not at JS execution time:

- The button is in the initial HTML → its `animation-delay: 700ms` counts from **t=0** (first paint).
- Pills are inserted by Svelte only after hydration + `onMount` → their timers count from **t=onMount**.

Rough timeline on a cold refresh where hydration takes ~500ms:

| element              | starts fading      | fully visible |
| -------------------- | ------------------ | ------------- |
| shuffle button       | t=700ms (absolute) | t=1400ms      |
| pill 1 (delay 350ms) | t=500+350=850ms    | t=1550ms      |
| pill 6 (delay 600ms) | t=500+600=1100ms   | t=1800ms      |

The button appears ~150ms before the first pill. Exactly the reported bug.

The authorial mistake is the delay arithmetic (`350 + VISIBLE_COUNT * 50 + 50`): it assumes all elements share one animation clock. They don't — the button's clock is tied to SSR paint, the pills' clock is tied to hydration.

## Goal

Kill the root cause, not the symptom. Make pills and button share one animation clock by SSR-ing both. Simplify the component along the way — the current code has two branches of nearly identical markup (`{#if pillGen === 0} ... {:else} ... {/if}`) because it conflates "first render" with "different animation style", and that split is scaffolding around the empty-initial-state bug.

## Decisions

### Initial pills are fixed, not random

The current random-on-first-load behavior is a side effect of populating state in `onMount`, not a deliberate product feature. Every approach that preserves per-visit randomness while fixing the bug costs either UX quality (re-render flicker after initial paint) or architectural complexity (split CSR/SSR, disable prerender, or build-time pseudo-randomness that isn't actually per-user). Fixed is materially simpler — no `onMount`, no hydration-time state change, one source of truth for initial state.

Reshuffle remains the way to explore variety. The editorial value is that every first-visit user sees the same curated six, which is what the hand-picked list was meant to achieve in the first place.

### The six, in wrap-balanced order

Six pills chosen for the first-impression narrative (market, traffic, trends, local performance, sentiment, pricing), run through the same short/long interleave `pickPills` uses so the flex-wrap rows aren't lopsided by label length:

1. **Who opened nearby** (17 chars) — shortest
2. **Who's getting the traffic** (25) — longest
3. **Emerging food trends** (20) — 2nd shortest
4. **Local market performance** (24) — 2nd longest
5. **What guests are saying** (22) — middle-short
6. **Lunch price positioning** (23) — middle-long

Expected layout at 750px container: 2 rows (3 pills + 3 pills + button), each row carrying one long and one short pill so neither row feels top-heavy. Mobile labels are all 11–13 chars (essentially uniform), so the desktop order also renders fine on mobile without a separate mobile ordering.

### No slide-up on reshuffle

Preserved from prior discussion. Initial load keeps the opacity + `translateY(8px)` slide. Reshuffle is opacity-only.

## Planned changes

Single file: `src/lib/components/restaurants/TopicPills.svelte`.

### 1. Remove `onMount`, pre-populate `topics` with a deterministic initial set

Replace:

```ts
import { onMount } from 'svelte';
// ...
let topics = $state<TopicPillItem[]>([]);

onMount(() => {
	topics = pickPills(PILL_POOL, VISIBLE_COUNT, isMobile);
});
```

with:

```ts
function byLabel(label: string): TopicPillItem {
	const p = PILL_POOL.find((x) => x.label === label);
	if (!p) throw new Error(`TopicPills: no pill with label "${label}"`);
	return p;
}

// Deterministic, wrap-balanced initial set. Order follows the same
// short/long interleave that pickPills applies on reshuffle, so flex-wrap
// rows stay balanced.
const INITIAL_TOPICS: TopicPillItem[] = [
	'Who opened nearby',
	"Who's getting the traffic",
	'Emerging food trends',
	'Local market performance',
	'What guests are saying',
	'Lunch price positioning'
].map(byLabel);

let topics = $state<TopicPillItem[]>(INITIAL_TOPICS);
```

The `byLabel` helper exists so a missing label throws a descriptive error at module load, not a silent `undefined.label` `TypeError` deep inside the each-loop.

### 2. Collapse the two template branches into one `{#key pillGen}` block

Current:

```svelte
{#if pillGen === 0}
	<div>... pills + button with hero-fade animation ...</div>
{:else}
	{#key pillGen}
		<div>... pills + button with topic-pill-shuffle animation ...</div>
	{/key}
{/if}
```

Both branches render the same structure. The only differences are the animation class and the delay arithmetic. Collapse into:

```svelte
{#key pillGen}
	<div class="...">
		{#each topics as topic, i (topic.label)}
			<div
				class={pillGen === 0 ? 'pill-fade-slide' : 'pill-fade'}
				style="animation-delay: {firstDelay + i * STAGGER}ms"
			>
				<button onclick={() => onPick(topic.query)} class="topic-pill ...">...</button>
			</div>
		{/each}
		<div
			class={pillGen === 0 ? 'pill-fade-slide' : 'pill-fade'}
			style="animation-delay: {buttonDelay}ms"
		>
			<button onclick={reshuffle} class="shuffle-btn ...">...</button>
		</div>
	</div>
{/key}
```

`{#key pillGen}` forces a DOM re-create on reshuffle so the animation replays. The conditional class swap preserves "slide on initial, opacity-only on reshuffle" without duplicating markup.

### 3. Keep two animations, unify stagger

Keep two CSS animations since they map to a real UX distinction (initial load earns the slide; reshuffle doesn't):

```css
.pill-fade-slide {
	animation: fadeInSlide 0.7s ease-out both;
}
.pill-fade {
	animation: fadeIn 0.6s ease-out both;
}

@keyframes fadeInSlide {
	from {
		opacity: 0;
		transform: translateY(8px);
	}
	to {
		opacity: 1;
		transform: translateY(0);
	}
}
@keyframes fadeIn {
	from {
		opacity: 0;
	}
	to {
		opacity: 1;
	}
}
```

Unify stagger arithmetic:

```ts
const STAGGER = 50;
const firstDelay = $derived(pillGen === 0 ? 350 : 150);
const buttonDelay = $derived(firstDelay + (VISIBLE_COUNT + 1) * STAGGER);
```

Stagger was 50ms on initial, 100ms on reshuffle before. Unifying to 50ms tightens reshuffle slightly; if it feels too snappy in practice, bump reshuffle's stagger back to 100.

Delay budget:

| element | before (initial) | before (reshuffle) | after (initial) | after (reshuffle) |
| ------- | ---------------- | ------------------ | --------------- | ----------------- |
| pill 1  | 350ms            | 150ms              | 350ms           | 150ms             |
| pill 6  | 600ms            | 650ms              | 600ms           | 400ms             |
| button  | 700ms            | 750ms              | 700ms           | 500ms             |

### 4. Narrow container `max-width` from 750px to 680px

Unrelated to the hydration-order root cause, but surfaced during post-fix review: at 750px the component occasionally wrapped as `4 pills + 2 pills + button` on reshuffle, producing an unbalanced layout that also shifted the button's horizontal position across reshuffles.

After empirical measurement across 40+ reshuffles at multiple widths:

| max-width | Layout consistency                                                                             | Notes                                 |
| --------- | ---------------------------------------------------------------------------------------------- | ------------------------------------- |
| 750px     | 4+2 on some reshuffles                                                                         | Original — button drifts horizontally |
| 620px     | 3+3 pills always, but button oscillates between row 2 inline and row 3 alone; rare 3+2+1 split | Over-corrected                        |
| 640px     | 3+3 pills always, button oscillates between row 2 inline (61%) and row 3 alone (39%)           | No 3+2+1                              |
| **680px** | **3+3+button-inline always (41/41 runs)**                                                      | Sweet spot                            |
| 700px     | 98% clean, ~2% 4+2 regression                                                                  | Too wide                              |

The 680px window is narrow: below ~673px the button can't fit inline after 3 row-2 pills (drops to its own row); above ~682px row 1 can admit 4 pills (the original bug). Load-bearing comment added above the declaration.

This is calibrated to the current `PILL_POOL` label widths and 13px font. If either changes, re-measure.

## Net effect

- Root cause gone: pills are in the SSR HTML, same animation clock as the button, button can't beat pills.
- `onMount` removed.
- One template branch instead of two. ~50 lines of duplicated markup deleted.
- Two CSS animations kept (`pill-fade-slide`, `pill-fade`) — they encode a real UX distinction.
- Initial six curated, in wrap-balanced order.
- `byLabel` helper makes the "label doesn't match the pool" failure mode immediate and descriptive.
- Container width pinned at 680px for consistent 3+3+button-inline layout on every reshuffle.

## What this changes for users

- **First load**: every visitor sees the same curated six, rendered with the slide-up animation. Previously, visitors saw a random six — populated ~500ms after page load due to the `onMount` path. The bug made the reshuffle button arrive before them, which is what kicked this off. Moving from random-then-late to curated-and-on-time is the real product change, not a side effect.
- **Reshuffle**: unchanged in intent. Clicking the button still draws six random pills from all 24. Animation is opacity-only (no slide), which matches current behavior.
- **Returning users**: land on the same six each time. Reshuffle is where variety lives. The button's affordance already signals this.

## Risks

- **`byLabel` crashes at module load if a label drifts out of `PILL_POOL`.** Intentional — loud failure in dev is better than silent empty pills. Risk mitigated by the helper's descriptive error message.
- **Reshuffle stagger tightens** from 100ms → 50ms per pill. Minor; easy to tune post-implementation if it reads as rushed.
- **680px is calibrated to current label widths and font size.** If someone adds a shorter label (below 15 chars), changes the font size, tweaks pill padding, or removes enough long pills that 4 short pills can fit, the window collapses and layout could regress to 4+2 or to button-on-own-row. Load-bearing comment above the declaration documents this.

## Out of scope

- No changes to `PILL_POOL` contents or ordering.
- No changes to `pickPills` / `topic-pills-shuffle.ts` — reshuffle keeps using it unchanged.
- No changes to `RestaurantHero.svelte`. Consumer is unaffected — component API is unchanged.

## Verification plan

1. `npm run check` — type-check clean.
2. `npm run test` — Vitest, including the `pickPills` spec which should still pass (we don't touch that file).
3. Svelte autofixer on the modified component.
4. Chrome DevTools MCP against dev server (port 5199):
   - Load `/agent` fresh, confirm the six chosen pills appear in the declared order, button lands last.
   - Click reshuffle, confirm pills randomize with opacity-only animation (no slide), button lands last.
5. After a build, inspect `.svelte-kit/output/prerendered/pages/agent.html` to confirm six `topic-pill` classes now ship in SSR HTML (was 0).
