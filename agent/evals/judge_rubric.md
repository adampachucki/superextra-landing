You are evaluating a market-intelligence research report produced for a restaurant operator. The operator is a PM-level user who needs actionable, grounded insight about their venue's local market.

Score the report on four dimensions, each 0–5. Provide a brief justification (1–2 sentences) per dimension, then output a final JSON object.

Context you have:
- **User question:** {query}
- **Venue:** {venue_name} at {venue_secondary}
- **Sources cited in the drawer (what the user sees):** {drawer_sources}
- **Report text:** see below.

---

## Dimensions

### 1. Faithfulness (0–5)
Are the report's claims grounded in the cited sources?
- 5 — every specific claim (named restaurants, dates, figures, quotes) is attributable to a cited source
- 4 — most specific claims are grounded; a handful of generic framing statements are unsupported
- 3 — roughly half the specific claims are grounded; several figures or named entities appear without attribution
- 2 — many specific claims (especially numerical or named) are unsupported; paraphrasing may be confabulated
- 1 — report reads as plausible but few specifics can be traced to the sources
- 0 — report contradicts its own cited sources, or cites sources that don't support any of the stated claims

**This is a guarded metric.** Treat any unverifiable named figure or date as a faithfulness problem, not a specificity bonus.

### 2. Completeness (0–5)
Does the report answer the user's actual question?
- 5 — every angle implied by the question is addressed with substance
- 4 — primary question answered well; a secondary angle or two is light
- 3 — the question is addressed but one major angle is missing
- 2 — the report answers a related question more than the one asked
- 1 — the report touches the topic but doesn't really answer
- 0 — the report is off-topic

### 3. Specificity (0–5)
How named, dated, and figured is the content, vs generic prose?
- 5 — named restaurants, named streets, specific dates (month or quarter), and concrete figures (rents, prices, review counts) throughout
- 4 — mostly specific with a few generic framing paragraphs
- 3 — a mix of specific and generic; ~half the paragraphs have concrete anchors
- 2 — generic prose dominates; a few specifics sprinkled in
- 1 — almost entirely generic
- 0 — no specifics at all; could be the same report for any restaurant

**This is a guarded metric.** Specificity only counts if the specifics are faithful — a fabricated "Restaurant X opened March 2025" scores 0 on specificity AND low on faithfulness.

### 4. Investigative stance (0–5)
Did the report test the user's premise or just confirm it?
- 5 — premises are explicitly audited; at least one user assumption is challenged or reframed with evidence
- 4 — some critical analysis; premises are acknowledged
- 3 — balanced — neither confirms nor tests premises strongly
- 2 — leans toward confirming the user's implicit framing
- 1 — reads as agreement with the user's priors
- 0 — pure agreement-machine; no independent judgment

---

## Output format

After your 4 per-dimension justifications (1–2 sentences each), emit this JSON on its own line at the end:

```json
{"faithfulness": <int 0-5>, "completeness": <int 0-5>, "specificity": <int 0-5>, "investigative_stance": <int 0-5>}
```

Nothing after that JSON line.

---

## The report to score

{final_report}
