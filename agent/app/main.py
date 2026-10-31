"""HTTP API for the triage agent: POST /triage with an alert, get a run result back."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from agent.app.graph import TriageAgent
from agent.app.schemas import Alert
from agent.app.tools import ToolClient
from agent.config import load_settings
from agent.llm import get_llm
from agent.prompts import load_prompt
from agent.telemetry import setup_telemetry

settings = load_settings()
state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_telemetry()
    state["agent"] = TriageAgent(
        get_llm(settings), load_prompt(), settings.limits, release=settings.release
    )
    state["http"] = httpx.Client(base_url=settings.mock_tools_url, timeout=10.0)
    yield
    state["http"].close()


app = FastAPI(title="triage-agent", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    agent: TriageAgent = state["agent"]
    return {
        "status": "ok",
        "provider": agent.llm.provider,
        "model": agent.llm.model,
        "prompt_version": agent.prompt.version,
    }


@app.post("/triage")
def triage(alert: Alert) -> dict:
    # Sync handler: FastAPI runs it in a worker thread, so a slow LLM call
    # does not block other requests.
    agent: TriageAgent = state["agent"]
    return agent.run(alert, ToolClient(state["http"], alert.alert_id)).to_dict()
