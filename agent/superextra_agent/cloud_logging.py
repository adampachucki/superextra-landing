"""Small structured-log helper for Agent Engine runtime diagnostics."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


log = logging.getLogger(__name__)


def emit_cloud_log(event: str, *, severity: str = "INFO", **fields: Any) -> None:
    """Emit one structured JSON log row to stdout."""

    payload = {
        "severity": severity,
        "message": "superextra_agent_runtime",
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    payload.update({k: v for k, v in fields.items() if v is not None})
    _attach_trace_fields(payload)

    try:
        print(json.dumps(payload, default=str, ensure_ascii=False), flush=True)
    except Exception:  # noqa: BLE001
        log.exception("failed to emit structured cloud log")


def _attach_trace_fields(payload: dict[str, Any]) -> None:
    try:
        from opentelemetry import trace
    except Exception:
        return

    try:
        span_context = trace.get_current_span().get_span_context()
        if not span_context.is_valid:
            return
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if project:
            trace_id = f"{span_context.trace_id:032x}"
            payload["logging.googleapis.com/trace"] = (
                f"projects/{project}/traces/{trace_id}"
            )
        payload["logging.googleapis.com/spanId"] = f"{span_context.span_id:016x}"
        payload["logging.googleapis.com/trace_sampled"] = bool(
            span_context.trace_flags.sampled
        )
    except Exception:
        return
