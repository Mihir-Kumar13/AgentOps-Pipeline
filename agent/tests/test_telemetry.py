"""Telemetry contract: span names, nesting, attributes and metrics (docs/METRICS.md).

OTel global providers can only be set once per process, so this module installs
in-memory ones at import and every test reads from them.
"""

import json

import pytest
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from agent.app.graph import TriageAgent
from agent.app.schemas import Alert
from agent.app.tools import ToolClient
from agent.config import Limits
from agent.llm.base import Message, ToolCall
from agent.llm.scripted import ScriptedLLM
from agent.prompts import Prompt
from agent.telemetry.instruments import histogram_views

SPANS = InMemorySpanExporter()
READER = InMemoryMetricReader()
_tp = TracerProvider()
_tp.add_span_processor(SimpleSpanProcessor(SPANS))
trace.set_tracer_provider(_tp)
metrics.set_meter_provider(MeterProvider(metric_readers=[READER], views=histogram_views()))

ALERT = Alert(
    alert_id="ALR-oom-01", service="checkout-api", summary="x", fired_at="2026-10-01T10:00:00+00:00"
)
VALID = json.dumps(
    {
        "severity": "P3",
        "probable_cause": "unknown",
        "evidence": ["e"],
        "recommended_action": "a",
        "ticket_id": None,
    }
)


def call(name: str, i: int = 0, **args) -> Message:
    args = args or {"service": "checkout-api", "window": f"{i}m"}
    return Message(role="assistant", tool_calls=[ToolCall(f"c{i}", name, args)])


def text(content: str) -> Message:
    return Message(role="assistant", content=content)


@pytest.fixture(autouse=True)
def clear_spans():
    SPANS.clear()


def run(script, tools_http, release="stable"):
    agent = TriageAgent(ScriptedLLM(script), Prompt("t-v9", "x"), Limits(), release=release)
    return agent.run(ALERT, ToolClient(tools_http, ALERT.alert_id))


def metric_points(name: str) -> list:
    data = READER.get_metrics_data()
    points = []
    for rm in data.resource_metrics if data else []:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == name:
                    points.extend(m.data.data_points)
    return points


def counter_value(name: str, **labels) -> float:
    return sum(
        p.value
        for p in metric_points(name)
        if all(p.attributes.get(k) == v for k, v in labels.items())
    )


def test_span_tree_names_and_nesting(tools_http):
    run(
        [call("get_metrics"), call("get_logs", query="", service="a", window="1h"), text(VALID)],
        tools_http,
    )
    spans = {s.name: s for s in SPANS.get_finished_spans()}
    root = spans["invoke_agent triage-agent"]
    assert {"chat scripted", "execute_tool get_metrics", "execute_tool get_logs"} <= set(spans)
    agent_spans = [
        s for s in SPANS.get_finished_spans() if s.name.split()[0] in ("chat", "execute_tool")
    ]
    assert all(s.parent.span_id == root.context.span_id for s in agent_spans)
    assert len([s for s in agent_spans if s.name == "chat scripted"]) == 3
    # Every span, including mock-tools' HTTP server spans, is in the one run trace.
    assert {s.context.trace_id for s in SPANS.get_finished_spans()} == {root.context.trace_id}


def test_tool_http_span_is_child_of_execute_tool(tools_http):
    run([call("get_metrics"), text(VALID)], tools_http)
    spans = SPANS.get_finished_spans()
    tool = next(s for s in spans if s.name == "execute_tool get_metrics")
    server = next(s for s in spans if s.name == "POST /tools/get_metrics")
    assert server.parent.span_id == tool.context.span_id


def test_root_span_attributes(tools_http):
    result = run([call("get_metrics"), text(VALID)], tools_http, release="canary")
    root = next(s for s in SPANS.get_finished_spans() if s.name.startswith("invoke_agent"))
    a = root.attributes
    assert a["gen_ai.operation.name"] == "invoke_agent"
    assert a["gen_ai.request.model"] == "scripted"
    assert a["app.agent.prompt_version"] == "t-v9"
    assert a["app.agent.release"] == "canary"
    assert a["app.agent.tool_calls"] == 1
    assert a["app.agent.status"] == "ok"
    assert a["gen_ai.usage.input_tokens"] == result.input_tokens
    assert a["app.agent.cost_usd"] == result.cost_usd
    assert root.status.status_code != StatusCode.ERROR


def test_chat_span_has_token_usage(tools_http):
    run([text(VALID)], tools_http)
    chat = next(s for s in SPANS.get_finished_spans() if s.name == "chat scripted")
    assert chat.attributes["gen_ai.usage.input_tokens"] == 10
    assert chat.attributes["gen_ai.usage.output_tokens"] == 5
    assert chat.attributes["gen_ai.operation.name"] == "chat"


def test_tool_error_marks_span_and_counts_metric(tools_http):
    before = counter_value("agent_tool_errors", tool="get_metrics")
    run([call("get_metrics", bogus="x"), text(VALID)], tools_http)
    span = next(s for s in SPANS.get_finished_spans() if s.name == "execute_tool get_metrics")
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "tool_error"
    assert counter_value("agent_tool_errors", tool="get_metrics") == before + 1
    assert counter_value("agent_tool_calls", tool="get_metrics") >= 1


def test_duplicate_call_is_not_a_tool_error(tools_http):
    before = counter_value("agent_tool_errors")
    run([call("get_metrics"), call("get_metrics"), text(VALID)], tools_http)
    dup = [s for s in SPANS.get_finished_spans() if s.attributes.get("error.type")]
    assert [s.attributes["error.type"] for s in dup] == ["duplicate_call"]
    assert counter_value("agent_tool_errors") == before


def test_run_metrics_recorded(tools_http):
    runs_before = counter_value("agent_runs", status="ok", release="stable")
    valid_before = counter_value("agent_output_valid", valid="true")
    run([text(VALID)], tools_http)
    assert counter_value("agent_runs", status="ok", release="stable") == runs_before + 1
    assert counter_value("agent_output_valid", valid="true") == valid_before + 1
    assert metric_points("agent_run_cost_usd")
    assert metric_points("agent_run_duration_seconds")


def test_loop_limit_counts_loop_and_errors_root(tools_http):
    loops_before = counter_value("agent_loops")
    invalid_before = counter_value("agent_output_valid", valid="false")
    run([call("get_metrics")] * 5, tools_http)
    root = next(s for s in SPANS.get_finished_spans() if s.name.startswith("invoke_agent"))
    assert root.status.status_code == StatusCode.ERROR
    assert root.attributes["error.type"] == "replan_limit"
    assert counter_value("agent_loops") == loops_before + 1
    assert counter_value("agent_output_valid", valid="false") == invalid_before + 1


def test_provider_error_marks_chat_span(tools_http):
    class Boom(ScriptedLLM):
        def chat(self, *a, **k):
            raise ConnectionError("network down")

    agent = TriageAgent(Boom([]), Prompt("t", "x"), Limits())
    agent.run(ALERT, ToolClient(tools_http, ALERT.alert_id))
    chat = next(s for s in SPANS.get_finished_spans() if s.name == "chat scripted")
    assert chat.status.status_code == StatusCode.ERROR
    assert chat.attributes["error.type"] == "ConnectionError"
