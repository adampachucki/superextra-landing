"""Deploy the probe apps to Agent Runtime.

Run:  cd agent && PYTHONPATH=.. .venv/bin/python -m agent.probe.deploy

Idempotent: if a probe with the same display_name exists, returns its
resource_name without redeploying. Pass --redeploy to force rebuild.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import vertexai
from vertexai import agent_engines

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
STAGING_BUCKET = os.environ.get(
    "PROBE_STAGING_BUCKET", "gs://superextra-site-agent-engine-staging"
)

# Resource names recorded here so subsequent harness runs find them.
STATE_FILE = Path(__file__).parent / "deployed_resources.json"

REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines,adk]==1.147.0",
    "google-adk==1.28.0",
    "google-cloud-firestore==2.22.0",
    "typing-extensions>=4.12",
    "requests>=2.31",
]

# Extra packages bundled into the deployment so the agent module is
# importable on the runtime side.
EXTRA_PACKAGES = ["./probe"]

DISPLAY_NAMES = {
    "lifecycle": "superextra-probe-lifecycle",
    "event_shape": "superextra-probe-event-shape",
    "kitchen": "superextra-probe-kitchen",
    "gemini3": "superextra-probe-gemini3",
    "prod_shape": "superextra-probe-prod-shape",
}


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def _find_existing(display_name: str):
    for ae in agent_engines.list():
        if ae.display_name == display_name:
            return ae
    return None


def deploy_one(flavour: str, app_factory, redeploy: bool, env_vars: dict | None = None) -> str:
    display_name = DISPLAY_NAMES[flavour]
    existing = _find_existing(display_name)
    if existing and not redeploy:
        print(f"[{flavour}] reusing existing: {existing.resource_name}")
        return existing.resource_name
    if existing and redeploy:
        print(f"[{flavour}] deleting existing: {existing.resource_name}")
        existing.delete(force=True)

    print(f"[{flavour}] creating ({display_name}) — this can take several minutes")
    t0 = time.monotonic()
    app = app_factory()
    # Wrap our ADK `App` in `AdkApp` so it exposes the
    # query/stream_query/async_stream_query methods that
    # agent_engines.create expects on a deployable object.
    deployable = agent_engines.AdkApp(app=app)
    remote = agent_engines.create(
        agent_engine=deployable,
        display_name=display_name,
        requirements=REQUIREMENTS,
        extra_packages=EXTRA_PACKAGES,
        # IMPORTANT: per-flavour gcs_dir_name so concurrent deploys don't
        # overwrite each other's pickle in the staging bucket. Without
        # this, two parallel deploys both write to
        # gs://.../agent_engine/agent_engine.pkl and one wins.
        gcs_dir_name=f"agent_engine_{flavour}",
        # GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are reserved by
        # Agent Runtime — set automatically. Don't pass them.
        env_vars=env_vars or {},
    )
    elapsed = time.monotonic() - t0
    print(f"[{flavour}] created in {elapsed:.1f}s: {remote.resource_name}")
    return remote.resource_name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--redeploy", action="store_true", help="force redeploy")
    ap.add_argument(
        "--flavour",
        choices=["lifecycle", "event_shape", "kitchen", "gemini3", "prod_shape", "both"],
        default="both",
    )
    args = ap.parse_args()

    vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING_BUCKET)

    # Import factories LATE so vertexai.init runs first (Agent Engine is
    # picky about init order in some SDK versions). Use top-level `probe.`
    # path so cloudpickle records the same module name the deployed
    # runtime sees (extra_packages bundles `./probe` as the package root).
    from probe.agent import make_lifecycle_app, make_event_shape_app

    state = _load_state()
    if args.flavour in ("lifecycle", "both"):
        state["lifecycle"] = deploy_one("lifecycle", make_lifecycle_app, args.redeploy)
    if args.flavour in ("event_shape", "both"):
        state["event_shape"] = deploy_one(
            "event_shape", make_event_shape_app, args.redeploy
        )
    if args.flavour == "kitchen":
        from probe.kitchen_sink import make_kitchen_app
        from google.cloud.aiplatform_v1.types.env_var import SecretRef
        kitchen_env = {
            "PLAIN_VAR": "plain-value",
            "SECRET_VAR": SecretRef(secret="probe-test-key", version="latest"),
        }
        state["kitchen"] = deploy_one(
            "kitchen", make_kitchen_app, args.redeploy, env_vars=kitchen_env
        )
    if args.flavour == "gemini3":
        from probe.gemini3 import make_gemini3_app
        state["gemini3"] = deploy_one(
            "gemini3", make_gemini3_app, args.redeploy
        )
    if args.flavour == "prod_shape":
        from probe.prod_shape import make_prod_shape_app
        state["prod_shape"] = deploy_one(
            "prod_shape", make_prod_shape_app, args.redeploy
        )
    _save_state(state)
    print("\nResources written to:", STATE_FILE)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
