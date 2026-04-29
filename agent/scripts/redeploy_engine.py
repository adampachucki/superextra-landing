#!/usr/bin/env python3
"""Redeploy the Superextra ADK app to the existing Vertex AI Agent Engine.

Dry-run by default. Pass --yes to call agent_engines.update(...).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT = "superextra-site"
LOCATION = "us-central1"
STAGING_BUCKET = "gs://superextra-site-agent-engine-staging"
RESOURCE_NAME = (
    "projects/907466498524/locations/us-central1/"
    "reasoningEngines/1179666575196684288"
)
GCS_DIR_NAME = "agent_engine_staging"
LEGACY_ADC_ACCOUNT = "adam@finebite.co"


def _agent_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_requirements(agent_root: Path) -> list[str]:
    requirements_path = agent_root / "requirements.txt"
    return [
        line.strip()
        for line in requirements_path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _candidate_adc_paths() -> list[Path]:
    return [
        Path.home()
        / ".config"
        / "gcloud"
        / "legacy_credentials"
        / LEGACY_ADC_ACCOUNT
        / "adc.json",
        Path("/home/adam/.config/gcloud/legacy_credentials")
        / LEGACY_ADC_ACCOUNT
        / "adc.json",
    ]


def _resolve_credentials(explicit_path: str | None) -> Path | None:
    if explicit_path:
        return Path(explicit_path).expanduser()

    existing_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing_env:
        return Path(existing_env).expanduser()

    for path in _candidate_adc_paths():
        if path.exists():
            return path

    return None


def _configure_credentials(credentials_path: Path | None, *, project: str) -> None:
    if credentials_path is None:
        return
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)
    os.environ.setdefault("GOOGLE_CLOUD_QUOTA_PROJECT", project)


def _pickle_smoke(app: object) -> int:
    import cloudpickle

    return len(cloudpickle.dumps(app))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Redeploy Superextra's existing Vertex AI Agent Engine."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually run agent_engines.update(...). Default is dry-run.",
    )
    parser.add_argument("--resource-name", default=RESOURCE_NAME)
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--location", default=LOCATION)
    parser.add_argument("--staging-bucket", default=STAGING_BUCKET)
    parser.add_argument("--gcs-dir-name", default=GCS_DIR_NAME)
    parser.add_argument(
        "--credentials",
        help=(
            "Path to legacy ADC json. Defaults to GOOGLE_APPLICATION_CREDENTIALS "
            "or the known adam@finebite.co gcloud legacy_credentials path."
        ),
    )
    parser.add_argument(
        "--skip-pickle-check",
        action="store_true",
        help="Skip the local cloudpickle preflight.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agent_root = _agent_root()
    sys.path.insert(0, str(agent_root))
    os.chdir(agent_root)

    credentials_path = _resolve_credentials(args.credentials)
    _configure_credentials(credentials_path, project=args.project)

    requirements = _read_requirements(agent_root)
    extra_packages = ["./superextra_agent"]

    print("Agent Engine redeploy")
    print(f"  resource:       {args.resource_name}")
    print(f"  project:        {args.project}")
    print(f"  location:       {args.location}")
    print(f"  staging bucket: {args.staging_bucket}")
    print(f"  gcs dir:        {args.gcs_dir_name}")
    print(f"  requirements:   {', '.join(requirements)}")
    print(f"  extra packages: {', '.join(extra_packages)}")
    if credentials_path:
        print(f"  credentials:    {credentials_path}")
    else:
        print(
            "  credentials:    not set "
            "(set GOOGLE_APPLICATION_CREDENTIALS or pass --credentials)"
        )

    from superextra_agent.agent import app

    if not args.skip_pickle_check:
        size = _pickle_smoke(app)
        print(f"  cloudpickle:    ok ({size} bytes)")

    if not args.yes:
        print("\nDry run only. Re-run with --yes to deploy.")
        return 0

    import vertexai
    from vertexai import agent_engines

    vertexai.init(
        project=args.project,
        location=args.location,
        staging_bucket=args.staging_bucket,
    )
    remote = agent_engines.update(
        args.resource_name,
        agent_engine=agent_engines.AdkApp(app=app),
        requirements=requirements,
        gcs_dir_name=args.gcs_dir_name,
        extra_packages=extra_packages,
    )
    print(f"\nUpdated: {remote.resource_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
