"""Tool definitions shown to the LLM, and the HTTP client that runs them on mock-tools."""

from typing import Any

import httpx
from opentelemetry.propagate import inject

from agent.llm.base import ToolSpec

_SERVICE = {"type": "string", "description": "Service name from the alert"}
_WINDOW = {"type": "string", "description": "Look-back window, for example 30m or 1h"}

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        "get_metrics",
        "CPU, memory, error rate and p95 latency series for a service, plus its normal baseline.",
        {
            "type": "object",
            "properties": {"service": _SERVICE, "window": _WINDOW},
            "required": ["service", "window"],
        },
    ),
    ToolSpec(
        "get_logs",
        "Recent log lines for a service. `query` filters lines by text; empty means all.",
        {
            "type": "object",
            "properties": {"service": _SERVICE, "window": _WINDOW, "query": {"type": "string"}},
            "required": ["service", "window", "query"],
        },
    ),
    ToolSpec(
        "get_recent_deploys",
        "Recent deploys of a service with version, time and note.",
        {"type": "object", "properties": {"service": _SERVICE}, "required": ["service"]},
    ),
    ToolSpec(
        "get_runbook",
        "Runbook text for an alert type, for example high_memory or high_error_rate.",
        {
            "type": "object",
            "properties": {"alert_type": {"type": "string"}},
            "required": ["alert_type"],
        },
    ),
    ToolSpec(
        "create_ticket",
        "Open an incident ticket. Returns the ticket id. Only for P1 and P2.",
        {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["severity", "title", "body"],
        },
    ),
]

TOOL_NAMES = {t.name for t in TOOL_SPECS}


class ToolClient:
    """Calls mock-tools over HTTP.

    The alert id travels as a header, not as a tool argument: mock-tools uses it to
    pick the scenario's data, and the LLM never sees or controls it.
    The caller sets the timeout on the httpx client.
    """

    def __init__(self, http: httpx.Client, alert_id: str):
        self._http = http
        self._alert_id = alert_id

    def call(self, name: str, args: dict[str, Any]) -> tuple[Any, str | None]:
        """Return (result, error). Errors are returned, not raised, so the LLM can react."""
        try:
            headers = {"X-Alert-Id": self._alert_id}
            # W3C traceparent: the mock-tools request joins this run's trace.
            inject(headers)
            resp = self._http.post(f"/tools/{name}", json=args, headers=headers)
        except httpx.HTTPError as exc:
            return None, f"tool transport error: {type(exc).__name__}"
        if resp.status_code != 200:
            return None, f"tool returned HTTP {resp.status_code}: {resp.text[:200]}"
        return resp.json(), None
