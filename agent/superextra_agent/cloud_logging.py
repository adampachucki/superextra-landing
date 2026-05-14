"""Small structured-log helper for Agent Engine runtime diagnostics."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


log = logging.getLogger(__name__)
_cloud_logger: Any | None = None


def _project_id() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT")
        or "superextra-site"
    )


def _get_cloud_logger() -> Any:
    global _cloud_logger
    if _cloud_logger is None:
        from google.cloud import logging as cloud_logging

        client = cloud_logging.Client(project=_project_id())
        _cloud_logger = client.logger("superextra_agent_runtime")
    return _cloud_logger


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, default=str, ensure_ascii=False))


def emit_cloud_log(event: str, *, severity: str = "INFO", **fields: Any) -> None:
    """Emit one structured Cloud Logging row for Agent Engine diagnostics."""

    payload = {
        "message": "superextra_agent_runtime",
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    payload.update({k: v for k, v in fields.items() if v is not None})
    trace_fields = _current_trace_fields()

    try:
        _get_cloud_logger().log_struct(
            _json_safe(payload),
            severity=severity,
            **trace_fields,
        )
    except Exception:  # noqa: BLE001
        _emit_stdout_fallback(payload, severity=severity, trace_fields=trace_fields)


def _emit_stdout_fallback(
    payload: dict[str, Any], *, severity: str, trace_fields: dict[str, Any]
) -> None:
    fallback = {"severity": severity, **payload}
    if trace := trace_fields.get("trace"):
        fallback["logging.googleapis.com/trace"] = trace
    if span_id := trace_fields.get("span_id"):
        fallback["logging.googleapis.com/spanId"] = span_id
    if "trace_sampled" in trace_fields:
        fallback["logging.googleapis.com/trace_sampled"] = trace_fields["trace_sampled"]
    try:
        print(json.dumps(fallback, default=str, ensure_ascii=False), flush=True)
    except Exception:  # noqa: BLE001
        log.exception("failed to emit structured cloud log")


def _current_trace_fields() -> dict[str, Any]:
    try:
        from opentelemetry import trace
    except Exception:
        return {}

    try:
        span_context = trace.get_current_span().get_span_context()
        if not span_context.is_valid:
            return {}
        trace_id = f"{span_context.trace_id:032x}"
        return {
            "trace": f"projects/{_project_id()}/traces/{trace_id}",
            "span_id": f"{span_context.span_id:016x}",
            "trace_sampled": bool(span_context.trace_flags.sampled),
        }
    except Exception:
        return {}
