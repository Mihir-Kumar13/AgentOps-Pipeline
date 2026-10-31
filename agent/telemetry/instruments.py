"""Span and metric names: the telemetry contract from docs/METRICS.md.

Names here must match docs/METRICS.md, the Prometheus alert rules and the Grafana
dashboard. Change them in all four places or not at all.

The tracer and meter come from the global OTel API. Before setup_telemetry() runs
they are proxies, so importing this module never needs a collector.
"""

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

AGENT_NAME = "triage-agent"

tracer = trace.get_tracer(AGENT_NAME)
meter = metrics.get_meter(AGENT_NAME)

# Prometheus names after the collector's translation: counters get a `_total` suffix.
# Units are left empty on purpose so no unit suffix is appended to the names below.
runs = meter.create_counter("agent_runs", description="Agent runs by release and status")
run_cost = meter.create_histogram("agent_run_cost_usd", description="Cost of one run in USD")
run_duration = meter.create_histogram(
    "agent_run_duration_seconds", description="Wall-clock time of one run"
)
tool_errors = meter.create_counter("agent_tool_errors", description="Failed tool calls by tool")
loops = meter.create_counter(
    "agent_loops", description="Runs stopped by the tool-call or replan limit"
)
output_valid = meter.create_counter(
    "agent_output_valid", description="Runs by whether the final report passed the schema"
)

COST_BUCKETS = [0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1]
DURATION_BUCKETS = [0.5, 1, 2, 5, 10, 15, 20, 30, 45, 60]


def histogram_views() -> list[View]:
    """Buckets sized for this agent; OTel's defaults are for milliseconds, not USD or seconds."""
    return [
        View(
            instrument_name="agent_run_cost_usd",
            aggregation=ExplicitBucketHistogramAggregation(COST_BUCKETS),
        ),
        View(
            instrument_name="agent_run_duration_seconds",
            aggregation=ExplicitBucketHistogramAggregation(DURATION_BUCKETS),
        ),
    ]
