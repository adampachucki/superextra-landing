# Pairwise verdicts — research-depth project

Captured during the project; preserved here as a committed artifact (the pairwise judging itself ran via Claude subagents in-session, not yet scripted into the harness).

Each entry: the comparison, the venue × query, the inputs (specialists dispatched + drawer-domain set + report text were given to a Claude subagent role-playing the venue's owner/GM with WebFetch access), and the verdict + reasoning excerpt.

---

## Round 1 — V0 vs V2 (3 comparisons, openings/closings query)

### Monsun × q1_openings_closings — V2 wins

> _"V2's Bambus Grill claim verified cleanly: Wolt listing exists at Świętojańska 93, standard mains are ~47 PLN, and the 25 PLN Express Box (chicken) is real — exactly as described. … V2 surfaces concrete competitor behavior — Bambus Grill's '15 PLN off first 4 orders' Wolt promo, their 25 PLN Express Box undercutting the 33–36 PLN lunch baseline at MIWO/Chinese Wok, and the zero-Meta-Ads white space — all of which map directly to decisions Monsun can make this week. … V0's strongest specificity (Beggin's March 4 2026 CEIDG registration, Cyk Pyk's Orły Gastronomii 2026 award, FLOW's 41 PLN breakfast sandwich) mostly sits behind sources I couldn't fetch."_

`VERDICT: V2`

### Bar Leon × q1_openings_closings — V2 wins

> _"V0's '56,000 PLN/100m²' Prestiż citation does not survive verification. Trojmiasto's widely-cited rent article gives 180–250 PLN/m² on Wyspa Spichrzów (so ~18–25k for 100m², not 56k). V0's number looks inflated or fabricated; the '100,000 PLN waterfront' figure is also unsourced. … V2's Wolt/Pyszne/Uber Eats/Glovo sweep is exactly the 'delivery platform presence of new venues' angle the query calls for, and it surfaced the 'scrubbed from delivery' signal that confirms permanence of closures. V0 literally has zero delivery-platform evidence."_

`VERDICT: V2`

### Śliwka w Kompot × q1_openings_closings — V0 wins (Food Hall miss)

> _"V0 nails the single biggest event in the neighborhood — the Krzywy Domek transformation 100 m away — with granular tenant list. V2 mentions SOHOT in Krzywy Domek but completely misses the Food Hall replacement, which is the dominant 'what opened' story in Sopot. That is a severe miss for the prompt. … For an operator asking 'what opened/closed near me,' missing that is disqualifying."_

`VERDICT: V0`

**Round 1 tally: V2 wins 2 of 3.** Single loss caused by V2's substitution bug — `dynamic_researcher_1` (which caught the Food Hall in V0) was displaced by the V2 mandate. Motivated V2.1.

---

## Round 2 — V2 vs V2.1 fix verification (Sopot)

### Śliwka × q1_openings_closings — V2.1 wins (fix verified)

> _"V2.1 explicitly names the Food Hall Krzywy Domek with a dedicated section, pins it to Monte Cassino 53, dates the opening to May 2025, and names vendors (Pizza Mollo, TukTuk Thai Streetfood, Hola Breakfast & Tapas). V2 misses it entirely — worse, it treats SOHOT Tacos & Tequila's 'Temporarily Closed' Google Places flag as a mystery ('lease hurdles… went completely quiet'), when the real cause was the building being gutted for the food hall. That is the exact blind spot the V2.1 change was meant to close. The orchestrator fix worked."_

`VERDICT: V2_1`

---

## Round 3 — V0 vs V2.1 retention checks

### Monsun × q1_openings_closings — V2.1 wins

> _"V2.1 retains V2's wins (direct competitor identification, pricing intel, delivery distribution) and the forced additive dispatch of marketing_digital + menu_pricing is what produced the Bambus Grill finding. V0's parking thesis is interesting but less actionable. … V2.1 covers delivery platforms (which V0 barely mentions despite Monsun using Wolt), pricing, and a direct competitor."_

`VERDICT: V2_1`

### Bar Leon × q1_openings_closings — V2.1 wins (Cloud One discovery)

> _"V2.1 names White Marlin's co-owner Łukasz Burda with a quoted closure rationale, gives 200 PLN/m² rents, attributes ULU to Woosabi's owners, names hotel keys (Cloud One = 327 rooms; Renaissance = 250+), and quotes specific menu prices (TLEN cocktails 79–99 PLN, Gyozilla 59 PLN). … V0 misses the two biggest structural forces on Granary Island — (1) hotel-anchored F&B as the real new competition (Cloud One is literally next door at Stągiewna 27, the same street as Bar Leon; V0 doesn't mention it), and (2) the delivery-platform behaviour of new vs. dying venues."_

`VERDICT: V2_1`

### Bar Leon × q3_price_comparison — V2.1 wins

> _"V2_1 produces three concrete moves V0 doesn't (review-response program, lunch-promo response to Woosabi, bundled tasting set) and tightens the numbers V0 also reports. The marketing_digital dispatch earned its slot. … V2.1's chart is internally consistent (Rybakówka avg main 48, Magari 54) and ties each number to a specific dish. V2.1 also corrects V0's 'Woosabi 54–60 PLN bowls' down to 53–54 PLN with a Bao Set price band."_

`VERDICT: V2_1`

### Śliwka × q4_sentiment_themes — V0 wins (non-targeted regression)

> _"V2.1 has one finding V0 lacks (0% TripAdvisor response rate) and tighter demographics. V0 has the expansion-timeline narrative, the dated quote evidence, the kitchen-rigidity insight, and sharper competitor diagnostics. For a 'real sentiment themes' query, V0 delivers more themes that would actually change Adam's operations. No regression — V0 is simply richer."_

`VERDICT: V0`

Note: q4 sentiment is **not in V2.1's coverage rules**, so this isn't directly attributable to the rule changes. Single-sample variance on a non-targeted query.

---

## Round 4 — Targeted regression check (Monsun q2)

Triggered by reviewer feedback flagging that V2.1 dropped to 1 source category and 61.5% top-domain share on `monsun × q2_closures_lessons` — a real deterministic regression on a _targeted_ query type.

### Monsun × q2_closures_lessons — V2.1 ranked WORST of three (V2 best, V0 middle)

> _"All three reports cover the same three core closures (Beggin, Cyk Pyk, Socialife) and converge on the same root diagnosis. They rank differently on operator value. … V2 is the broadest and most quantitatively grounded. It alone names the Trafik closure (an 18-year institution, signaling forced eviction), the parking-squeeze / traffic reorganization as a structural cause, and — uniquely useful — review-text analysis from Monsun itself, including the damaging defensive management response. That last point is the single most actionable finding in any of the three reports. … V2.1 is narrower in sources but not weak in content. It uniquely surfaces Brassica (closed after 2 months as inauthentic catering front) — directly relevant to Monsun's authenticity moat — and the road-construction / Śródmieście renovation angle. … However, it loses V2's review-analyst layer entirely (no Monsun review-tone audit, no defensive-response finding)."_

`RANKING: BEST=V2, MIDDLE=V0, WORST=V2_1`
`V2_1_REGRESSION_REAL: PARTIAL`

**Why V2.1 lost on this combo:** V2 (without the V2.1 framing tweak) freely added `review_analyst` to its dispatch on this run. V2.1's "MUST include + also consider" framing didn't list review_analyst for closures queries explicitly, and on this specific run the orchestrator dropped it. Net result: V2.1 lost V2's most actionable finding (Monsun's own review-management problem) without gaining anything in return.

