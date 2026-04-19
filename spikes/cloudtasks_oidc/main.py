"""Spike C/H/I echo service.

/run  — receives POST, echoes headers + body for OIDC auth verification.
/sleep?seconds=N  — sleeps N seconds then returns, for dispatch-deadline and
                    SIGTERM behavior tests.
"""
import asyncio
import json
import os
import signal
import time
from fastapi import FastAPI, Request

app = FastAPI()

@app.get("/")
def health():
    return {"ok": True}

@app.post("/run")
async def run(req: Request):
    body = await req.body()
    try:
        parsed = json.loads(body) if body else None
    except Exception:
        parsed = {"_unparsable": True, "bytes": len(body)}

    info = {
        "ok": True,
        "headers_seen": {
            k: v for k, v in req.headers.items()
            if k.lower().startswith(("x-cloudtasks", "authorization", "x-goog"))
        },
        "body": parsed,
        "env": {k: os.environ.get(k, "") for k in ("K_SERVICE", "K_REVISION", "GOOGLE_CLOUD_PROJECT")},
    }
    # Mask the auth token so we don't echo it back in full
    if "authorization" in info["headers_seen"]:
        info["headers_seen"]["authorization"] = info["headers_seen"]["authorization"][:20] + "…"
    print(json.dumps(info), flush=True)
    return info


# ── H — dispatch-deadline behavior ──────────────────────────────────────────
# Sleep for N seconds, log periodic heartbeats, return at the end.
# Cloud Tasks dispatch-deadline will cancel the inbound request before this
# returns if seconds > dispatchDeadline.

@app.post("/sleep")
async def sleep_endpoint(req: Request):
    seconds = int(req.query_params.get("seconds", "30"))
    task_name = req.headers.get("x-cloudtasks-taskname", "manual")
    retry_count = req.headers.get("x-cloudtasks-taskretrycount", "0")
    exec_count = req.headers.get("x-cloudtasks-taskexecutioncount", "0")
    print(json.dumps({
        "stage": "sleep_begin",
        "seconds": seconds,
        "task_name": task_name,
        "retry_count": retry_count,
        "exec_count": exec_count,
        "t": time.time(),
    }), flush=True)
    try:
        for elapsed in range(1, seconds + 1):
            await asyncio.sleep(1)
            if elapsed % 5 == 0 or elapsed in (1, 2, 3):
                print(json.dumps({
                    "stage": "sleep_tick",
                    "elapsed_s": elapsed,
                    "task_name": task_name,
                    "t": time.time(),
                }), flush=True)
    except asyncio.CancelledError:
        # This is the key observation for H: did Cloud Run propagate the
        # upstream cancellation to the handler coroutine?
        print(json.dumps({
            "stage": "sleep_cancelled",
            "task_name": task_name,
            "t": time.time(),
        }), flush=True)
        raise

    print(json.dumps({
        "stage": "sleep_done",
        "seconds": seconds,
        "task_name": task_name,
        "t": time.time(),
    }), flush=True)
    return {"ok": True, "seconds": seconds, "task_name": task_name}


# ── I — SIGTERM handler ─────────────────────────────────────────────────────
# Observe SIGTERM arrival time during revision rollout / instance shutdown.

_original_sigterm = signal.getsignal(signal.SIGTERM)

def _on_sigterm(signum, frame):
    print(json.dumps({
        "stage": "SIGTERM",
        "signum": signum,
        "t": time.time(),
    }), flush=True)
    if callable(_original_sigterm):
        _original_sigterm(signum, frame)

signal.signal(signal.SIGTERM, _on_sigterm)
