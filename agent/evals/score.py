"""Score captured run JSONs into a flat CSV.

Reads every `<venue>__<query>.json` under --results and emits one row per
run with deterministic metrics (Phase 1 AND Final set) plus Gemini-judge
rubric scores. Judge calls happen in parallel-capped asyncio.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

AGENT_DIR = Path(__file__).resolve().parent.parent
EVALS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(AGENT_DIR))


# ── Domain → category taxonomy ─────────────────────────────────────────────
# 8 categories, matching docs/research-depth-eval-plan.md.
# Domains matched by suffix: a rule "trojmiasto.pl" matches foo.trojmiasto.pl too.

_CATEGORY_RULES: list[tuple[str, str]] = [
    # 1. Community discussion
    ("reddit.com", "community"),
    ("wykop.pl", "community"),
    ("forum.gazeta.pl", "community"),
    ("trojmiasto.pl", "community"),  # trojmiasto is forum-heavy; treat as community
    # 2. Local press (Tricity + national PL dailies)
    ("gdynia.naszemiasto.pl", "local_press"),
    ("gdansk.naszemiasto.pl", "local_press"),
    ("sopot.naszemiasto.pl", "local_press"),
    ("naszemiasto.pl", "local_press"),
    ("wyborcza.pl", "local_press"),
    ("wyborcza.biz", "local_press"),
    ("dziennikbaltycki.pl", "local_press"),
    ("radiogdansk.pl", "local_press"),
    ("radiogdansk.pl", "local_press"),
    ("rp.pl", "local_press"),
    ("tvn24.pl", "local_press"),
    ("onet.pl", "local_press"),
    ("interia.pl", "local_press"),
    # 3. Industry sites & reports
    ("horecatrends.pl", "industry"),
    ("orlygastronomii.pl", "industry"),
    ("foodie.pl", "industry"),
    ("foodfakty.pl", "industry"),
    ("smaki.pl", "industry"),
    ("statista.com", "industry"),
    ("ibisworld.com", "industry"),
    ("nielseniq.com", "industry"),
    ("deloitte.com", "industry"),
    ("mckinsey.com", "industry"),
    ("pwc.com", "industry"),
    ("kpmg.com", "industry"),
    ("ey.com", "industry"),
    # 4. Influencers & blogs
    ("instagram.com", "influencers_blogs"),
    ("tiktok.com", "influencers_blogs"),
    ("youtube.com", "influencers_blogs"),
    ("youtu.be", "influencers_blogs"),
    ("medium.com", "influencers_blogs"),
    ("substack.com", "influencers_blogs"),
    ("blogspot.com", "influencers_blogs"),
    # 5. Consumer platforms
    ("maps.google.com", "consumer_platforms"),
    ("google.com/maps", "consumer_platforms"),  # path-qualified — handled separately below
    ("pyszne.pl", "consumer_platforms"),
    ("wolt.com", "consumer_platforms"),
    ("glovoapp.com", "consumer_platforms"),
    ("glovo.com", "consumer_platforms"),
    ("bolt.eu", "consumer_platforms"),
    ("food.bolt.eu", "consumer_platforms"),
    ("ubereats.com", "consumer_platforms"),
    ("thefork.com", "consumer_platforms"),
    ("thefork.pl", "consumer_platforms"),
    ("opentable.com", "consumer_platforms"),
    ("tripadvisor.com", "consumer_platforms"),
    ("tripadvisor.pl", "consumer_platforms"),
    ("tripadvisor.co.uk", "consumer_platforms"),
    ("yelp.com", "consumer_platforms"),
    ("zomato.com", "consumer_platforms"),
    ("michelin.com", "consumer_platforms"),
    ("guide.michelin.com", "consumer_platforms"),
    ("foursquare.com", "consumer_platforms"),
    ("finebite.com", "consumer_platforms"),
    ("openstreetmap.org", "consumer_platforms"),
    # 6. Venue's own channels — generally the target restaurant's own domain.
    #    We can't classify this from the URL alone; will be handled by a
    #    caller-supplied `venue_own_domains` set (None = skip).
    # 7. Official registries & statistics
    ("ceidg.gov.pl", "official_registry"),
    ("prod.ceidg.gov.pl", "official_registry"),
    ("krs.ms.gov.pl", "official_registry"),
    ("stat.gov.pl", "official_registry"),
    ("gus.gov.pl", "official_registry"),
    ("regon.stat.gov.pl", "official_registry"),
    ("eurostat.ec.europa.eu", "official_registry"),
    ("ec.europa.eu", "official_registry"),
    ("oecd.org", "official_registry"),
    ("sec.gov", "official_registry"),
    ("companieshouse.gov.uk", "official_registry"),
    ("handelsregister.de", "official_registry"),
    ("dnb.com", "official_registry"),
    ("creditreform.com", "official_registry"),
    ("krd.pl", "official_registry"),
    # 8. Commercial listings & marketplaces
    ("otodom.pl", "commercial_listings"),
    ("gratka.pl", "commercial_listings"),
    ("domiporta.pl", "commercial_listings"),
    ("m2bomber.com", "commercial_listings"),
    ("olx.pl", "commercial_listings"),
    ("olx.com", "commercial_listings"),
    ("morizon.pl", "commercial_listings"),
    ("pracuj.pl", "commercial_listings"),
    ("indeed.com", "commercial_listings"),
]

CATEGORIES = [
    "community",
    "local_press",
    "industry",
    "influencers_blogs",
    "consumer_platforms",
    "venue_own",
    "official_registry",
    "commercial_listings",
]

# Landing-page marketing wall (from src/lib/components/DataSources.svelte:7).
# Used for "wall overlap" secondary diagnostic. Each entry maps the brand
# to one or more domain tokens. Google Maps is listed but we exclude
# auto-written google_maps provider pills from the count (see below).
_WALL_BRAND_DOMAINS: dict[str, list[str]] = {
    "TripAdvisor": ["tripadvisor.com", "tripadvisor.pl", "tripadvisor.co.uk"],
    "OpenTable": ["opentable.com"],
    "Yelp": ["yelp.com"],
    "TheFork": ["thefork.com", "thefork.pl"],
    "Michelin Guide": ["michelin.com", "guide.michelin.com"],
    "Zomato": ["zomato.com"],
    "Google Maps": ["maps.google.com", "google.com"],  # special-cased below
    "OpenStreetMap": ["openstreetmap.org"],
    "Foursquare": ["foursquare.com"],
    "Finebite": ["finebite.com"],
    "Instagram": ["instagram.com"],
    "Facebook": ["facebook.com"],
    "TikTok": ["tiktok.com"],
    "Uber Eats": ["ubereats.com"],
    "Wolt": ["wolt.com"],
    "Just Eat": ["just-eat.com", "justeat.com"],
    "Glovo": ["glovoapp.com", "glovo.com"],
    "CEIDG / KRS": ["ceidg.gov.pl", "krs.ms.gov.pl"],
    "Handelsregister": ["handelsregister.de"],
    "Companies House": ["companieshouse.gov.uk"],
    "SEC / EDGAR": ["sec.gov"],
    "Statista": ["statista.com"],
    "Deloitte": ["deloitte.com"],
    "NielsenIQ": ["nielseniq.com"],
    "Eurostat": ["eurostat.ec.europa.eu", "ec.europa.eu"],
    "IBISWorld": ["ibisworld.com"],
    "Krajowy Rejestr Długów": ["krd.pl"],
    "Dun & Bradstreet": ["dnb.com"],
    "Creditreform": ["creditreform.com"],
}


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _classify_domain(domain: str, venue_own_domains: set[str] | None = None) -> str:
    if not domain:
        return "other"
    if venue_own_domains and any(domain.endswith(d) for d in venue_own_domains):
        return "venue_own"
    for pattern, category in _CATEGORY_RULES:
        # Simple suffix match — also allows subdomains (gdynia.naszemiasto.pl matches naszemiasto.pl)
        if domain == pattern or domain.endswith("." + pattern) or pattern in domain:
            return category
    return "other"


def _diversity_stats(entries: list[dict], venue_own_domains: set[str] | None = None) -> dict:
    """Compute top-domain share, unique domain count, category coverage.

    Accepts a list of {url, domain?} dicts. Prefers the `domain` field when
    present (grounding chunks supply real domains; redirect URLs would parse
    to vertexaisearch.cloud.google.com otherwise).
    """
    if not entries:
        return {
            "n_urls": 0,
            "unique_domains": 0,
            "top_domain": None,
            "top_domain_count": 0,
            "top_domain_share": 0.0,
            "categories": [],
            "category_count": 0,
        }
    domains = [
        (e.get("domain") or _domain_of(e.get("url") or "")).lower()
        for e in entries
    ]
    counter = Counter(d for d in domains if d)
    top_domain, top_count = counter.most_common(1)[0] if counter else (None, 0)
    categories = {_classify_domain(d, venue_own_domains) for d in domains if d}
    # Don't count "other" as a covered category
    real_cats = sorted(c for c in categories if c != "other")
    return {
        "n_urls": len(entries),
        "unique_domains": len(counter),
        "top_domain": top_domain,
        "top_domain_count": top_count,
        "top_domain_share": round(top_count / max(len(entries), 1), 3),
        "categories": real_cats,
        "category_count": len(real_cats),
    }


def _wall_overlap(drawer_sources: list[dict]) -> dict:
    """Count distinct marketing-wall brands appearing in drawer sources.

    Excludes the auto-written Google Maps provider pill (written by the
    Places enricher for every target place regardless of research depth,
    so its presence is plumbing, not research-depth signal).
    """
    drawer_domains = {
        (s.get("domain") or _domain_of(s.get("url") or "")).lower()
        for s in drawer_sources
    }
    drawer_domains.discard("")
    # Detect the auto-written Google Maps pill: kind == "provider" AND
    # provider field == "google_maps". Strip its domain from the set.
    auto_gm = any(
        (s.get("provider") == "google_maps") or (s.get("kind") == "provider" and "google" in (s.get("domain") or ""))
        for s in drawer_sources
    )
    matched_brands: list[str] = []
    for brand, domains in _WALL_BRAND_DOMAINS.items():
        if brand == "Google Maps" and auto_gm:
            # Excluded from count when the hit came only from auto-write.
            # If some OTHER Google Maps URL is also present (user venue clicked
            # through grounding, etc.), that's still just the auto-write brand;
            # skip.
            continue
        if any(d in drawer_domains for d in domains):
            matched_brands.append(brand)
    return {
        "wall_brands_matched": matched_brands,
        "wall_brand_count": len(matched_brands),
        "wall_total_brands": len(_WALL_BRAND_DOMAINS),
    }


def _provider_presence(drawer_sources: list[dict]) -> dict:
    providers = {s.get("provider") for s in drawer_sources if s.get("provider")}
    return {
        "has_google_maps_pill": "google_maps" in providers,
        "has_google_reviews_pill": "google_reviews" in providers,
        "has_tripadvisor_pill": "tripadvisor" in providers,
    }


# ── Gemini judge ───────────────────────────────────────────────────────────

JUDGE_MODEL = "gemini-2.5-pro"
RUBRIC_PATH = EVALS_DIR / "judge_rubric.md"


def _build_judge_prompt(run: dict) -> str:
    """Build the judge prompt with explicit replace() — the rubric contains
    literal curly braces in the JSON example output, so str.format would
    misinterpret them as placeholders."""
    rubric = RUBRIC_PATH.read_text()
    drawer_str = "\n".join(
        f"- {s.get('domain', '?')}: {s.get('url', '')}"
        for s in (run.get("drawer_sources") or [])
    ) or "(none)"
    substitutions = {
        "{query}": run.get("query_text", ""),
        "{venue_name}": run.get("venue_name", ""),
        "{venue_secondary}": run.get("venue_secondary", ""),
        "{drawer_sources}": drawer_str,
        "{final_report}": run.get("final_report", ""),
    }
    for token, value in substitutions.items():
        rubric = rubric.replace(token, value)
    return rubric


_JUDGE_JSON_RE = re.compile(r"\{[^{}]*\"faithfulness\"[^{}]*\}", re.DOTALL)


async def _score_with_gemini(run: dict) -> dict:
    """Call Gemini with the rubric and parse the tail JSON."""
    # Lazy imports so the deterministic path works without credentials.
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site"),
        location="global",
    )
    prompt = _build_judge_prompt(run)
    resp = await client.aio.models.generate_content(
        model=JUDGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    text = resp.text or ""
    m = _JUDGE_JSON_RE.search(text)
    if not m:
        return {
            "judge_error": "no_json",
            "judge_raw_tail": text[-400:],
        }
    try:
        scores = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        return {
            "judge_error": f"parse: {e}",
            "judge_raw_tail": text[-400:],
        }
    return {
        "faithfulness": scores.get("faithfulness"),
        "completeness": scores.get("completeness"),
        "specificity": scores.get("specificity"),
        "investigative_stance": scores.get("investigative_stance"),
        "judge_raw_tail": text[-400:],
    }


# ── CSV assembly ───────────────────────────────────────────────────────────


async def _score_file(path: Path, no_judge: bool, venue_own: dict[str, set[str]]) -> dict:
    run = json.loads(path.read_text())

    # Phase 1 evidence set: union of grounding entries + fetched URLs + provider pills.
    # Grounding entries carry real domain from web.domain; fetched URLs parse directly.
    p1_entries: list[dict] = []
    seen: set[str] = set()
    for e in run.get("grounding_entries") or []:
        url = e.get("url")
        if url and url not in seen:
            seen.add(url)
            p1_entries.append({"url": url, "domain": e.get("domain")})
    for url in run.get("fetched_urls") or []:
        if url and url not in seen:
            seen.add(url)
            p1_entries.append({"url": url, "domain": _domain_of(url)})
    for p in run.get("provider_pills") or []:
        url = p.get("url")
        if url and url not in seen:
            seen.add(url)
            p1_entries.append({"url": url, "domain": p.get("domain") or _domain_of(url)})
    # Final evidence set: drawer_sources already carry domain (grounding: from web.domain; provider: from pill)
    final_entries = [
        {"url": s.get("url"), "domain": s.get("domain")}
        for s in (run.get("drawer_sources") or []) if s.get("url")
    ]

    own = venue_own.get(run.get("venue_key", ""), set())
    phase1 = _diversity_stats(p1_entries, own)
    final = _diversity_stats(final_entries, own)
    wall = _wall_overlap(run.get("drawer_sources") or [])
    providers = _provider_presence(run.get("drawer_sources") or [])

    row: dict = {
        "variant": run.get("variant"),
        "venue_key": run.get("venue_key"),
        "query_id": run.get("query_id"),
        "primary_probe": run.get("query_primary_probe"),
        "elapsed_s": run.get("elapsed_s"),
        "timed_out": run.get("timed_out"),
        "error": run.get("error"),
        "synth_outcome": run.get("synth_outcome"),
        "gap_ran": run.get("gap_ran"),
        "specialists_dispatched": ",".join(run.get("specialists_dispatched") or []),
        # Phase 1
        "p1_urls": phase1["n_urls"],
        "p1_unique_domains": phase1["unique_domains"],
        "p1_top_domain": phase1["top_domain"],
        "p1_top_domain_share": phase1["top_domain_share"],
        "p1_category_count": phase1["category_count"],
        "p1_categories": ";".join(phase1["categories"]),
        # Final
        "final_urls": final["n_urls"],
        "final_unique_domains": final["unique_domains"],
        "final_top_domain": final["top_domain"],
        "final_top_domain_share": final["top_domain_share"],
        "final_category_count": final["category_count"],
        "final_categories": ";".join(final["categories"]),
        # Wall + providers
        "wall_brand_count": wall["wall_brand_count"],
        "wall_brands": ";".join(wall["wall_brands_matched"]),
        "has_google_maps_pill": providers["has_google_maps_pill"],
        "has_google_reviews_pill": providers["has_google_reviews_pill"],
        "has_tripadvisor_pill": providers["has_tripadvisor_pill"],
        # Tokens + tools
        "tokens_total": (run.get("token_totals") or {}).get("total", 0),
        "tokens_prompt": (run.get("token_totals") or {}).get("prompt", 0),
        "tokens_candidates": (run.get("token_totals") or {}).get("candidates", 0),
        "tool_call_counts": json.dumps(run.get("tool_call_counts") or {}),
    }

    if no_judge or not run.get("final_report"):
        row.update({
            "faithfulness": None,
            "completeness": None,
            "specificity": None,
            "investigative_stance": None,
            "judge_error": None if no_judge else "no_final_report",
        })
    else:
        try:
            judge = await _score_with_gemini(run)
        except Exception as e:  # noqa: BLE001
            judge = {"judge_error": f"{type(e).__name__}: {e}"}
        row.update({
            "faithfulness": judge.get("faithfulness"),
            "completeness": judge.get("completeness"),
            "specificity": judge.get("specificity"),
            "investigative_stance": judge.get("investigative_stance"),
            "judge_error": judge.get("judge_error"),
        })

    return row


async def _main_async(args) -> int:
    # Optional per-venue "own domain" map for category 6 detection.
    venue_own: dict[str, set[str]] = {}
    if args.venue_own:
        venue_own = {k: set(v) for k, v in json.loads(Path(args.venue_own).read_text()).items()}

    results_dir = Path(args.results)
    files = sorted(results_dir.glob("*.json"))
    if not files:
        print(f"[score] no run JSONs in {results_dir}", flush=True)
        return 2

    print(f"[score] scoring {len(files)} runs (judge={'OFF' if args.no_judge else 'ON'})", flush=True)

    sem = asyncio.Semaphore(args.judge_concurrency)

    async def _one(path: Path) -> dict:
        async with sem:
            row = await _score_file(path, args.no_judge, venue_own)
            print(
                f"[score] {path.name} → "
                f"final_top%={row['final_top_domain_share']} "
                f"cat_cov={row['final_category_count']} "
                f"faith={row.get('faithfulness')}",
                flush=True,
            )
            return row

    rows = await asyncio.gather(*(_one(p) for p in files))

    if not rows:
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"[score] wrote {out_path} ({len(rows)} rows)", flush=True)
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, help="directory of per-run JSONs")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument("--no-judge", action="store_true", help="skip Gemini judge (deterministic metrics only)")
    parser.add_argument("--judge-concurrency", type=int, default=4)
    parser.add_argument(
        "--venue-own",
        help="optional JSON file: {venue_key: [own_domains]} for venue_own category detection",
    )
    args = parser.parse_args()

    # Env setup mirrors run_matrix.py
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "superextra-site")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

    def _load_dotenv(path: Path) -> None:
        if not path.exists():
            return
        for line in path.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    _load_dotenv(AGENT_DIR / ".env")
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(_main())
