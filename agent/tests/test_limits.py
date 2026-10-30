"""The agent's hard limits must hold no matter what the model does."""

import json

from agent.app.graph import TriageAgent
from agent.app.schemas import Alert
from agent.app.tools import ToolClient
from agent.config import Limits
from agent.llm.base import Message, ToolCall
from agent.llm.scripted import ScriptedLLM
from agent.prompts import Prompt

ALERT = Alert(
    alert_id="ALR-oom-01", service="checkout-api", summary="x", fired_at="2026-10-01T10:00:00+00:00"
)
PROMPT = Prompt(version="test", text="test")
DEFAULT_LIMITS = Limits()
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


def run(script: list[Message], tools_http, limits: Limits = DEFAULT_LIMITS):
    agent = TriageAgent(ScriptedLLM(script), PROMPT, limits)
    return agent.run(ALERT, ToolClient(tools_http, ALERT.alert_id))


def test_valid_answer_after_tool_call(tools_http):
    result = run([call("get_metrics"), text(VALID)], tools_http)
    assert result.status == "ok"
    assert result.report["severity"] == "P3"
    assert [c["name"] for c in result.tool_calls] == ["get_metrics"]
    assert result.prompt_version == "test"


def test_tool_call_limit_stops_run(tools_http):
    script = [call("get_metrics", i) for i in range(9)] + [text(VALID)]
    result = run(script, tools_http)
    assert result.status == "tool_limit"
    assert len(result.tool_calls) == 8
    assert result.report is None


def test_duplicate_calls_count_as_replans_and_stop(tools_http):
    script = [call("get_metrics")] * 5 + [text(VALID)]
    result = run(script, tools_http)
    assert result.status == "replan_limit"
    assert result.replans == 4
    assert sum(c["duplicate"] for c in result.tool_calls) == 4


def test_invalid_output_is_replanned_then_given_up(tools_http):
    result = run([text("not json")] * 4, tools_http)
    assert result.status == "invalid_output"
    assert result.replans == 3


def test_recovers_after_one_invalid_output(tools_http):
    result = run([text("oops"), text(VALID)], tools_http)
    assert result.status == "ok"
    assert result.replans == 1


def test_code_fenced_json_is_accepted(tools_http):
    result = run([text(f"```json\n{VALID}\n```")], tools_http)
    assert result.status == "ok"


def test_unknown_tool_is_reported_to_model(tools_http):
    result = run([call("delete_database"), text(VALID)], tools_http)
    assert result.status == "ok"
    assert result.replans == 1
    assert result.tool_calls[0]["error"].startswith("unknown tool")


def test_bad_tool_args_count_as_tool_error(tools_http):
    result = run([call("get_metrics", bogus="x"), text(VALID)], tools_http)
    assert result.tool_errors == 1
    assert "HTTP 422" in result.tool_calls[0]["error"]


def test_timeout(tools_http):
    result = run([text(VALID)], tools_http, Limits(timeout_s=-1))
    assert result.status == "timeout"


def test_provider_exception_ends_run_cleanly(tools_http):
    class Boom(ScriptedLLM):
        def chat(self, *a, **k):
            raise ConnectionError("network down")

    agent = TriageAgent(Boom([]), PROMPT, Limits())
    result = agent.run(ALERT, ToolClient(tools_http, ALERT.alert_id))
    assert result.status == "error"
    assert "network down" in result.error
