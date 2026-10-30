"""Input and output contracts of the triage agent.

The output schema is strict on purpose: the eval gate and the canary analysis
both count "schema invalid" as a failure, so anything loose here hides regressions.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["P1", "P2", "P3", "P4"]
ProbableCause = Literal[
    "oom", "bad_deploy", "db_saturation", "dependency_timeout", "false_alarm", "unknown"
]


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    service: str
    summary: str
    fired_at: str


class TriageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    probable_cause: ProbableCause
    evidence: list[str] = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    ticket_id: str | None
