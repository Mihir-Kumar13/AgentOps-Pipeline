"""The triage agent loop, built with LangGraph.

    llm ──tool calls──► tools ──► llm
     │
     └──text──► finalize ──valid──► END
                   └──invalid (replan)──► llm

Limits (CLAUDE.md section 5) are enforced here, not in the prompt:
- max tool calls: the run stops with status "tool_limit".
- max replans: the run stops with status "replan_limit" or "invalid_output".
  A replan is any turn the model must redo: invalid final JSON, an empty reply,
  an unknown tool, or a duplicate call (same tool + same args = a loop).
- timeout: checked before every step, the run stops with status "timeout".

Every run is traced (agent/telemetry/spans.py); the spans are no-ops unless
telemetry is enabled.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from agent.app.schemas import Alert, TriageReport
from agent.app.tools import TOOL_NAMES, TOOL_SPECS, ToolClient
from agent.config import Limits
from agent.llm.base import LLMClient, Message
from agent.llm.pricing import cost_usd
from agent.prompts import Prompt
from agent.telemetry.spans import chat_span, finish_run, mark_error, run_span, tool_span

RUNNING = "running"


@dataclass
class RunResult:
    alert_id: str
    status: str  # ok | invalid_output | tool_limit | replan_limit | timeout | error
    report: dict | None
    tool_calls: list[dict] = field(default_factory=list)
    tool_errors: int = 0
    replans: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class AgentState(TypedDict):
    messages: list[Message]
    calls_log: list[dict]
    tool_errors: int
    replans: int
    input_tokens: int
    output_tokens: int
    status: str
    report: dict | None
    error: str | None


class TriageAgent:
    def __init__(self, llm: LLMClient, prompt: Prompt, limits: Limits, release: str = "stable"):
        self.llm = llm
        self.prompt = prompt
        self.limits = limits
        # stable | canary: labels all telemetry so canary analysis can compare the two.
        self.release = release

    def run(self, alert: Alert, tools: ToolClient) -> RunResult:
        with run_span(
            alert.alert_id, self.llm.provider, self.llm.model, self.prompt.version, self.release
        ) as (span, ctx):
            result = self._run(alert, tools, ctx)
            finish_run(span, result, self.release)
        return result

    def _run(self, alert: Alert, tools: ToolClient, ctx) -> RunResult:
        start = time.monotonic()
        deadline = start + self.limits.timeout_s
        graph = self._build(tools, deadline, ctx)
        first = Message(
            role="user",
            content="Triage this alert.\n\nAlert:\n" + json.dumps(alert.model_dump()),
        )
        state: AgentState = graph.invoke(
            {
                "messages": [first],
                "calls_log": [],
                "tool_errors": 0,
                "replans": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "status": RUNNING,
                "report": None,
                "error": None,
            },
            config={"recursion_limit": 100},
        )
        return RunResult(
            alert_id=alert.alert_id,
            status=state["status"],
            report=state["report"],
            tool_calls=state["calls_log"],
            tool_errors=state["tool_errors"],
            replans=state["replans"],
            input_tokens=state["input_tokens"],
            output_tokens=state["output_tokens"],
            cost_usd=cost_usd(self.llm.model, state["input_tokens"], state["output_tokens"]),
            latency_s=round(time.monotonic() - start, 3),
            provider=self.llm.provider,
            model=self.llm.model,
            prompt_version=self.prompt.version,
            error=state["error"],
        )

    def _build(self, tools: ToolClient, deadline: float, ctx):
        limits = self.limits
        llm = self.llm

        def llm_node(state: AgentState) -> dict:
            if time.monotonic() > deadline:
                return {"status": "timeout"}
            with chat_span(ctx, llm.provider, llm.model) as span:
                try:
                    resp = llm.chat(self.prompt.text, state["messages"], TOOL_SPECS)
                except Exception as exc:  # provider/network failure ends the run, never crashes
                    span.record_exception(exc)
                    mark_error(span, type(exc).__name__, str(exc))
                    return {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:500]}
                span.set_attributes(
                    {
                        "gen_ai.usage.input_tokens": resp.input_tokens,
                        "gen_ai.usage.output_tokens": resp.output_tokens,
                    }
                )
            return {
                "messages": state["messages"] + [resp.message],
                "input_tokens": state["input_tokens"] + resp.input_tokens,
                "output_tokens": state["output_tokens"] + resp.output_tokens,
            }

        def tools_node(state: AgentState) -> dict:
            calls = state["messages"][-1].tool_calls
            log = list(state["calls_log"])
            if len(log) + len(calls) > limits.max_tool_calls:
                return {"status": "tool_limit"}
            seen = {(c["name"], json.dumps(c["args"], sort_keys=True)) for c in log}
            messages = list(state["messages"])
            errors, replans = state["tool_errors"], state["replans"]
            for call in calls:
                key = (call.name, json.dumps(call.args, sort_keys=True))
                entry = {
                    "name": call.name,
                    "args": call.args,
                    "error": None,
                    "error_type": None,  # tool_error | unknown_tool | duplicate_call
                    "duplicate": False,
                }
                with tool_span(ctx, call.name, call.id) as span:
                    if call.name not in TOOL_NAMES:
                        result, entry["error"] = None, f"unknown tool {call.name!r}"
                        entry["error_type"] = "unknown_tool"
                        replans += 1
                    elif key in seen:
                        result, entry["duplicate"] = None, True
                        entry["error"] = "duplicate call: you already have this result"
                        entry["error_type"] = "duplicate_call"
                        replans += 1
                    else:
                        result, entry["error"] = tools.call(call.name, call.args)
                        if entry["error"]:
                            entry["error_type"] = "tool_error"
                            errors += 1
                    if entry["error_type"]:
                        mark_error(span, entry["error_type"], entry["error"])
                seen.add(key)
                log.append(entry)
                payload = {"error": entry["error"]} if entry["error"] else result
                messages.append(
                    Message(
                        role="tool",
                        content=json.dumps(payload),
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
            update = {
                "messages": messages,
                "calls_log": log,
                "tool_errors": errors,
                "replans": replans,
            }
            if replans > limits.max_replans:
                update["status"] = "replan_limit"
            return update

        def finalize_node(state: AgentState) -> dict:
            text = state["messages"][-1].content
            try:
                report = TriageReport.model_validate_json(_strip_fences(text))
            except ValidationError as exc:
                if state["replans"] >= limits.max_replans:
                    return {"status": "invalid_output", "error": _short(exc)}
                fix = Message(
                    role="user",
                    content=(
                        f"Your answer was not a valid report: {_short(exc)}. "
                        "Reply with ONLY the JSON object described in the instructions."
                    ),
                )
                return {"messages": state["messages"] + [fix], "replans": state["replans"] + 1}
            return {"status": "ok", "report": report.model_dump()}

        def after_llm(state: AgentState) -> str:
            if state["status"] != RUNNING:
                return END
            return "tools" if state["messages"][-1].tool_calls else "finalize"

        def continue_or_end(state: AgentState) -> str:
            return "llm" if state["status"] == RUNNING else END

        g = StateGraph(AgentState)
        g.add_node("llm", llm_node)
        g.add_node("tools", tools_node)
        g.add_node("finalize", finalize_node)
        g.add_edge(START, "llm")
        g.add_conditional_edges("llm", after_llm, ["tools", "finalize", END])
        g.add_conditional_edges("tools", continue_or_end, ["llm", END])
        g.add_conditional_edges("finalize", continue_or_end, ["llm", END])
        return g.compile()


def _strip_fences(text: str) -> str:
    """Models sometimes wrap JSON in ``` fences despite instructions; that is not a failure."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _short(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:300]