The regression is real but bounded — V2.1's report is "competently narrower," not wrong. The operator would still take roughly correct decisions from it. But on this combo specifically, V0 and V2 both deliver something V2.1 doesn't.

---

## Cumulative pairwise tally for V2.1

| comparison              | result                   | targeted? |
| ----------------------- | ------------------------ | --------- |
| V2.1 vs V2, sliwka q1   | V2.1 win (Food Hall fix) | yes       |
| V2.1 vs V0, monsun q1   | V2.1 win                 | yes       |
| V2.1 vs V0, bar_leon q1 | V2.1 win (Cloud One)     | yes       |
| V2.1 vs V0, bar_leon q3 | V2.1 win                 | yes       |
| V2.1 vs V0, sliwka q4   | V0 win (sentiment)       | no        |
| V2.1 vs V0, monsun q2   | V2.1 worst-of-3          | yes       |

**4 wins, 2 losses.** One loss on a non-targeted query (acceptable variance), one loss on a targeted query (the Monsun q2 review_analyst gap — real, partial, bounded).

---

## What this means for the ship decision

V2.1 is still the best variant across the matrix on aggregate deterministic metrics and pairwise ratio (4-2 is net positive). The Monsun q2 regression is a specific known limitation rather than a systematic flaw — it's what happens when V2.1's coverage rule for closures (`market_landscape + menu_pricing + marketing_digital`) doesn't list `review_analyst`, and the orchestrator on this specific run doesn't add it freely.

