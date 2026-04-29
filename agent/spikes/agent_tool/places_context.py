"""Hand-crafted places_context for the spike.

Used by both variants identically — eliminates the enricher as a variable
in the apples-to-apples comparison. Loosely modelled on what the real
context_enricher would emit for `monsun` based on prior eval runs, but
intentionally minimal: target + 4 nearby competitors, just enough for the
specialists to have a concrete competitive set without re-discovering it.
"""

PLACES_CONTEXT = """\
TARGET RESTAURANT
- Name: Monsun
- Address: Świętojańska 49, 81-368 Gdynia, Poland
- Place ID: ChIJ48HwEQCn_UYRmVqYQULc9pM
- Rating: 4.6 (≈420 reviews)
- Price level: $$
- Cuisine: modern Polish, brunch-leaning
- Service modes: dine-in, takeaway
- Hours: Mon-Sun 09:00-22:00

COMPETITIVE SET (within ~700m, similar tier)
1. Bar Mleczny Słoneczny — Świętojańska 21, Gdynia. Rating 4.4 (≈300). $. Polish bistro.
2. Tłusta Kaczka — Starowiejska 10, Gdynia. Rating 4.5 (≈900). $$. Modern Polish.
3. Kurkuma Cafe — Świętojańska 24, Gdynia. Rating 4.7 (≈250). $$. Vegan/healthy.
4. Pueblo Desayuno — 10 Lutego 11, Gdynia. Rating 4.6 (≈600). $$. Brunch/Mexican.

NOTES
- All 5 venues are on Świętojańska / 10 Lutego, the main retail spine
  of central Gdynia.
- Google Places shows price level only — no actual menu prices or
  delivery markups are available from this source.
- Source: Google Places (synthetic for spike — not a live fetch).
"""

QUERY = "How does our menu pricing compare to competitors within 1 km?"
"""q3_price_comparison from agent/evals/queries.json — picked because both
menu_pricing and marketing_digital have natural relevance (price and
delivery-platform positioning), making it a fair test for whether the
orchestrator dispatches both regardless of routing mechanism."""
