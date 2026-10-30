"""Fake observability and ticketing tools with deterministic data.

Data comes from the eval dataset: each scenario carries `mock_data`, keyed by the
alert id that the agent sends in the X-Alert-Id header. Unknown alert ids get a
healthy, boring service, so the API also works for ad-hoc requests.
"""

import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header
from pydantic import BaseModel, ConfigDict

DEFAULT_SCENARIOS = Path(__file__).resolve().parents[2] / "evals/dataset/scenarios.jsonl"

HEALTHY = {
    "metrics": {
        "baseline": {"cpu_pct": 35, "memory_pct": 50, "error_rate_pct": 0.2, "latency_p95_ms": 180},
        "series": {
            "cpu_pct": [34, 36, 35, 35, 34, 36],
            "memory_pct": [50, 51, 50, 50, 51, 50],
            "error_rate_pct": [0.2, 0.2, 0.3, 0.2, 0.2, 0.2],
            "latency_p95_ms": [180, 178, 182, 181, 179, 180],
        },
        "pod_restarts": 0,
    },
    "logs": [],
    "deploys": [],
    "runbook": None,
}

RUNBOOKS = {
    "default": (
        "1. Check metrics against baseline. 2. Check logs for errors. "
        "3. Check recent deploys; roll back if errors started after a deploy. "
        "4. Escalate P1/P2 with a ticket."
    ),
}


def load_scenarios(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            scenario = json.loads(line)
            data[scenario["alert"]["alert_id"]] = scenario["mock_data"]
    return data


SCENARIOS = load_scenarios(Path(os.getenv("SCENARIOS_PATH", DEFAULT_SCENARIOS)))

app = FastAPI(title="mock-tools")


class _Args(BaseModel):
    # Unknown arguments are an error: a changed tool schema must break loudly.
    model_config = ConfigDict(extra="forbid")


class MetricsArgs(_Args):
    service: str
    window: str


class LogsArgs(_Args):
    service: str
    window: str
    query: str = ""


class DeploysArgs(_Args):
    service: str


class RunbookArgs(_Args):
    alert_type: str


class TicketArgs(_Args):
    severity: Literal["P1", "P2", "P3", "P4"]
    title: str
    body: str


def _data(alert_id: str | None) -> dict:
    return {**HEALTHY, **SCENARIOS.get(alert_id or "", {})}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "scenarios": len(SCENARIOS)}


@app.post("/tools/get_metrics")
def get_metrics(args: MetricsArgs, x_alert_id: str | None = Header(None)) -> dict:
    return {"service": args.service, "window": args.window, **_data(x_alert_id)["metrics"]}


@app.post("/tools/get_logs")
def get_logs(args: LogsArgs, x_alert_id: str | None = Header(None)) -> dict:
    lines = _data(x_alert_id)["logs"]
    query = args.query.strip().lower()
    if not query:
        return {"service": args.service, "lines": lines}
    matched = [ln for ln in lines if query in ln["msg"].lower()]
    if matched:
        return {"service": args.service, "lines": matched}
    # A too-narrow query should not hide the evidence completely.
    return {
        "service": args.service,
        "note": f"no lines matched {args.query!r}; showing latest lines",
        "lines": lines[-20:],
    }


@app.post("/tools/get_recent_deploys")
def get_recent_deploys(args: DeploysArgs, x_alert_id: str | None = Header(None)) -> dict:
    return {"service": args.service, "deploys": _data(x_alert_id)["deploys"]}


@app.post("/tools/get_runbook")
def get_runbook(args: RunbookArgs, x_alert_id: str | None = Header(None)) -> dict:
    text = _data(x_alert_id)["runbook"] or RUNBOOKS["default"]
    return {"alert_type": args.alert_type, "text": text}


@app.post("/tools/create_ticket")
def create_ticket(args: TicketArgs, x_alert_id: str | None = Header(None)) -> dict:
    return {"ticket_id": f"TCK-{x_alert_id or 'adhoc'}", "severity": args.severity}
