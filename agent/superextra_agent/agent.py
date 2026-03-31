from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents import LlmAgent
from .specialists import ALL_SPECIALISTS, MODEL
from pathlib import Path

INSTRUCTIONS_DIR = Path(__file__).parent / "instructions"

parallel_research = ParallelAgent(
    name="parallel_research",
    sub_agents=ALL_SPECIALISTS,
    description="Runs all specialist research agents in parallel.",
)

synthesizer = LlmAgent(
    name="synthesizer",
    model=MODEL,
    instruction=(INSTRUCTIONS_DIR / "synthesizer.md").read_text(),
    description="Synthesizes findings from all specialist agents into a cohesive report.",
    output_key="final_report",
)

research_pipeline = SequentialAgent(
    name="research_pipeline",
    sub_agents=[parallel_research, synthesizer],
    description="Full research pipeline: runs 7 specialist agents in parallel, then synthesizes findings into a cohesive market intelligence report. Use this when the question has enough context (restaurant, location, or area) to research.",
)

root_agent = LlmAgent(
    name="router",
    model=MODEL,
    instruction=(INSTRUCTIONS_DIR / "router.md").read_text(),
    description="Routes user questions to research or asks for clarification.",
    sub_agents=[research_pipeline],
    output_key="router_response",
)