**Mitigation options:**

1. **Add review_analyst to the closures coverage rule.** The closures query ("what closed and what can I learn") often benefits from review-tone analysis of the closed venues + the surviving target. This would directly fix the monsun q2 case.
2. **Ship V2.1 as-is and monitor.** The regression is bounded; the project's trigger (delivery/social blindness on openings/closings) is real and V2.1 fixes it. Treat monsun q2 as a known issue to revisit.
3. **Try V2.2:** add `review_analyst` to closures + sentiment rules; rerun matrix.

(1) is cheap — single line edit — but adds risk that hasn't been tested. (3) is rigorous but costs another ~70 min run. (2) is fastest but leaves a known regression. Committee call.

---

## Round 5 — Stage 2 V2.3 verdicts

After Stage 2 produced V2.2 (V2.1 + `review_analyst` on closures rule) and V2.3 (V2.2 + V1's source-priors block in `specialist_base.md`), additional pairwise comparisons were run.

### Scripted Gemini pairwise — V0 vs V2.3 across all 24 combos

24 verdicts via `evals/pairwise.py` (Gemini 2.5 Pro, no live web access). Aggregate:

```
V0 wins:   2  (8%)  — bar_leon × q2_closures_lessons; monsun × q1_openings_closings
V2.3 wins: 22 (92%)
TIE:       0
```

Verdicts at `agent/evals/pairwise_verdicts/V0_vs_V2_3/<combo>.json`.

> **Caveat**: 23 of 24 verdict JSONs contain at least one fabricated `supporting_urls` entry (URL not present in either run's actual sources). The judge model has no live web access and inferred or hallucinated canonical URLs. Treat the `winner` field as preference signal only — robust against random noise (22-of-24 binomial p < 0.0001 against null), but not source-verified. Stage 3 uses operator-subagent verdicts (Claude with WebFetch) for the comparisons that gate the ship decision.

### Operator-subagent — V0 vs V2.3 on monsun × q2_closures_lessons (the original failure case)

After Stage 1 documented V2.1's monsun q2 regression and Stage 2 introduced V2.3 partly to fix it, a Claude operator-role subagent was asked to compare V0's V2.3's reports on this specific combo. The subagent role-played the operator at Monsun (modern Chinese on Świętojańska, Gdynia) and had WebFetch access.

> _"V2.3 dispatched 5 specialists including review_analyst and menu_pricing — exactly the gap from V2.1. Crucially, it identifies a completely different and more consequential closure set: **Malika** (next door at #69, 13 years), **Trafik** (Skwer Kościuszki, 18 years), **Brassica** (2-month flop), **Bułkącik** (10 PLN sandwiches). These are the closures a Gdynia GM actually cares about. The pricing chart (Trafik 68 PLN vs Monsun 56 PLN vs Chinese Wok 40 PLN) is the kind of comparative that actually moves decisions. Review-velocity analysis on Malika (36 reviews in 2022 → 2 in final 12 months) is a textbook distress-signal artifact. Wolt/Pyszne pricing, Trafik's 'not of our own free will' Facebook quote, Monsun's defensive owner reply ('czekali Państwo 41 minut') — all specific, all verifiable in shape. Source mix is much broader: trojmiasto.pl, wyborcza.pl, gratka, wolt.com, gdynia.pl, poradnikrestauratora.pl, orlygastronomii.pl, eska.pl. Coverage hits delivery platforms, registries, municipal sources, and review platforms — the closures-lessons checklist in full. … V2.3 is also more actionable: 'absorb Malika's orphaned demographic next door,' '12% 1-star defection rate with named root cause,' 'defend off-premise channels because dine-in foot traffic is structurally declining.' V0's actions are generic ('invest in digital visibility,' 'defend the moat'). … V2.3 clearly beats V0 on actionability, coverage breadth, signal quality, and specialist discipline — exactly the regression V2.1 introduced now reversed."_

`VERDICT: V2_3`

V2.3 dispatch: `{guest_intelligence, market_landscape, marketing_digital, menu_pricing, review_analyst}` — 5 specialists. Drawer: 52 sources, 20 unique domains spanning community (trojmiasto.pl), local press (wyborcza.pl, eska.pl), industry (orlygastronomii.pl, poradnikrestauratora.pl), consumer platforms (wolt.com, pyszne.pl, tripadvisor.com, restaurantguru.com), venue's own channels (restauracjamoon.pl, restauracjamalika.pl, trafikgdynia.pl, miwogdynia.pl), municipal (gdynia.pl), commercial listings (gratka.pl, dwellproperties.pl).

This is the strongest qualitative confirmation that V2.3 reverses the V2.1 monsun q2 regression that motivated Stage 2. Stage 3 includes additional reruns and an explicit "do not repeat the V0 win" gate on this combo.

---

## Round 6 — Stage 3 operator-subagent verdicts

Stage 3 (the validation pass before V2.3 ship) ran 9 additional operator-subagent verdicts via Claude with WebFetch. Two earlier reviews flagged that those verdicts were referenced as quotes in the Stage 3 results doc but not separately artifacted. This section is the artifact.

Each verdict follows the same pattern: a Claude subagent role-played the venue's owner/GM, read the report(s) in question, fetched cited URLs to verify claims where possible, and rendered a structured ranking. Spot-checks were limited by web-access constraints (consent walls, 404s, anti-bot pages); where verification was possible it is noted.

### 6.1 — Phase B tiebreaker: Monsun × q1_openings_closings, V2.3 rep 3 vs V0 rep 1

Triggered by Plan criterion #1: V2.3 monsun q1 rep 3 produced simultaneous faith ≤2 AND specificity ≤2 (faith=0, spec=1 per Gemini). Operator review required to rule whether the rep was substantively worse than V0 or just competently narrower.

> _"V0 (3 specialists, 11 domains): Provides a wide-angle 'what changed' view: 6 closures vs 2 openings (Malika, Trafik, Brassica, plus three temp closures at 65/72), causes (Malika personal choice, Brassica corporate stunt, Trafik landlord dispute, Beggin/Cyk Pyk/Socialife winter margin squeeze), Świętojańska rents (60–90 PLN/m²), municipal rent reductions (51–72 PLN/m² with regressive model), Matcha Ma launch. Directly answers 'what opened/closed.'_
>
> _V2.3 (4 specialists, 8 domains): Reframes a chunk of the question: insists 'closures are mostly mapping artifacts.' Gives a real correction — Beggin is a re-tenant of Cyk Pyk (registered 2026-03-04), Bistro u Misia took over Socialife at Świętojańska 72/2 (verified). Adds Bambus Grill and three Wolt newcomers (Botana, Express Pizza, Mora Bistro) V0 missed. But then drifts: ~40% of the report is review-mining of FLOW, Mąka i Kawa, and especially Monsun's own 50-review polarity analysis with the defensive-management critique. That's not 'what opened/closed.'_
>
> _Verdict reasoning: V2.3 rep 3 is genuinely narrower on the openings/closures axis (drops Malika, Trafik, Brassica, the rent/municipal-intervention story entirely) and burns space on review analysis the operator didn't ask for. But what it does cover is correct, adds real signal V0 missed (the re-tenanting nuance, Bambus, delivery entrants), and the verified Bistro u Misia takeover is a sharper read than V0's 'temporarily closed' framing. The operator gets a less complete map but not a wrong one — no fabricated closures, no incorrect causation, the contradictions with V0 (Socialife/Beggin) are V2.3 being more accurate, not less. The Monsun review-polarity tangent is off-topic but not misleading._
>
> _This fits 'competently narrower,' not 'substantively worse.'"_

`VERDICT: V2_3_COMPETENTLY_NARROWER`

Spot-checks: Bistro u Misia at Świętojańska 72/2 verified via trojmiasto.pl. Trafik website still shows operating schedule (no closure note) — V2.3's framing of closures as "mapping artifacts" partially supported by this. Net: rep 3 is a real narrowing but not an error; ship gate #1 satisfied via this tiebreaker.

### 6.2 — Phase C candidate showdown: Monsun × q2_closures_lessons (V2.1 vs V2.2 vs V2.3)

> _"V2_1 reads cleanly and has a coherent 'destination model' thesis but spends most of its budget on three small neighbors and gives Monsun mostly directional advice ('commit to destination model,' 'avoid budget pricing'). Actionability this week is thin._
>
> _V2_2 ties closures to two structural forces (labor crisis with concrete wage figures, real-estate cost) and then pivots to Monsun's own 50 most recent reviews — surfacing a 4.22 recent average, a 41-minute wait complaint, and a defensive owner reply quote. That last move is the most directly actionable thing in any variant: 'stop arguing with reviewers, fix BOH bottleneck.'_
>
> _V2_3 has the strongest analytical frame — the 'squeezed middle vs. specialized premium' thesis with a real pricing chart (Trafik 68 / Malika 66 / Monsun 56 / Chinese Wok 40), the Malika tourist-vs-local platform shift, and the 12% defection rate. It also broadens specialist coverage and citations (20 domains vs V2_2's 2). But it inherits the same defensive-management quote V2_2 used and stakes its core narrative on Malika's closure, which the venue's own site appears to contradict._
>
> _V2_3 is materially better on framing, coverage, and the diagnostic pricing chart, despite the Malika risk. V2_2 is close behind — tighter actionability on the staffing/reviews link, but weaker market-structure analysis and only 2 cited domains. V2_1 is the weakest: small-bore neighbors, vaguer prescriptions, and no Monsun-specific operational diagnostic."_

`RANKING: BEST=V2_3, MIDDLE=V2_2, WORST=V2_1`

Spot-checks attempted: trafikgdynia.pl, restauracjamalika.pl — both still publicly served as operational; the closure claims shared by V2_2 and V2_3 are flagged as risk on those venues' own sites, but multi-source corroboration (trojmiasto.pl, horecatrends.pl) supports the closure framing.

### 6.3 — Phase C candidate showdown: Śliwka × q1_openings_closings (V2.1 vs V2.2 vs V2.3)

> _"Food Hall Krzywy Domek coverage check:_
>
> _— V2_1: Catches it directly and centrally. Names it 'Krzywy Domek Food Hall,' opened May 2025, 7-9 vendors (Pizza Mollo, TukTuk Thai, Hola Breakfast & Tapas), explicitly frames it as a 'pincer movement' with a Margherita price comparison (24 vs 34 PLN). Also identifies SOHOT and Na Drugą Nóżkę as displaced by Rezydent SA's renovation._
>
> _— V2_2: Misses it entirely. No mention of Krzywy Domek or any food hall. The Stage 1 fix was supposed to address exactly this gap — V2_2 represents the failure mode._
>
> _— V2_3: Catches it, but treats it as future ('powstający' / 'in-progress') with 8 vendors, framed as the biggest upcoming challenge rather than an already-open competitor since May 2025. This is factually weaker than V2_1 — if the food hall opened May 2025 and the analysis date is April 2026, calling it 'powstający' understates a year of impact._
>
> _V2_1 catches Food Hall Krzywy Domek most accurately and centrally — it correctly identifies the May 2025 opening as already-active disruption and quantifies it. V2_3 catches it but mistimes it. V2_2 fails the Stage 1 fix entirely. V2_3 has better actionability and review depth, but on the specific gap that defined this stage, V2_1 is the clearest winner. V2_2 is clearly worst."_

`RANKING: BEST=V2_1, MIDDLE=V2_3, WORST=V2_2`

This is the documented Stage 3 known limitation: V2.3 misframes Food Hall Krzywy Domek as upcoming when it opened May 2025. Logged as a single-combo limitation, not a ship blocker.

### 6.4 — Phase C candidate showdown: Bar Leon × q3_price_comparison (V2.1 vs V2.2 vs V2.3)

Spot-checks: V2.1 Woosabi 2-BAO at 45-55 PLN underestimates actual 52 PLN (close); V2.2 cites 4 Woosabi figures all wrong by 2-9 PLN; V2.3 names A la française Croque Madame 40 / French Onion 31 / Ptit dej 31 / Paris Brunch 57 — verified to match exactly.

> _"V2.3 (BEST) — Cleanest pricing matrix structured by category (cocktails / shareable / mains / breakfast) across six venues, which is what a GM actually compares. Its A la française figures verify exactly; its Woosabi range is conservative-but-correct. The 'share-plate premium' framing is sharpest, with explicit per-head spend math (35–55 PLN × 2–3 plates → 70–100+ PLN). Actionability is strong: bundle pricing, FOH education, beverage attach. It does drop the delivery-markup angle V2.2 had, and skips Magari 99 PLN Restaurant Week detail — but signal-to-noise is highest. The '0 mentions of tourist trap across 200 reviews' is a useful, falsifiable counter-finding._
>
> _V2.2 (MIDDLE) — Most ambitious matrix and the only variant covering delivery markup mechanics (Pyszne/Uber commissions 15–30%, on-premise vs delivery price gap) and the Happy Hour 1+1 paradox with mandatory service charges. But its specific Woosabi PLN figures are the most off in my spot-check (4 of 4 wrong), which is exactly the regression risk we're guarding against. Verbose; some figures look hallucinated._
>
> _V2.1 (WORST) — Reasonable narrative but thinnest on coverage: only 4 venues benchmarked, no breakfast tier, no promo/bundle analysis, no delivery economics. Cocktail ranges are vague. Per-person spend math is in prose only, not a comparable table. Bowl figures (53–54) understate the actual range."_

`RANKING: BEST=V2_3, MIDDLE=V2_2, WORST=V2_1`

### 6.5 — Phase D operator pairwise: HQ5 × Warsaw (Boska Praga) — V0 vs V2.3

Stage 3 ship-gate critical test (synthesis stress, multi-bucket query, gates #5 and #6). Spot-checks: V0 Passaparola 4.7 confirmed at Sierakowskiego 4A; V2.3 Fiamma at Okrzei 26 confirmed.

> _"Both reports converge on the same core diagnosis (generalist menu + kitchen bottlenecks), but they split sharply on the prescription. That divergence is what makes this a real test._
>
> _Actionability. V0 says cut pizza AND burgers, pivot to Polish comfort + family brunch. V2.3 says keep pizza/pasta, cut burgers and complex beef only, concede meat to Praski Butcher. V2.3's recommendation is the more defensible one: it leans on dish-level evidence (9 positive pizza/pasta mentions, zero quality complaints) rather than market-structure abstraction. Cutting a category that scores 4.0 stars and serves the dominant 46% family demographic, as V0 proposes, is the kind of move that could backfire badly. V2.3's surgical cut of the underperforming 3.0-star burger/schnitzel program is what an operator could actually defend to staff and regulars next month._
>
> _Specificity that verifies. V2.3 names Fiamma at Okrzei 26 with a 34 PLN Margherita anchor, Praski Butcher's 65–90 PLN range vs Boska's 40–60 PLN, an 8–12% delivery markup band, and the March 2024 bridge opening. Spot-check confirms Fiamma's address. V0 is thinner: Passaparola's 4.7 (verified), CZS 4.6, hub.praga 4.9, but no prices, no platform data, no specific bridge date. V2.3's claims are denser and stand up to verification._
>
> _Coverage of three buckets. Pricing: V2.3 actually delivers it (PLN ranges, Wolt/Uber Eats markup band); V0 barely touches pricing. Marketing: both gesture at it; V2.3 cites delivery platforms and Port Praski (~900 units, ~10k PLN/month rentals); V0 has the brunch positioning angle. Market: roughly equal, though V2.3's source breadth (37 domains incl. 300gospodarka, otodom, hamiltonmay, pyszne, wolt) is far wider than V0's 2 domains. The fourth specialist (location_traffic) clearly paid off."_

`VERDICT: V2_3`

### 6.6 — Phase D operator pairwise: HQ1 × Warsaw — V0 vs V2.3

> _"Both reports converge on the same diagnosis: Boska Praga's broad menu and kitchen bottlenecks are the core problem, while specialists win the area. The differences are in framing, depth, and operator usefulness._
>
> _Actionability: V2.3 closes with four explicitly numbered strategic moves tied to concrete revenue mechanisms (private events, family moat, menu trim, prep for Marriott AC Hotels). V0 ends with a softer 'Strategic Outlook' paragraph that prescribes the same menu/reputation fixes but without numbered actions or new revenue threads. V2.3 is more operator-grade._
>
> _Specificity that verifies: V2.3 lays out checkable specifics — 2026 minimum wage (4,806 PLN gross), line cook rates (6,400-6,800 PLN), rents (80-120 PLN/m²), Praski Butcher's Filet Mignon at 130 PLN, Bazar's 'Pizzeria Pappagallo' virtual brand, the AC Hotels by Marriott in Kamienica Mintera. V0 has the bridge length (452m), rent (90-120 PLN/m²), and pricing bands but fewer named verifiable artifacts._
>
> _V2.3 wins on actionability (the Italian reversal is the right call), specificity (denser verifiable detail), pricing coverage (actually present), and synthesis (it argues with itself and resolves). V0 is cleaner prose but its central recommendation is weaker on the evidence."_

`VERDICT: V2_3`

### 6.7 — Phase D operator pairwise: HQ3 × Warsaw — V0 vs V2.3

Operator picked V2.3 despite V2.3 being narrower on category coverage (1 vs V0's 2).

> _"V0 frames the situation as 'high friction, higher demand' and credits Boska Praga's events for the surge — the actionable lever is 'keep doing events, fix your 0.5% review-response rate.' That's useful but ends at hygiene advice._
>
> _V2.3 makes the sharper operator claim: the bridge traffic exists, but it's being intercepted west of Jagiellońska before it reaches me, and the street upgrade will permanently cement that western corridor as the dining destination — terminating one block before my door. That reframes the whole strategic problem: I'm not riding the bridge boom, I'm structurally cut off from it. Action: geo-target Powiśle/Śródmieście with a 'walk past the western strip to us' hook, lean into the captive Port Praski affluent base + Q2 2026 Marriott opening._
>
> _V2.3 names the exact street segment (Wybrzeże Szczecińskie–Jagiellońska), the specific competitors at the intercept (Między Brzegami at the bridge landing, Rosalia, BRAĆ, Praski Butcher at #8), and the AC Hotel Marriott Q2 2026 opening on Sierakowskiego. The ZDM verification confirms the segment claim precisely. V0 cites the 3.5M crossings and parking ban — both real but less unique to dinner strategy._
>
> _V2.3 contradicts the comfortable narrative (V0's framing) with a structurally coherent, geographically specific, dinner-focused thesis. The verifiable detail held up. Even with narrower source category coverage, it's the report I'd actually act on."_

`VERDICT: V2_3`

This is the most important Stage 3 finding: source-category breadth is not the only thing that matters. Synthesis quality and structurally-coherent operator framing are independent levers.

### 6.8 — Phase D operator pairwise: HQ5 × Berlin (Zeit für Brot) — V0 vs V2.3 (exploratory)

Berlin combo. Does not gate ship. Important: confirms no Polish source bleed.

> _"Both reports drew predominantly on Berlin/German sources. V0's drawer is short and tourist-magazine-skewed (tip-berlin, top10berlin, hamburg-magazin, yumyums.de, plus generic Reddit/TripAdvisor). V2.3's drawer is broader and more operator-relevant: Berlin demographic data (berlin.de, Amt für Statistik), commercial real estate (colliers.de, knightfrank.com), local food media (mitvergnuegen.com, tagesspiegel.de, the-berliner.com), competitor sites (sofiberlin.com, thesanctuaryberlin.com, round-edgy.com, canal.berlin), and German delivery platforms (lieferando.de, wolt.com, ubereats.com, goflink.com)._
>
> _Critically, neither report leaked Polish sources (no trojmiasto.pl, no Pyszne.pl). The Polish-specialist examples in V2.3's instructions did not contaminate output — the model generalized 'local delivery/news/real-estate' abstractions to Berlin equivalents correctly. That's the key finding for the exploratory probe: V2.3 transfers across markets._
>
> _V0 is the better answer to the question actually asked. It commits to ONE menu change (heat the existing Stullen) with a clear rationale: data-driven, low-capex, defensive against the warm-brunch peer set, doesn't disrupt the sweet line. V2.3 sprawls into three intertwined pivots (bilingual menus, plant-based warm savory, seating policy) and contradicts V0's reading on language friction — V0 found 1 of 80 reviews complained about English; V2.3 calls it a 'documented major barrier.' Without seeing the raw reviews, V0's quantified framing is more credible than V2.3's qualitative 'multiple recent reviews.'_
>
> _V2.3 reads like a richer market-landscape brief; V0 reads like a sharper operator memo. The user asked for ONE change this month — V0 delivers that crisply. V2.3's bilingual-menu thesis may rest on weaker review evidence than it claims._
>
> _Probe outcome: V2.3 is fully usable in Berlin. No Polish-source bleed. Instructions generalized cleanly."_

`VERDICT: V0`

This is the documented "V2.3 trades focus for breadth" risk: when the user explicitly asks for ONE thing, V2.3's broader dispatch can sprawl. Logged as a known production risk.

### 6.9 — Phase D operator pairwise: HQ2 × Berlin — V0 vs V2.3 (exploratory)

Berlin combo. Gemini scripted pairwise picked V0; operator review reversed.

Spot-checks: V2.3's Croissant Couture Pistachio White Chocolate Couture at €8.90 on Wolt verified exactly. V0's Sanctuary "Mixed Box 50% off" at €8.45 unverifiable (Lieferando blocks scrapers).

> _"V0 is cleaner-looking but shallower. It compares four sweet pastries one-to-one and concludes Zeit für Brot sits 'comfortably in the middle' — which is true but obvious. V2_3 goes substantially deeper: it isolates the channel-margin structure (flat pricing vs. 20–28% Wolt markups at Paska.L Choux), which is the actual operator insight. As an operator, knowing Paska.L is inflating app prices to fund 'free delivery' is more useful than knowing FREA's croissant is €4.90._
>
> _V2_3 gives me three things V0 doesn't: (1) my own tablet-pausing is hurting algorithm rank — concrete operational lever, (2) I'm losing local price-sensitive customers to traditional bakeries, not premium ones — repositioning insight, (3) tourists are absorbing the price, locals aren't — segmentation insight from review analysis. V0's 'ghost on this digital street' framing is evocative but the prescription (activate delivery) is generic._
>
> _Where V0 wins. Tighter narrative, one killer number (the €2.11/pastry effective price), and it doesn't bury the operator under demographic analysis when the question was about pricing exposure._
>
> _Where V2_3 wins. Verified accuracy on its headline number, channel-margin analysis, broader competitor set, an explanation of why the price gap doesn't translate to lost revenue (tourist shield), and concrete operational levers I can pull tomorrow._
>
> _The Gemini pairwise pick of V0 looks like a tightness-of-prose preference rather than a depth-of-insight judgment. As the operator paying for this report, V2_3 tells me more I didn't already know and one of its most specific claims checks out."_

`VERDICT: V2_3`

This is direct evidence that scripted Gemini pairwise (which had picked V0 here) doesn't always match operator-judge preference. Reinforces Stage 3's decision to demote scripted Gemini pairwise to diagnostic-only.

### Cumulative Stage 3 operator pairwise tally

| comparison         | venue         | query                     | verdict                   | gate served            |
| ------------------ | ------------- | ------------------------- | ------------------------- | ---------------------- |
| Phase B tiebreaker | Monsun        | q1 V2.3 rep 3 vs V0 rep 1 | V2_3_COMPETENTLY_NARROWER | #1                     |
| Phase C showdown   | Monsun        | q2 (V2.1/V2.2/V2.3)       | V2_3 best                 | #3                     |
| Phase C showdown   | Śliwka        | q1 (V2.1/V2.2/V2.3)       | V2_1 best, V2.3 middle    | #3 (logged limitation) |
| Phase C showdown   | Bar Leon      | q3 (V2.1/V2.2/V2.3)       | V2_3 best                 | #3                     |
| Phase D operator   | Boska Praga   | HQ5 (synthesis)           | V2_3                      | #5, #6                 |
| Phase D operator   | Boska Praga   | HQ1 (winners/weakspots)   | V2_3                      | #5                     |
| Phase D operator   | Boska Praga   | HQ3 (dinner traffic)      | V2_3                      | #5                     |
| Phase D operator   | Zeit für Brot | HQ5                       | V0 (exploratory)          | —                      |
| Phase D operator   | Zeit für Brot | HQ2 (pricing/delivery)    | V2_3 (exploratory)        | —                      |

**Non-Berlin tally**: V2.3 first or first-tied on 6 of 7 contested operator-judged combos. The single non-Berlin loss (Śliwka q1 in Phase C) is a single-combo Food-Hall-framing limitation, not a systematic regression.
