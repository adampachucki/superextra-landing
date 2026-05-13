from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_redeploy_engine():
    path = Path(__file__).resolve().parents[1] / "scripts" / "redeploy_engine.py"
    spec = importlib.util.spec_from_file_location("redeploy_engine", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trace_env_vars_use_google_adk_event_content_mode():
    redeploy_engine = _load_redeploy_engine()

    assert redeploy_engine.TRACE_ENV_VARS == {
        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    }


def test_deploy_script_changes_are_tracked_for_redeploy_staleness():
    redeploy_engine = _load_redeploy_engine()

    assert "agent/scripts/redeploy_engine.py" in redeploy_engine._RUNTIME_PATHS
