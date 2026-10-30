"""Deterministic checks for one agent run (CLAUDE.md section 6, step 1).

Each check is True/False. `quality` is the fraction passed (0..1); `passed` means
every check passed. The checks are cheap, so they run on every PR.
"""

import json

from pydantic import ValidationError

from agent.app.schemas import TriageReport
from agent.config import Limits

DEFAULT_LIMITS = Limits()


def score_run(run: dict, expected: dict, limits: Limits = DEFAULT_LIMITS) -> dict:
    """Score a RunResult dict against a scenario's `expected` block."""
    report = run.get("report")
    called = [c["name"] for c in run.get("tool_calls", []) if not c.get("error")]
    keys = [(c["name"], json.dumps(c["args"], sort_keys=True)) for c in run.get("tool_calls", [])]

    checks = {
        "schema_valid": _schema_valid(report),
        "severity_match": bool(report) and report.get("severity") == expected["severity"],
        "cause_match": bool(report) and report.get("probable_cause") == expected["probable_cause"],
        "required_tools": all(t in called for t in expected["required_tools"]),
        "forbidden_tools": not any(t in called for t in expected["forbidden_tools"]),
        "tool_budget": len(keys) <= limits.max_tool_calls,
        "no_loops": len(keys) == len(set(keys)) and run.get("status") != "replan_limit",
        "ticket_consistent": _ticket_consistent(run, report),
    }
    passed = sum(checks.values())
    return {"checks": checks, "quality": passed / len(checks), "passed": passed == len(checks)}


def _schema_valid(report: dict | None) -> bool:
    if report is None:
        return False
    try:
        TriageReport.model_validate(report)
    except ValidationError:
        return False
    return True


def _ticket_consistent(run: dict, report: dict | None) -> bool:
    """ticket_id must be the id create_ticket returned, or null if no ticket was made.

    mock-tools always returns TCK-<alert_id>, so the expected id is known.
    """
    if not report:
        return False
    calls = run.get("tool_calls", [])
    made = any(c["name"] == "create_ticket" and not c.get("error") for c in calls)
    if not made:
        return report.get("ticket_id") is None
    return report.get("ticket_id") == f"TCK-{run['alert_id']}"
