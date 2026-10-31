# Decisions (short ADRs)

Each entry: what we decided, why, and what it affects. Newest last.

---

## ADR-001: AWS region is `ap-south-1` (Mumbai)
- **Date:** 2026-10-31 (Phase 0)
- **Decision:** All AWS resources go in `ap-south-1`.
- **Why:** Low latency from India. It is also the CLAUDE.md default.
- **Affects:** Terraform provider config (Phase 3), ECR and S3 locations, and pricing lookups in `docs/COSTS.md`.

## ADR-002: Default LLM provider is the Gemini API (API key), for now
- **Date:** 2026-10-31 (Phase 0)
- **Decision:** The agent will call Google's Gemini API by default, using an API key.
- **Why:** The owner chose it for now.
- **Difference from CLAUDE.md:** CLAUDE.md lists Anthropic API (default) or Amazon Bedrock. CLAUDE.md has not been changed yet.
- **Affects:**
  - Phase 1: done. The `gemini` provider is in `agent/llm/gemini.py`, and prices are in `agent/llm/pricing.py` (see ADR-005).
  - Phase 4: the Gemini key is stored in AWS Secrets Manager and synced by External Secrets. It is never in Git.
  - Phase 4: the NetworkPolicy and egress allow-list must allow the Gemini API endpoint.
  - Locally the key comes from an env var (for example `GEMINI_API_KEY` in a git-ignored `.env`).

## ADR-003: Branch model is `main` plus one branch per phase
- **Date:** 2026-10-31 (Phase 0)
- **Decision:** The default branch is `main` (renamed from `master`). Each phase is built on its own branch (`phase-0-repo-setup`, `phase-1-...`) and merged through a PR.
- **Why:** This matches CLAUDE.md section 9. Later, CI and branch protection hang off `main`.
- **GitHub repo:** `Mihir-Kumar13/AgentOps-Pipeline`. The Phase 3 OIDC trust policy will be limited to this repo.

## ADR-004: Python deps managed with uv; code runs from the repo root
- **Date:** 2026-10-31 (Phase 1)
- **Decision:** `pyproject.toml` pins direct dependencies with `==`, and `uv.lock` pins the full tree. The project is not an installable package (`[tool.uv] package = false`). Code runs as `python -m ...` from the repo root.
- **Dependency groups:** shared (fastapi, httpx, pydantic, pyyaml, uvicorn), `agent` (google-genai, langgraph, python-dotenv), `dev` (pytest). The mock-tools image installs only the shared deps.
- **Why:** One lock file for reproducible builds. It is fast, and `uv` was already on the machine.

## ADR-005: Phase 1 implements `gemini` and `mock` providers only
- **Date:** 2026-10-31 (Phase 1)
- **Decision:** `LLM_PROVIDER` supports `mock` (default, free) and `gemini`. The default Gemini model is `gemini-3.1-flash-lite`, which is cheap and current ($0.25 / $1.50 per 1M tokens in / out at paid-tier prices, checked 2026-10-31). Change it with `LLM_MODEL`.
- **Not built:** `anthropic` and `bedrock` (named in CLAUDE.md). They can't be tested without credentials, so they wait until they are needed.
- **mock provider:** a keyword and threshold rule engine. It never sees the expected answers. It tests plumbing only, and its score says nothing about LLM quality.
- **Free tier:** the owner's key is free tier (15 requests/min for this model). Set `LLM_MAX_RPM=12` to pace calls. Pacing adds wait time to measured latency, so free-tier latency numbers must not be used as gate baselines.

## ADR-006: Agent limits and the meaning of "replan"
- **Date:** 2026-10-31 (Phase 1)
- **Decision:** These limits are enforced in code (`agent/app/graph.py`): 8 tool calls, 3 replans, 60 s.
- **Replan:** any turn the model must redo. That means an invalid final JSON, an empty reply, an unknown tool name, or a **duplicate call** (same tool and same arguments). A duplicate is how a loop shows up, so it is not executed again.
- **Statuses:** `ok`, `invalid_output`, `tool_limit`, `replan_limit`, `timeout`, `error`. `tool_limit` and `replan_limit` feed `agent_loops_total` in Phase 2.
- **Known gap:** the timeout is checked between steps. One slow LLM call (30 s HTTP timeout, up to 4 retries) can overrun it.

## ADR-007: mock-tools data is keyed by alert id; evals run mock-tools in-process
- **Date:** 2026-10-31 (Phase 1)
- **Decision:** Each scenario's `mock_data` is served for its `alert_id`. The agent sends the alert id in an `X-Alert-Id` header, not as a tool argument, so the LLM never sees or controls which data it gets.
- **Evals:** `evals/runner.py` mounts the mock-tools FastAPI app in-process (no server, no network). Setting `MOCK_TOOLS_URL` makes it use a running server instead (for example the compose stack).
- **Why:** `make eval` is fast and self-contained, and the same app code serves both modes.

## ADR-008: Add an `openai` provider; default model `gpt-5-nano`
- **Date:** 2026-10-31 (Phase 1)
- **Decision:** `LLM_PROVIDER=openai` uses the OpenAI Chat Completions API (`openai==3.42.0`, `agent/llm/openai_provider.py`). The key comes from `OPENAI_API_KEY`. The default model is `gpt-5-nano` ($0.05 / $0.40 per 1M tokens in / out, checked 2026-10-31).
- **Why:** Gemini's free tier kept returning `503 "high demand"`, so a complete 20-scenario result was impossible. A cheap paid model gives a complete, repeatable baseline for about $0.01–0.02 per 20 scenarios.
- **Details:** the SDK retries 429/5xx (4 retries). Reasoning tokens are billed as output and are already inside `completion_tokens`. Cached-input discounts are ignored, so recorded costs are slightly high. The free-tier pacing (`LLM_MAX_RPM`) moved to the shared `agent/llm/pacing.py`.
- **Rule:** one model per result. Answers from Gemini and OpenAI are never merged into one baseline.
- **Affects later phases:** in Phase 4 the key moves to Secrets Manager, and NetworkPolicy egress must allow `api.openai.com`. CLAUDE.md still names Anthropic/Bedrock.
