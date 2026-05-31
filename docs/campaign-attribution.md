# Campaign attribution and prompt prefill

The landing page picks up ad-campaign UTM parameters and click-IDs on arrival,
stamps them into `localStorage`, and adapts the prompt area to the campaign
hook the visitor clicked on. This doc explains how to construct ad URLs, what
the recognized values do, and how downstream code (analytics / CAPI / future
work) reads the stored attribution.

## Anatomy of an ad URL

The landing page recognizes these query params:

| Param          | Purpose                                                       |
| -------------- | ------------------------------------------------------------- |
| `utm_source`   | Where the click came from (`meta`, `reddit`, etc.)            |
| `utm_medium`   | Channel type (`cpc`, `social`, etc.)                          |
| `utm_campaign` | Free-form campaign identifier                                 |
| `utm_content`  | **Hook pillar key** — drives the prompt-pills selection       |
| `fbclid`       | Meta click ID — required for Meta Conversions API attribution |
| `rdt_cid`      | Reddit click ID — required for Reddit Conversions API         |
| `q`            | Prefills the prompt textarea with the given question          |

Example Meta ad URL for a pricing hook:

```
https://landing.superextra.ai/?utm_source=meta&utm_medium=cpc&utm_campaign=us-pricing-jun26&utm_content=price&q=Are+4+brunch+spots+near+me+priced+higher+than+mine%3F
```

`fbclid` is appended automatically by Meta when the ad serves; you don't put
it in the destination URL yourself. Same for `rdt_cid` on Reddit ads.

## Recognized `utm_content` values

Each maps to a topic-pill category. When a campaign UTM is detected on
landing, the first three visible pills are drawn from that category; the
remaining three are random fillers from other categories. Same wrap-balanced
interleave as the default set.

| `utm_content` | Pill category    | Pills shown                                                        |
| ------------- | ---------------- | ------------------------------------------------------------------ |
| `price`       | `pricing`        | Menu price gaps, Lunch price positioning, Drinks pricing landscape |
| `hire`        | `wage`           | Salary benchmarks, Chef pay, Server wages                          |
| `open`        | `site_selection` | Foot traffic, Best streets, Competition density                    |
| `shifts`      | `market_shifts`  | Closures, Format shifts, Food trends                               |

One canonical key per pillar — no aliases. Mixing `price` and `pricing` in
campaign URLs would fragment reporting cohorts. Stick to these four.

Unrecognized `utm_content` values are still accepted and stamped (so the
analytics layer never loses attribution), but the pill set falls back to
the deterministic default. To add a new pillar, extend
`CONTENT_TO_PILL_CATEGORY` in `src/lib/campaign.ts` and tag a pill
category to match.

## The `?q=` prefill

When the URL includes `?q=...`, the prompt textarea is pre-populated with the
decoded value on landing. The prompt-area's typewriter placeholder animation
stops automatically because the textarea is non-empty.

The prefill plays well with the existing auth flow: if the visitor submits
without signing in, the draft (including the prefilled query) is preserved in
`localStorage` across the login modal — same mechanism as a manually typed
prompt.

Keep the query short and URL-encoded. Aim for a single concrete question that
matches the ad's headline.

## Attribution semantics (first-touch)

`stampFirstTouch()` runs once on first mount in `+layout.svelte`. Behavior:

- If the URL contains any UTM or click-ID params, the full payload is written
  to `localStorage.se_first_touch` along with a `stampedAt` timestamp.
- If the key already exists and hasn't expired, **it is not overwritten** —
  later ad clicks within the 30-day TTL preserve the original attribution.
- If the key has expired (>30 days old), it's cleared and a new stamp is
  written.
- Errors (private mode, quota full, JSON corruption) fail silently.

The 30-day TTL matches Meta's standard attribution window. To change it, edit
`TTL_DAYS` in `src/lib/campaign.ts`.

### Why first-touch, not last-touch

Most ad platforms credit the last click before conversion. Our analytics
layer wants the opposite: the first click is what we're testing in MVP
validation. The CAPI Cloud Function (separate work) still sends `fbclid` and
`rdt_cid` from the stamped first-touch, which means each ad platform sees its
own click credited correctly without us double-counting.

## Reading the attribution downstream

Other code reads the stamped payload via the exported helpers:

```ts
import { firstTouch, campaignCategory } from '$lib/campaign';

const ft = firstTouch();
// → { utm_source, utm_medium, utm_campaign, utm_content, fbclid?, rdt_cid?, stampedAt }
// or null

const cat = campaignCategory();
// → 'pricing' | 'wage' | 'site_selection' | 'market_shifts' | null
```

`campaignCategory()` checks the current URL first, then falls back to the
stored first-touch. This lets a visitor navigate around and still see
category-coherent UI even after the original UTM has been dropped from the
URL.

`firstTouch()` is the source of truth for analytics: pass `utm_*` to your
event payloads, pass `fbclid`/`rdt_cid` to the conversion-API call when the
user signs up.

## Storage details

- **Key**: `se_first_touch`
- **Shape**: JSON-encoded `FirstTouch` interface (see `src/lib/campaign.ts`)
- **TTL**: 30 days from `stampedAt`
- **Origin**: in production, `landing.superextra.ai/*` 301-redirects to
  `agent.superextra.ai/:rest` (see `firebase.json`), so every ad click is
  served from `agent.superextra.ai` directly. The marketing landing and the
  agent UI share that origin — the same `localStorage` is visible to both
  the prompt-area landing and the post-signup chat flow. No cross-subdomain
  handoff needed.

## Adding a new hook pillar

1. Add an entry to `CONTENT_TO_PILL_CATEGORY` in `src/lib/campaign.ts`
   mapping the new `utm_content` keys to a category string.
2. Tag the relevant pills in `src/lib/components/restaurants/TopicPills.svelte`
   with the same `category` value.
3. Add or update Paraglide message entries if the pills are new.
4. Test by visiting `/?utm_content=<your-key>` in the browser and confirming
   the pills swap correctly.

No code changes are needed if you only want a new campaign on an existing
pillar — just point the ad URL at the existing `utm_content` value with a
fresh `utm_campaign` identifier.

## Testing

- `src/lib/topic-pills-shuffle.spec.ts` covers `pickPills` + `pickPillsWithCategory`
- Manual verification: open the dev server (`http://localhost:5199/?utm_content=price&q=...`)
  and confirm pills match the table above
