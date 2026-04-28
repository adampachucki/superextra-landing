"""Weekly transport-cost baseline for the GEAR migration window.

Pulls the last N days of usage proxies for both transports so we can spot
a meaningful spend delta between the legacy Cloud Run worker baseline
and the live Reasoning Engine. NOT a $ figure — Reasoning Engine spend
is opaque from Cloud Monitoring; Vertex AI SKUs only resolve in BigQuery
billing export (not enabled for this project) or the GCP Console
billing UI.

Usage proxies that ARE here:

- gear (Reasoning Engine path): `aiplatform.googleapis.com/generate_content_requests_per_minute_per_project_per_base_model`
  + `aiplatform.googleapis.com/generate_content_input_tokens_per_minute_per_base_model`
  These ARE intended to count Gemini calls made FROM INSIDE the engine.
  **Important caveat (verified 2026-04-27):** at our project level these
  metrics return 0 even when gear runs are happening — Reasoning Engine
  appears to bill Gemini calls against the engine's tenant project,
  not the customer project. The script keeps querying them in case
  Google changes the attribution; until then, dollar-figure comparison
  has to come from the GCP Console Billing UI (last paragraph of the
  output) which DOES surface the spend correctly.
- cloudrun (legacy worker): `run.googleapis.com/request_count` +
  `run.googleapis.com/container/billable_instance_time` for service
  `superextra-worker`. These ARE billed.

Re-run this weekly. After Stage B was flipped on 2026-04-27 19:22 UTC,
worker traffic should taper to sticky cloudrun sessions only and gear
Gemini volume should pick up. The week-over-week delta tells us if
gear's effective cost is wildly different from cloudrun's.

Run with:
    GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=superextra-site \
      agent/.venv/bin/python scripts/cost_baseline.py [--days 7]

Moved from `agent/probe/` to `scripts/` during Phase 9 because the
probe directory was deleted with the rest of the R3 scripts. Reuses
the agent venv since `google-cloud-monitoring` already ships there.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

from google.cloud import monitoring_v3


PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "superextra-site")


def _interval(days: int) -> monitoring_v3.TimeInterval:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return monitoring_v3.TimeInterval(
        start_time=start,
        end_time=end,
    )


def _sum_series(client, name: str, filter_str: str, days: int) -> float:
    """Returns the cumulative sum across all matching series for the window."""
    interval = _interval(days)
    aggregation = monitoring_v3.Aggregation(
        alignment_period={"seconds": days * 86400},
        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_SUM,
        cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
    )
    total = 0.0
    pages = client.list_time_series(
        request={
            "name": name,
            "filter": filter_str,
            "interval": interval,
            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            "aggregation": aggregation,
        }
    )
    for series in pages:
        for point in series.points:
            v = point.value
            total += (
                v.int64_value
                if v.int64_value
                else v.double_value
                if v.double_value
                else 0.0
            )
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    client = monitoring_v3.MetricServiceClient()
    name = f"projects/{PROJECT}"

    print(f"# Transport cost baseline — last {args.days} days, project={PROJECT}")
    print(f"# Stage B flipped 2026-04-27 19:22 UTC; readings before that")
    print(f"# date are pre-flip cloudrun-dominated; after, gear-dominated.\n")

    # gear proxy: Gemini calls from inside the engine
    print("## gear (Reasoning Engine — Gemini calls as proxy)")
    gem_reqs = _sum_series(
        client,
        name,
        'metric.type = "aiplatform.googleapis.com/generate_content_requests_per_minute_per_project_per_base_model"',
        args.days,
    )
    print(f"  generate_content_requests (cumulative): {gem_reqs:,.0f}")
    gem_input = _sum_series(
        client,
        name,
        'metric.type = "aiplatform.googleapis.com/generate_content_input_tokens_per_minute_per_base_model"',
        args.days,
    )
    print(f"  generate_content_input_tokens (cumulative): {gem_input:,.0f}")

    # cloudrun side: legacy worker request count + instance time
    print("\n## cloudrun (legacy worker — directly billed)")
    cr_reqs = _sum_series(
        client,
        name,
        'metric.type = "run.googleapis.com/request_count" AND resource.label.service_name = "superextra-worker"',
        args.days,
    )
    print(f"  worker request_count: {cr_reqs:,.0f}")
    cr_instance_seconds = _sum_series(
        client,
        name,
        'metric.type = "run.googleapis.com/container/billable_instance_time" AND resource.label.service_name = "superextra-worker"',
        args.days,
    )
    print(
        f"  worker billable_instance_time: {cr_instance_seconds:,.1f} container-seconds "
        f"(~{cr_instance_seconds / 3600:.2f} container-hours)"
    )

    # agentStream Cloud Function — common to both transports, single counter
    print("\n## agentStream (POST entry point — common to both transports)")
    as_reqs = _sum_series(
        client,
        name,
        'metric.type = "run.googleapis.com/request_count" AND resource.label.service_name = "agentstream"',
        args.days,
    )
    print(f"  agentStream request_count: {as_reqs:,.0f}")

    print(
        "\n# For dollar figures, see GCP Console → Billing → Reports, filtered by\n"
        "# project=superextra-site. Service breakdown groups Vertex AI SKUs together;\n"
        "# the relevant rows are 'Vertex AI Online Prediction' (engine + Gemini)\n"
        "# and 'Cloud Run' (worker). Compare week-over-week."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
