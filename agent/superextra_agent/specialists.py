from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from pathlib import Path

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"
MODEL = "gemini-2.5-pro"

def load_instructions(name: str) -> str:
    return (INSTRUCTIONS_DIR / f"{name}.md").read_text()

market_landscape = LlmAgent(
    name="market_landscape",
    model=MODEL,
    description="Analyzes restaurant market dynamics: openings, closings, competitor activity, cuisine trends, saturation, white space.",
    instruction=load_instructions("market_landscape"),
    tools=[google_search],
    output_key="market_result",
)

menu_pricing = LlmAgent(
    name="menu_pricing",
    model=MODEL,
    description="Analyzes menus, pricing, delivery markups, promotions, trending dishes.",
    instruction=load_instructions("menu_pricing"),
    tools=[google_search],
    output_key="pricing_result",
)

revenue_sales = LlmAgent(
    name="revenue_sales",
    model=MODEL,
    description="Estimates revenue, check size, seasonality, channel splits, platform share.",
    instruction=load_instructions("revenue_sales"),
    tools=[google_search],
    output_key="revenue_result",
)

guest_intelligence = LlmAgent(
    name="guest_intelligence",
    model=MODEL,
    description="Analyzes review sentiment, complaint/praise patterns, rating trends.",
    instruction=load_instructions("guest_intelligence"),
    tools=[google_search],
    output_key="guest_result",
)

location_traffic = LlmAgent(
    name="location_traffic",
    model=MODEL,
    description="Analyzes foot traffic, demographics, purchasing power, rent, trade areas.",
    instruction=load_instructions("location_traffic"),
    tools=[google_search],
    output_key="location_result",
)

operations = LlmAgent(
    name="operations",
    model=MODEL,
    description="Analyzes labor market, salary benchmarks, rent, supplier pricing.",
    instruction=load_instructions("operations"),
    tools=[google_search],
    output_key="ops_result",
)

marketing_digital = LlmAgent(
    name="marketing_digital",
    model=MODEL,
    description="Analyzes social media, ads, delivery platform presence, web presence.",
    instruction=load_instructions("marketing_digital"),
    tools=[google_search],
    output_key="marketing_result",
)

ALL_SPECIALISTS = [
    market_landscape,
    menu_pricing,
    revenue_sales,
    guest_intelligence,
    location_traffic,
    operations,
    marketing_digital,
]
