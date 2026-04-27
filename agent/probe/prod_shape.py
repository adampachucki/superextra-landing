"""Round-2 R2.5 — production agent shape (SequentialAgent + ParallelAgent
+ output_key chains + transfer_to_agent).

Stripped-down replica of `agent/superextra_agent/agent.py`'s structure
without the real specialists or external API calls — exercises the
framework primitives the production agent depends on, so we can verify
they all work under deployed Agent Runtime.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.apps import App

from .probe_plugin import ProbePlugin

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")

# Two fake specialists running under a ParallelAgent. Each writes to a
# distinct output_key, mirroring how our production specialists write
# `pricing_result`, `marketing_result`, etc.
spec_a = LlmAgent(
    name="prod_spec_a",
    model="gemini-2.5-flash",
    instruction="Reply with the single word: 'spec_a_output'.",
    output_key="result_a",
)
spec_b = LlmAgent(
    name="prod_spec_b",
    model="gemini-2.5-flash",
    instruction="Reply with the single word: 'spec_b_output'.",
    output_key="result_b",
)

parallel_specs = ParallelAgent(
    name="prod_parallel",
    sub_agents=[spec_a, spec_b],
)

# Synthesizer reads both outputs from session.state via the prompt
# template — mirrors our production synthesizer pattern.
synth = LlmAgent(
    name="prod_synth",
    model="gemini-2.5-flash",
    instruction=(
        "You will see two upstream results in state: result_a={result_a} and "
        "result_b={result_b}. Reply with the words 'synth_combined: ' followed "
        "by the literal values of both outputs concatenated with a space."
    ),
    output_key="final",
)

# Sequential pipeline: run the parallel block, then the synth.
prod_root = SequentialAgent(
    name="prod_pipeline",
    sub_agents=[parallel_specs, synth],
)


def make_prod_shape_app() -> App:
    return App(
        name="superextra_probe_prod_shape",
        root_agent=prod_root,
        plugins=[ProbePlugin(project=PROJECT)],
    )
