from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from google.genai import types
from pathlib import Path
import os

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"

_version = os.environ.get("GEMINI_VERSION", "3.1")

if _version == "3.1":
    MODEL = "gemini-3.1-pro-preview"
    SPECIALIST_MODEL = "gemini-3.1-pro-preview-customtools"
    THINKING_CONFIG = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
    )
else:
    MODEL = "gemini-2.5-pro"
    SPECIALIST_MODEL = MODEL
    THINKING_CONFIG = None

def load_instructions(name: str) -> str:
    return (INSTRUCTIONS_DIR / f"{name}.md").read_text()

market_landscape = LlmAgent(
    name="market_landscape",
    model=SPECIALIST_MODEL,
    description="Analyzes restaurant market dynamics: openings, closings, competitor activity, cuisine trends, saturation, white space.",
    instruction=load_instructions("market_landscape"),
    tools=[google_search],
    output_key="market_result",
    generate_content_config=THINKING_CONFIG,
)

menu_pricing = LlmAgent(
    name="menu_pricing",
    model=SPECIALIST_MODEL,
    description="Analyzes menus, pricing, delivery markups, promotions, trending dishes.",
    instruction=load_instructions("menu_pricing"),
    tools=[google_search],
    output_key="pricing_result",
    generate_content_config=THINKING_CONFIG,
)

revenue_sales = LlmAgent(
    name="revenue_sales",
    model=SPECIALIST_MODEL,
    description="Estimates revenue, check size, seasonality, channel splits, platform share.",
    instruction=load_instructions("revenue_sales"),
    tools=[google_search],
    output_key="revenue_result",
    generate_content_config=THINKING_CONFIG,
)

guest_intelligence = LlmAgent(
    name="guest_intelligence",
    model=SPECIALIST_MODEL,
    description="Analyzes review sentiment, complaint/praise patterns, rating trends.",
    instruction=load_instructions("guest_intelligence"),
    tools=[google_search],
    output_key="guest_result",
    generate_content_config=THINKING_CONFIG,
)

location_traffic = LlmAgent(
    name="location_traffic",
    model=SPECIALIST_MODEL,
    description="Analyzes foot traffic, demographics, purchasing power, rent, trade areas.",
    instruction=load_instructions("location_traffic"),
    tools=[google_search],
    output_key="location_result",
    generate_content_config=THINKING_CONFIG,
)

operations = LlmAgent(
    name="operations",
    model=SPECIALIST_MODEL,
    description="Analyzes labor market, salary benchmarks, rent, supplier pricing.",
    instruction=load_instructions("operations"),
    tools=[google_search],
    output_key="ops_result",
    generate_content_config=THINKING_CONFIG,
)

marketing_digital = LlmAgent(
    name="marketing_digital",
    model=SPECIALIST_MODEL,
    description="Analyzes social media, ads, delivery platform presence, web presence.",
    instruction=load_instructions("marketing_digital"),
    tools=[google_search],
    output_key="marketing_result",
    generate_content_config=THINKING_CONFIG,
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
