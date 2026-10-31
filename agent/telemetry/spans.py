"""Span helpers for the agent loop, following the OTel GenAI semantic conventions.

    invoke_agent triage-agent      (one per run)
    ├── chat <model>               (one per LLM call)
    └── execute_tool <tool>        (one per tool call)

LangGraph may run nodes outside the caller's context, so child spans take the run's
context explicitly instead of relying on the "current span".
"""

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from agent.telemetry import instruments as ins

if TYPE_CHECKING:
    from agent.app.graph import RunResult

log = logging.getLogger("agent.run")

# gen_ai.provider.name values from the GenAI semantic conventions.
PROVIDER_NAMES = {"gemini": "gcp.gemini", "openai": "openai"}
LOOP_STATUSES = {"tool_limit", "replan_limit"}


def provider_name(provider: str) -> str:
    return PROVIDER_NAMES.get(provider, provider)


@contextmanager
def run_span(alert_id: str, provider: str, model: str, prompt_version: str, release: str):
    attrs = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": ins.AGENT_NAME,
        "gen_ai.provider.name": provider_name(provider),
        "gen_ai.request.model": model,
        "app.agent.prompt_version": prompt_version,
        "app.agent.release": release,
        "app.alert.id": alert_id,
    }
    with ins.tracer.start_as_current_span(
        f"invoke_agent {ins.AGENT_NAME}", kind=SpanKind.INTERNAL, attributes=attrs
    ) as span:
        yield span, trace.set_span_in_context(span)


@contextmanager
def chat_span(ctx: otel_context.Context, provider: str, model: str):
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider_name(provider),
        "gen_ai.request.model": model,
    }
    with ins.tracer.start_as_current_span(
        f"chat {model}", context=ctx, kind=SpanKind.CLIENT, attributes=attrs
    ) as span:
        yield span


@contextmanager
def tool_span(ctx: otel_context.Context, tool: str, call_id: str):
    attrs = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": tool,
        "gen_ai.tool.call.id": call_id,
    }
    with ins.tracer.start_as_current_span(
        f"execute_tool {tool}", context=ctx, kind=SpanKind.INTERNAL, attributes=attrs
    ) as span:
        yield span


RUN_STATUSES = ("ok", "invalid_output", "tool_limit", "replan_limit", "timeout", "error")


def init_series(release: str, model: str, prompt_version: str, tools: list[str]) -> None:
    """Create every counter series at 0 when the agent starts.

    Prometheus cannot see the first increment of a series it has never scraped, so
    without this the dashboards and alerts would undercount each new process.
    """
    labels = {"release": release}
    for status in RUN_STATUSES:
        ins.runs.add(
            0, {**labels, "status": status, "prompt_version": prompt_version, "model": model}
        )
    for valid in ("true", "false"):
        ins.output_valid.add(0, {**labels, "valid": valid})
    ins.loops.add(0, labels)
    for tool in tools:
        ins.tool_calls.add(0, {**labels, "tool": tool})
        ins.tool_errors.add(0, {**labels, "tool": tool})


def mark_error(span: trace.Span, error_type: str, message: str = "") -> None:
    span.set_attribute("error.type", error_type)
    span.set_status(Status(StatusCode.ERROR, message[:200]))


def finish_run(span: trace.Span, result: "RunResult", release: str) -> None:
    """Put run totals on the root span, record the metrics, and log one summary line."""
    span.set_attributes(
        {
            "gen_ai.usage.input_tokens": result.input_tokens,
            "gen_ai.usage.output_tokens": result.output_tokens,
            "app.agent.cost_usd": result.cost_usd,
            "app.agent.tool_calls": len(result.tool_calls),
            "app.agent.replans": result.replans,
            "app.agent.status": result.status,
        }
    )
    if result.status != "ok":
        mark_error(span, result.status, result.error or "")

    labels = {"release": release}
    ins.runs.add(
        1,
        {
            **labels,
            "status": result.status,
            "prompt_version": result.prompt_version,
            "model": result.model,
        },
    )
    ins.run_cost.record(result.cost_usd, labels)
    ins.run_duration.record(result.latency_s, labels)
    ins.output_valid.add(1, {**labels, "valid": str(result.report is not None).lower()})
    if result.status in LOOP_STATUSES:
        ins.loops.add(1, labels)
    for call in result.tool_calls:
        ins.tool_calls.add(1, {**labels, "tool": call["name"]})
        # Loops (duplicate calls) and unknown tools are model mistakes, not tool failures.
        if call.get("error_type") == "tool_error":
            ins.tool_errors.add(1, {**labels, "tool": call["name"]})

    # Emitted inside the run span, so the log line carries the trace id (Loki -> Tempo link).
    log.info(
        "triage run finished",
        extra={
            "alert_id": result.alert_id,
            "status": result.status,
            "model": result.model,
            "cost_usd": result.cost_usd,
            "latency_s": result.latency_s,
            "tool_calls": len(result.tool_calls),
            "severity": (result.report or {}).get("severity"),
            "probable_cause": (result.report or {}).get("probable_cause"),
        },
    )
