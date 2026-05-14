from __future__ import annotations

from types import SimpleNamespace

from superextra_agent import cloud_logging


def test_emit_cloud_log_writes_structured_cloud_entry(monkeypatch):
    calls: list[tuple[dict, dict]] = []

    class FakeLogger:
        def log_struct(self, payload, **kwargs):
            calls.append((payload, kwargs))

    monkeypatch.setattr(cloud_logging, "_get_cloud_logger", lambda: FakeLogger())
    monkeypatch.setattr(
        cloud_logging,
        "_current_trace_fields",
        lambda: {
            "trace": "projects/superextra-site/traces/abc",
            "span_id": "span-1",
            "trace_sampled": True,
        },
    )

    cloud_logging.emit_cloud_log(
        "active_stage",
        severity="WARNING",
        sid="sid-1",
        run_id="run-1",
        skipped=None,
    )

    assert calls == [
        (
            {
                "message": "superextra_agent_runtime",
                "event": "active_stage",
                "ts": calls[0][0]["ts"],
                "sid": "sid-1",
                "run_id": "run-1",
            },
            {
                "severity": "WARNING",
                "trace": "projects/superextra-site/traces/abc",
                "span_id": "span-1",
                "trace_sampled": True,
            },
        )
    ]


def test_emit_cloud_log_falls_back_to_structured_stdout(monkeypatch, capsys):
    class BrokenLogger:
        def log_struct(self, _payload, **_kwargs):
            raise RuntimeError("logging unavailable")

    monkeypatch.setattr(cloud_logging, "_get_cloud_logger", lambda: BrokenLogger())
    monkeypatch.setattr(
        cloud_logging,
        "_current_trace_fields",
        lambda: {
            "trace": "projects/superextra-site/traces/abc",
            "span_id": "span-1",
            "trace_sampled": True,
        },
    )

    cloud_logging.emit_cloud_log("finalize_success", sid="sid-1")

    out = capsys.readouterr().out
    assert '"message": "superextra_agent_runtime"' in out
    assert '"event": "finalize_success"' in out
    assert '"severity": "INFO"' in out
    assert '"logging.googleapis.com/trace": "projects/superextra-site/traces/abc"' in out


def test_current_trace_fields_returns_empty_without_valid_span(monkeypatch):
    monkeypatch.setattr(
        "opentelemetry.trace.get_current_span",
        lambda: SimpleNamespace(
            get_span_context=lambda: SimpleNamespace(is_valid=False)
        ),
    )

    assert cloud_logging._current_trace_fields() == {}
