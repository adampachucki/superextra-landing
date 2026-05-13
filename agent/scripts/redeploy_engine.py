#!/usr/bin/env python3
"""Redeploy the Superextra ADK app to the existing Vertex AI Agent Engine.

Dry-run by default. Pass --yes to call agent_engines.update(...).

Tracks the deployed runtime commit sha in a tiny GCS metadata blob
alongside the staged pickle (`{staging_bucket}/{gcs_dir}/.deployed_commit`).
Uses it to detect stale Agent Engine runtime packages and to skip noop
redeploys. Pass --check to just print status and exit (non-zero if stale).
Pass --force to override the noop / dirty-tree guards.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT = "superextra-site"
LOCATION = "us-central1"
STAGING_BUCKET = "gs://superextra-site-agent-engine-staging"
RESOURCE_NAME = (
    "projects/907466498524/locations/us-central1/"
    "reasoningEngines/1179666575196684288"
)
GCS_DIR_NAME = "agent_engine_staging"
LEGACY_ADC_ACCOUNT = "adam@finebite.co"
TRACE_ENV_VARS = {
    "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
    # Capture GenAI prompt/response content in official OTel telemetry.
    # This intentionally uses Agent Engine/ADK telemetry rather than a custom
    # prompt sink so traces, logs, and model-call metadata stay correlated.
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
}


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


# ── Deployed-commit tracking ─────────────────────────────────────────────────


_DEPLOYED_MARKER = ".deployed_commit"
_RUNTIME_PATHS = (
    "agent/superextra_agent",
    "agent/requirements.txt",
    "agent/scripts/redeploy_engine.py",
)


def _git_runtime_sha(cwd: Path) -> str | None:
    """Latest commit touching Agent Engine runtime or deploy inputs."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-n", "1", "--format=%H", "--", *_RUNTIME_PATHS],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
        )
        sha = out.decode().strip()
        return sha or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _git_dirty_runtime_paths(cwd: Path) -> list[str]:
    """Lines from `git status --porcelain` for runtime/deploy inputs."""
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *_RUNTIME_PATHS],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
        )
        return [line.rstrip() for line in out.decode().splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def _git_log_summary(cwd: Path, deployed: str, head: str) -> str:
    """Runtime/deploy-path `git log --oneline deployed..head`, or empty."""
    try:
        out = subprocess.check_output(
            ["git", "log", "--oneline", f"{deployed}..{head}", "--", *_RUNTIME_PATHS],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
        )
        return out.decode().rstrip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _gcs_marker_blob(staging_bucket: str, gcs_dir: str, project: str):
    """Return a `google.cloud.storage` blob handle for the deployed-commit marker."""
    from google.cloud import storage

    bucket_name = staging_bucket.removeprefix("gs://").split("/")[0]
    client = storage.Client(project=project)
    return client.bucket(bucket_name).blob(f"{gcs_dir}/{_DEPLOYED_MARKER}")


def _read_deployed_commit(staging_bucket: str, gcs_dir: str, project: str) -> str | None:
    """Last-deployed commit sha from the GCS marker, or None if not set."""
    try:
        blob = _gcs_marker_blob(staging_bucket, gcs_dir, project)
        if not blob.exists():
            return None
        return blob.download_as_text().strip()
    except Exception as exc:  # noqa: BLE001
        print(f"  deployed sha:   could not read marker ({exc})")
        return None


def _write_deployed_commit(
    staging_bucket: str, gcs_dir: str, project: str, sha: str
) -> None:
    """Record the deployed sha in the GCS marker. Best effort; logs on failure."""
    try:
        blob = _gcs_marker_blob(staging_bucket, gcs_dir, project)
        blob.upload_from_string(sha + "\n", content_type="text/plain")
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: could not record deployed sha: {exc}")


def _deployment_env_vars(agent_engine: Any) -> dict[str, Any]:
    """Return currently deployed env vars so update(env_vars=...) preserves them.

    Agent Engine updates replace the whole deployment env list. Preserve existing
    plain and secret env entries before adding telemetry flags.
    """
    deployment = agent_engine.gca_resource.spec.deployment_spec
    return {
        item.name: item.value for item in deployment.env if item.name
    } | {
        item.name: item.secret_ref
        for item in deployment.secret_env
        if item.name and item.secret_ref is not None
    }


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
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Just print latest runtime commit vs deployed runtime status and exit. "
            "Returns non-zero if the deployed runtime is behind."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Override the no-op detection (deployed runtime sha == latest runtime "
            "sha) and the dirty-tree warning. Required to redeploy when nothing "
            "changed."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agent_root = _agent_root()
    repo_root = agent_root.parent  # `git status` paths are repo-relative
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

    runtime_sha = _git_runtime_sha(repo_root)
    deployed_sha = _read_deployed_commit(
        args.staging_bucket, args.gcs_dir_name, args.project
    )
    if runtime_sha:
        print(f"  runtime commit: {runtime_sha}")
    else:
        print("  runtime commit: unknown (not a git repo?)")
    if deployed_sha:
        print(f"  deployed runtime sha: {deployed_sha}")
    else:
        print("  deployed runtime sha: no marker (first deploy after marker added)")

    is_current = bool(runtime_sha and deployed_sha and runtime_sha == deployed_sha)
    dirty = _git_dirty_runtime_paths(repo_root)

    # --check: print status + exit; non-zero iff stale relative to runtime commit
    if args.check:
        if dirty:
            print("\nStatus: ✗ DIRTY — runtime/deploy inputs have uncommitted changes")
            for line in dirty[:10]:
                print(f"  {line}")
            if len(dirty) > 10:
                print(f"  … ({len(dirty) - 10} more)")
            return 1
        if not runtime_sha:
            return 0
        if not deployed_sha:
            print("\nStatus: unknown — no deployed marker (run a deploy to seed it)")
            return 0
        if is_current:
            print("\nStatus: ✓ up to date")
            return 0
        log = _git_log_summary(repo_root, deployed_sha, runtime_sha)
        print("\nStatus: ✗ STALE — deployed runtime is behind packaged runtime")
        if log:
            print("Runtime commits since last deploy:")
            for line in log.splitlines():
                print(f"  {line}")
        return 1

    if dirty:
        print("\nWARNING: runtime/deploy inputs have uncommitted changes:")
        for line in dirty[:10]:
            print(f"  {line}")
        if len(dirty) > 10:
            print(f"  … ({len(dirty) - 10} more)")
        print(
            "  Deployed marker will be set to the latest committed runtime sha, "
            "which won't reflect uncommitted work."
        )

    from superextra_agent.agent import app

    if not args.skip_pickle_check:
        size = _pickle_smoke(app)
        print(f"  cloudpickle:    ok ({size} bytes)")

    if not args.yes:
        print("\nDry run only. Re-run with --yes to deploy.")
        return 0

    if is_current and not args.force:
        print(
            "\nAgent Engine is already at the packaged runtime commit. Skipping redeploy.\n"
            "Use --force to redeploy anyway (e.g. after a marker reset)."
        )
        return 0

    import vertexai
    from vertexai import agent_engines

    vertexai.init(
        project=args.project,
        location=args.location,
        staging_bucket=args.staging_bucket,
    )

    existing = agent_engines.get(args.resource_name)
    env_vars = _deployment_env_vars(existing)
    env_vars.update(TRACE_ENV_VARS)
    print(f"  env vars:       preserving/updating {', '.join(sorted(env_vars))}")

    remote = existing.update(
        agent_engine=agent_engines.AdkApp(app=app),
        requirements=requirements,
        gcs_dir_name=args.gcs_dir_name,
        extra_packages=extra_packages,
        env_vars=env_vars,
    )
    print(f"\nUpdated: {remote.resource_name}")

    if runtime_sha:
        _write_deployed_commit(
            args.staging_bucket, args.gcs_dir_name, args.project, runtime_sha
        )
        print(f"  recorded:       deployed runtime sha = {runtime_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
