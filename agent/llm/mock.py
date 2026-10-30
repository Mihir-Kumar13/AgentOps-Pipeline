"""Rule-based stand-in for an LLM, for plumbing tests with zero API cost.

It calls the investigation tools, then decides with simple keyword and threshold
rules. It does not see expected answers, so its score is honest but naive: it is
meant to exercise the pipeline, not to be a good triager.
"""

import json
import re
from datetime import datetime, timedelta

from agent.llm.base import LLMResponse, Message, ToolCall, ToolSpec

INVESTIGATE = ["get_metrics", "get_logs", "get_recent_deploys"]


class MockLLM:
    provider = "mock"
    model = "mock-heuristic-v1"

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMResponse:
        alert = _parse_alert(messages[0].content)
        results = {m.name: _loads(m.content) for m in messages if m.role == "tool"}
        missing = [t for t in INVESTIGATE if t not in results]
        if missing:
            calls = [ToolCall(f"mock_{t}", t, _args(t, alert["service"])) for t in missing]
            return _reply(Message(role="assistant", tool_calls=calls), messages)

        report = decide(alert, results)
        if report["severity"] in ("P1", "P2") and "create_ticket" not in results:
            args = {
                "severity": report["severity"],
                "title": f"{alert['service']}: {report['probable_cause']}",
                "body": "; ".join(report["evidence"]),
            }
            call = ToolCall("mock_create_ticket", "create_ticket", args)
            return _reply(Message(role="assistant", tool_calls=[call]), messages)
        if "create_ticket" in results:
            report["ticket_id"] = results["create_ticket"].get("ticket_id")
        return _reply(Message(role="assistant", content=json.dumps(report)), messages)


def decide(alert: dict, results: dict) -> dict:
    metrics = results.get("get_metrics") or {}
    series = metrics.get("series") or {}
    baseline = metrics.get("baseline") or {}
    logs = (results.get("get_logs") or {}).get("lines") or []
    text = " ".join(line.get("msg", "") for line in logs).lower()

    err = _last(series, "error_rate_pct")
    lat = _last(series, "latency_p95_ms")
    base_lat = baseline.get("latency_p95_ms") or lat or 1.0
    restarts = metrics.get("pod_restarts", 0)
    has_data = any(series.values())

    if not has_data:
        cause = "unknown"
    elif "oomkilled" in text or "outofmemory" in text:
        cause = "oom"
    elif "connection pool" in text or "too many connections" in text:
        cause = "db_saturation"
    elif "timed out" in text or "timeout" in text:
        cause = "dependency_timeout"
    elif _recent_deploy(alert, results) and err >= 2:
        cause = "bad_deploy"
    elif err < 1 and lat <= 1.5 * base_lat:
        cause = "false_alarm"
    else:
        cause = "unknown"

    if cause == "false_alarm":
        severity = "P4"
    elif not has_data:
        severity = "P3"
    elif err >= 10:
        severity = "P1"
    elif err >= 2 or lat > 3 * base_lat or restarts > 0:
        severity = "P2"
    else:
        severity = "P3"

    return {
        "severity": severity,
        "probable_cause": cause,
        "evidence": [f"error_rate={err}%", f"p95={lat}ms (baseline {base_lat}ms)"],
        "recommended_action": "follow the runbook for this cause",
        "ticket_id": None,
    }


def _recent_deploy(alert: dict, results: dict) -> bool:
    fired = datetime.fromisoformat(alert["fired_at"])
    for d in (results.get("get_recent_deploys") or {}).get("deploys") or []:
        at = datetime.fromisoformat(d["deployed_at"])
        if timedelta(0) <= fired - at <= timedelta(minutes=60):
            return True
    return False


def _last(series: dict, key: str) -> float:
    values = series.get(key) or [0]
    return float(values[-1])


def _args(tool: str, service: str) -> dict:
    if tool == "get_metrics":
        return {"service": service, "window": "1h"}
    if tool == "get_logs":
        return {"service": service, "window": "1h", "query": ""}
    return {"service": service}


def _parse_alert(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("mock LLM expects the alert JSON in the first user message")
    return json.loads(match.group(0))


def _loads(text: str) -> dict:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _reply(msg: Message, history: list[Message]) -> LLMResponse:
    # Rough token estimate (4 chars ~ 1 token) so token plumbing is exercised.
    chars = sum(len(m.content) for m in history)
    return LLMResponse(
        message=msg, input_tokens=chars // 4, output_tokens=len(msg.content) // 4 + 5
    )
