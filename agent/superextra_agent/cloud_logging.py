"""Small structured-log helper for Agent Engine runtime diagnostics."""

from __future__ import annotations

import json
import logging
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

    try:
        print(json.dumps(payload, default=str, ensure_ascii=False), flush=True)
    except Exception:  # noqa: BLE001
        log.exception("failed to emit structured cloud log")
