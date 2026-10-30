# CLAUDE.md — AgentOps Pipeline (AWS)

> Eval-gated CI/CD + OpenTelemetry observability + canary rollback for an AI agent, on AWS EKS.
> Read this whole file at the start of every session. Work on ONE phase at a time.

---

## 0. How you (Claude) must work in this repo

1. **Check `docs/PROGRESS.md` first.** It says which phase is current. Only work on that phase.
2. **Never jump ahead.** If a task belongs to a later phase, write it in `docs/PROGRESS.md` under "Later" and move on.
3. **Finish a phase with proof.** Every phase has an "Acceptance check". Run it, paste the real output into `docs/PROGRESS.md`, then stop and ask me to review before starting the next phase.
4. **Explain in plain, simple English.** I am a DevOps engineer (~2.5 years, strong on Docker, Linux, CI/CD, GCP; newer to AWS and AI agents). When you use an AWS or AI term for the first time, explain it in one line.
5. **Small steps.** Prefer many small commits over one huge change. Commit message format: `phaseN: short description`.
6. **Ask before anything that costs money or is hard to undo** (terraform apply, creating AWS resources, large LLM runs). Show the plan and the estimated cost first.
7. **Never commit secrets.** No API keys, AWS keys, or tokens in the repo, in logs, or in examples. Use env vars, Secrets Manager, or GitHub OIDC.
8. **Do not invent results.** Numbers in the README (catch rate, cost, latency) must come from real runs saved in `results/`.
9. **If you are unsure, say so and ask.** Do not guess AWS account IDs, regions, or ARNs.
10. **Pin versions** (Terraform providers, Helm charts, Docker base images, Python packages). Write the pinned version in the file, not "latest".

---

## 1. Project goal (one paragraph)

Build a small but real **incident-triage AI agent**, and around it a full **AgentOps pipeline**:
every change to the agent (prompt, model, tool, code) goes through a pull request. The pipeline tests the agent on a fixed set of tasks (the **eval gate**). If quality, cost, or speed gets worse, the PR is blocked. If it passes and is merged, the new version is deployed as a **canary** on EKS. OpenTelemetry watches the live agent, and **Argo Rollouts** rolls back automatically if the canary is worse than stable. At the end I publish a **scorecard** showing how many deliberately bad changes the gates caught.

**What makes this project different from blog posts:** it is a complete, reproducible, AWS-native build with *measured proof* (catch rate, false-block rate, cost per PR), not just a design.

### Non-goals (do NOT build these)
- No RAG pipeline, no vector database, no chat UI.
- No multi-cloud. AWS only.
- No custom LLM training or fine-tuning.
- No big frontend. Grafana is the only UI.

---

## 2. Architecture (high level)

```
 DEVELOPER ── git push / PR ──► GITHUB
                                  │
        ┌─────────────────────────┴──────────────────────────┐
        │ GitHub Actions                                      │
        │  1 lint + unit tests                                │
        │  2 build Docker image ─► Amazon ECR                 │
        │  3 EVAL GATE (run agent on test set, N repeats)     │
        │      quality / cost / latency / tool-errors         │
        │      compare to baseline (stored in S3)             │
        │      post PR comment                                │
        │  4 PASS ─► update image tag in Git (GitOps)         │
        │     FAIL ─► block PR                                │
        │  Auth to AWS: GitHub OIDC ─► IAM role (no keys)     │
        └─────────────────────────┬──────────────────────────┘
                                  ▼
 ┌──────────────────────────── AWS ───────────────────────────┐
 │ Terraform builds all of this                                │
 │                                                             │
 │  VPC ─ public + private subnets                             │
 │  EKS cluster (managed node group, Spot)                     │
 │   ├─ ns: agent                                              │
 │   │    ├─ agent-api (FastAPI + LangGraph)  [Argo Rollout]   │
 │   │    │     stable + canary                                │
 │   │    └─ mock-tools (fake alerts/logs/metrics/tickets)     │
 │   ├─ ns: observability                                      │
 │   │    OTel Collector → Tempo (traces)                      │
 │   │                   → Prometheus (metrics, alerts)        │
 │   │                   → Loki (logs)      → Grafana          │
 │   ├─ ns: argo-rollouts   (canary + analysis + rollback)     │
 │   └─ AWS Load Balancer Controller (ALB, traffic split)      │
 │                                                             │
 │  ECR            container images                            │
 │  S3             Terraform state, eval results, baselines    │
 │  Secrets Manager  LLM API key (via External Secrets)        │
 │  IAM            OIDC role for GitHub, IRSA roles for pods   │
 │  AWS Budgets    cost alarm                                  │
 └──────────────────────────┬─────────────────────────────────┘
                            ▼
              LLM provider (Anthropic API or Amazon Bedrock)
```

### Two loops
- **Loop 1 (before deploy):** PR → eval gate → block or allow.
- **Loop 2 (after deploy):** canary → OTel metrics → Prometheus analysis → promote or auto-rollback.

### Key design rule
**One metric definition, used in three places:** the PR eval gate, the canary analysis, and the Grafana dashboard. Define metric names once in `docs/METRICS.md` and reuse them.

---

## 3. Tech stack (pin versions when you create files)

| Area | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Agent + eval code |
| Agent framework | LangGraph (or Pydantic AI if simpler) | Clear tool loop, easy to trace |
| API | FastAPI + uvicorn | Simple HTTP endpoint for the agent |
| LLM | Provider-agnostic wrapper. Default: Anthropic API. Option: Amazon Bedrock | Switch with env var `LLM_PROVIDER` |
| Eval | Own scorer in Python (pytest) + optional promptfoo | Full control over stats and cost |
| Stats | scipy (Welch's t-test) | LLM output varies run to run |
| Tracing | OpenTelemetry SDK + Collector | Standard GenAI span names |
| Backends | Tempo, Prometheus, Loki, Grafana (self-hosted via Helm) | Cheap, open source |
| IaC | Terraform >= 1.10 | State in S3 with native locking |
| Cluster | Amazon EKS, managed node group, Spot | Cheapest real Kubernetes on AWS |
| Packaging | Helm charts + Kustomize | Standard |
| Progressive delivery | Argo Rollouts + AnalysisTemplates | Canary + auto rollback |
| CI/CD | GitHub Actions + OIDC to AWS | No long-lived keys |
| Registry | Amazon ECR | Image storage |
| Secrets | AWS Secrets Manager + External Secrets Operator | No secrets in Git |
| Pod permissions | IRSA (or EKS Pod Identity) | Least privilege per pod |
| Local dev | Docker Compose, kind (optional) | Build and test without AWS cost |

Region default: `ap-south-1` (Mumbai). Confirm with me before first apply.

---

## 4. Repository structure (create as phases need it)

```
.
├── CLAUDE.md
├── README.md
├── Makefile                      # make eval | make up | make down | make lint ...
├── docs/
│   ├── PROGRESS.md               # current phase, checklists, pasted proof
│   ├── ARCHITECTURE.md
│   ├── METRICS.md                # single source of truth for metric names
│   ├── COSTS.md                  # real costs per session
│   └── DECISIONS.md              # short ADR-style notes
├── agent/
│   ├── app/                      # FastAPI + LangGraph agent
│   ├── prompts/                  # versioned prompt files
│   ├── llm/                      # provider wrapper (anthropic / bedrock / mock)
│   ├── telemetry/                # OTel setup, span helpers, cost calc
│   ├── tests/                    # unit tests
│   └── Dockerfile
├── mock-tools/                   # fake alert/log/metrics/deploy/ticket services
├── evals/
│   ├── dataset/                  # scenarios.jsonl (40-50 tasks)
│   ├── scorers/                  # deterministic checks + optional LLM judge
│   ├── runner.py                 # runs N repeats, writes results JSON
│   ├── compare.py                # baseline vs candidate, Welch's t-test
│   ├── thresholds.yaml           # gate rules
│   └── injected-regressions/     # bad changes used for the scorecard
├── observability/
│   ├── compose/                  # docker-compose stack for local
│   ├── helm-values/              # tempo, prometheus, loki, grafana, otel-collector
│   ├── dashboards/               # Grafana JSON (provisioned)
│   └── alerts/                   # Prometheus rules + promtool tests
├── infra/
│   ├── bootstrap/                # PERSISTENT: state bucket, OIDC provider, ECR, budget
│   └── cluster/                  # EPHEMERAL: VPC, EKS, add-ons (destroy after sessions)
├── deploy/
│   ├── helm/agent/               # chart with Argo Rollout + AnalysisTemplate
│   └── argocd-or-kustomize/      # optional GitOps
├── .github/workflows/
│   ├── pr.yml                    # lint, test, build, eval gate
│   ├── main.yml                  # push image, update tag, deploy
│   └── nightly.yml               # full eval sweep + judge validation
└── results/                      # saved eval runs + scorecard (committed summaries only)
```

**Two Terraform stacks on purpose:** `bootstrap` stays alive (cheap, holds state/ECR/OIDC). `cluster` is destroyed after each work session so I only pay for EKS while I use it.

---

## 5. The agent (what we are building)

**Name:** `triage-agent`
**Job:** receives an alert, investigates with tools, returns a structured triage report.

**Input (JSON):** `{ "alert_id", "service", "summary", "fired_at" }`

**Tools (all served by `mock-tools`, deterministic data):**
| Tool | Returns |
|---|---|
| `get_metrics(service, window)` | CPU, memory, error rate, latency series |
| `get_logs(service, window, query)` | log lines |
| `get_recent_deploys(service)` | list of recent deploys |
| `get_runbook(alert_type)` | runbook text |
| `create_ticket(severity, title, body)` | ticket id (mock) |

**Output (strict JSON schema):**
```json
{
  "severity": "P1|P2|P3|P4",
  "probable_cause": "oom|bad_deploy|db_saturation|dependency_timeout|false_alarm|unknown",
  "evidence": ["short strings that cite tool results"],
  "recommended_action": "string",
  "ticket_id": "string|null"
}
```

**Agent limits (enforced in code):** max 8 tool calls, max 3 replans, 60 s timeout. These limits are also what the "loop detection" alert watches.

**Prompt rules:** prompts live in `agent/prompts/` as files with a version header. The agent reads the version at startup and puts it in every span as `app.agent.prompt_version`.

---

## 6. Eval design

### Dataset (`evals/dataset/scenarios.jsonl`)
- 40–50 scenarios, each with: alert input, which mock data to serve, expected `severity`, expected `probable_cause`, required tools, forbidden tools.
- Categories: OOM, bad deploy, DB saturation, dependency timeout, false alarm (10 each) + ~5 adversarial (prompt injection hidden in a log line, contradictory data, missing data).
- Split: `dev` (used while building prompts) and `holdout` (used only by the gate). Do not tune prompts on `holdout`.

### Scoring (cheap first, judge last)
1. **Deterministic checks (every PR):** valid JSON schema, severity match, cause match, required tools called, forbidden tools NOT called, tool calls <= 8, no loops.
2. **Cost and speed (every PR):** tokens in/out, `cost_usd` per run, wall-clock latency (p50, p95).
3. **LLM-as-judge (nightly only):** rates quality of `evidence`. Validate the judge weekly against ~20 human-labelled examples (Cohen's kappa) so the judge itself is trusted.

### Statistical gate (`evals/compare.py`)
- Run every scenario **N = 3 times** (configurable) for both baseline and candidate.
- Compare quality with **Welch's t-test** (alpha 0.05) and also require an absolute floor.
- Rules live in `evals/thresholds.yaml`, for example:
  - quality: candidate must not drop by more than 3 points vs baseline AND must stay >= 0.85
  - cost per run: <= baseline x 1.20
  - p95 latency: <= baseline x 1.30
  - tool error rate: <= 2%
  - safety (injection scenarios): 100% must pass (absolute, no tolerance)
- Baseline = last successful run on `main`, stored in S3 as `baselines/main.json` (also keep a copy of summary in `results/`).
- Exit code `0` = pass, `1` = fail. PR comment shows a table of baseline vs candidate with deltas.

### Cost control for evals
- PRs run with a **cheap model** and a **mock LLM mode** for pure plumbing tests (no API cost).
- Cache nothing that hides real regressions. Record cost per eval run in `docs/COSTS.md`.
- Hard cap: the runner aborts if a single eval run would exceed a budget set in env `EVAL_MAX_USD`.

---

## 7. Metrics and telemetry contract (`docs/METRICS.md`)

**Span names (OTel GenAI conventions):** `invoke_agent {agent}`, `chat {model}`, `execute_tool {tool}`.

**Standard attributes:** `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.tool.name`, `error.type`.

**Custom attributes (no standard yet, use `app.*`):** `app.agent.cost_usd`, `app.agent.tool_calls`, `app.agent.replans`, `app.agent.prompt_version`, `app.agent.release` (`stable` or `canary`).

**Prometheus metrics (via spanmetrics or direct):**
- `agent_runs_total{release,status}`
- `agent_run_cost_usd` (histogram)
- `agent_run_duration_seconds` (histogram)
- `agent_tool_errors_total{tool}`
- `agent_loops_total` (runs that hit the max tool calls/replans)
- `agent_output_valid_total{valid}` (schema valid or not)

**Alerts (`observability/alerts/`, each with a promtool unit test):**
1. cost per run > 3x 1-hour baseline
2. loop rate > 5%
3. tool error rate > 5%
4. output schema invalid > 2%

---

## 8. PHASES

> Each phase: **Goal → Tasks → Files → Acceptance check → Stop and review.**
> Update `docs/PROGRESS.md` at the end of every phase.

### Phase 0 — Repo setup and ground rules
**Goal:** a clean repo and a working agreement.
**Tasks**
- Create folder skeleton from section 4 (empty placeholders are fine).
- Add `Makefile` with placeholder targets, `.gitignore` (Terraform, Python, secrets), `.editorconfig`, pre-commit (ruff, terraform fmt, yamllint, gitleaks).
- Create `docs/PROGRESS.md` with the phase checklist, and empty `METRICS.md`, `COSTS.md`, `DECISIONS.md`.
- Ask me for: GitHub org/repo name, AWS region, LLM provider choice.
**Acceptance check:** `pre-commit run --all-files` passes; `docs/PROGRESS.md` shows Phase 0 done.

### Phase 1 — Agent + mock tools + eval harness (local, no AWS)
**Goal:** `make eval` prints a score on my laptop.
**Tasks**
- Build `mock-tools` (FastAPI) with deterministic data per scenario.
- Build the LLM wrapper with 3 providers: `anthropic`, `bedrock`, `mock` (mock returns scripted outputs for tests).
- Build `triage-agent` (LangGraph) with the 5 tools, limits, and strict output schema.
- Write the dataset (start with 20 scenarios, grow to 40–50), scorers, and `runner.py`.
- Dockerfile for agent and mock-tools; `docker-compose.yml` to run both.
- Unit tests for scorers and limits.
**Acceptance check**
- `make test` green.
- `make eval` (mock LLM) finishes in under 1 minute and prints per-category scores.
- `make eval LLM_PROVIDER=anthropic N=1` runs on the real model, prints score + cost.
- Save the first real run to `results/phase1-baseline.json`.

### Phase 2 — Observability, local first
**Goal:** every agent run shows up as a trace and as metrics in Grafana, locally.
**Tasks**
- Add OTel SDK to the agent: spans, GenAI attributes, `app.*` attributes, cost calculation.
- Compose stack: OTel Collector, Tempo, Prometheus, Loki, Grafana.
- Collector config: traces → Tempo; spanmetrics → Prometheus; logs → Loki.
- Grafana dashboard JSON (provisioned): runs, success rate, cost/run, p50/p95 latency, tool errors, loops, prompt version, stable vs canary.
- Prometheus alert rules + `promtool test rules`.
- Write `docs/METRICS.md` (the contract in section 7).
**Acceptance check**
- Run 10 scenarios; screenshot a trace showing `invoke_agent → chat → execute_tool`.
- `promtool test rules` passes.
- Dashboard shows data; save screenshots to `docs/img/`.

### Phase 3 — AWS foundation with Terraform
**Goal:** a working EKS cluster that I can create and destroy in one command each.
**Tasks**
- `infra/bootstrap` (applied once): S3 bucket for Terraform state (versioning, encryption, native locking), S3 bucket for eval results, ECR repos (with lifecycle policy), GitHub OIDC provider + IAM role (trust limited to this repo and branches), AWS Budgets alarm, Cost allocation tags.
- `infra/cluster` (ephemeral): VPC (2 AZs, public + private subnets), EKS (managed node group, Spot, 2 small nodes), add-ons (VPC CNI, CoreDNS, kube-proxy, EBS CSI), AWS Load Balancer Controller, External Secrets Operator, IRSA roles.
- Tag every resource: `project=agentops`, `owner=<me>`, `env=dev`.
- `make up` = terraform apply cluster; `make down` = terraform destroy cluster.
- **Cost warning to show me before first apply:** EKS control plane has an hourly fee, and NAT gateways cost hourly + per GB. Use one NAT gateway (or an alternative) and always destroy after sessions. Check current prices in the AWS pricing pages and write the estimate in `docs/COSTS.md`.
**Acceptance check**
- `terraform plan` shown to me and approved before `apply`.
- `kubectl get nodes` shows ready nodes.
- `make down` removes the cluster; bootstrap resources remain.
- Real cost of the session written to `docs/COSTS.md`.

### Phase 4 — Deploy agent and observability stack on EKS
**Goal:** the whole thing runs on EKS and I can see traces in Grafana there.
**Tasks**
- Helm values for Tempo, Prometheus, Loki, Grafana, OTel Collector (small resource requests; this is a demo cluster).
- Helm chart `deploy/helm/agent` for agent-api and mock-tools (Deployment first; Rollout comes in Phase 7).
- External Secrets: pull LLM API key from Secrets Manager into a Kubernetes Secret. No key in Git.
- ALB Ingress for the agent API (restricted by IP or auth) and Grafana (port-forward is fine if safer).
- NetworkPolicies: agent can only talk to mock-tools, the collector, and the LLM endpoint.
- Image pushed manually to ECR for now.
**Acceptance check**
- `curl` the agent endpoint, get a valid triage JSON.
- Grafana on EKS shows the same dashboard with live data.
- `kubectl get pods -A` all healthy; screenshot saved.

### Phase 5 — CI pipeline (build, test, push) with OIDC
**Goal:** a PR builds and tests the agent with zero stored AWS keys.
**Tasks**
- `pr.yml`: checkout → ruff + unit tests → docker build → (on same-repo PRs) assume AWS role via OIDC → push image tagged with commit SHA to ECR.
- Use `permissions: id-token: write` and least privilege on the IAM role (ECR push only, plus S3 access to the eval bucket).
- Cache dependencies; add concurrency cancel for the same PR.
- Trivy image scan (fail on critical).
- Protect `main`: require PR, require status checks.
**Acceptance check**
- A test PR shows green checks; image visible in ECR with the SHA tag.
- Show me the IAM role trust policy proving it is limited to this repo.

### Phase 6 — The eval gate
**Goal:** a bad change is blocked, a good change passes, with numbers in the PR comment.
**Tasks**
- Add `compare.py`, `thresholds.yaml`, baseline storage in S3 (`baselines/main.json`), updated on every successful merge to `main`.
- `pr.yml` adds the eval job: run candidate (N repeats) on the holdout set, compare with baseline, fail on any breached rule.
- PR comment (edit-in-place, not stacked) with a table: metric, baseline, candidate, delta, pass/fail.
- Path-scoped triggers: run the full gate only when `agent/`, `prompts/`, or `evals/` change; run cheap checks otherwise.
- `nightly.yml`: full dataset, judge scoring, judge validation.
- Safety rule: injection scenarios must be 100% pass.
**Acceptance check**
- PR A (harmless refactor) → gate passes.
- PR B (deliberately worse prompt) → gate fails, comment shows why.
- Eval cost per PR written to `docs/COSTS.md`.

### Phase 7 — Progressive delivery: canary + auto rollback
**Goal:** a merged change goes out as a canary and rolls back by itself if it is worse.
**Tasks**
- Install Argo Rollouts. Convert agent Deployment to a `Rollout` with canary steps (for example 10% → 50% → 100%) using the ALB traffic router (fallback: replica-based canary).
- `AnalysisTemplate` using Prometheus provider, comparing canary vs stable on: output-valid rate, tool error rate, loop rate, cost per run, p95 latency.
- `main.yml`: after merge, push image, update the image tag in the chart (commit back or use Argo CD), trigger the rollout.
- A small **traffic generator** (Kubernetes Job or script) that sends scenario traffic so the canary gets data.
- Add `app.agent.release=canary|stable` label to all telemetry so dashboards and analysis can split them.
**Acceptance check**
- Good change → canary promotes to 100%.
- Bad change that the offline gate missed (use an injected one) → canary aborts and rollback happens without me touching anything. Save `kubectl argo rollouts get rollout` output and Grafana screenshot.

### Phase 8 — Scorecard and hardening (the proof)
**Goal:** real numbers that prove the pipeline works.
**Tasks**
- Create `evals/injected-regressions/` with 10 changes, each as a patch or branch:
  1. vague prompt (quality drop)
  2. swap to a weaker model
  3. tool schema change (breaks a tool call)
  4. prompt that causes loops (replans)
  5. verbose prompt (cost spike)
  6. slow tool (latency spike)
  7. prompt injection from a log line
  8. removed safety instruction
  9. **control:** harmless whitespace/refactor (must PASS)
  10. **control:** genuinely better prompt (must PASS)
- Script `make scorecard` runs all 10 through the gate (and canary for ones the gate misses) and writes `results/scorecard.md` and JSON.
- Report: **catch rate**, **false-block rate**, **where caught (PR gate vs canary)**, **time to rollback**, **cost per PR gate**.
- Security pass: least-privilege IAM review, image scan, secrets scan, NetworkPolicy check.
- Document known limits honestly (what the gate cannot see, small dataset size, LLM variance).
**Acceptance check:** `results/scorecard.md` exists with real numbers and links to the runs that produced them.

### Phase 9 — Documentation and portfolio
**Goal:** someone can understand, run, and trust this project in 10 minutes.
**Tasks**
- `README.md`: one-paragraph pitch, architecture diagram, 2-minute quickstart (`make up`, `make eval`, `make down`), scorecard table, cost table, "what this is not", limitations.
- `docs/ARCHITECTURE.md` with the diagram and a data-flow explanation of both loops.
- 3–5 minute demo video script: bad PR blocked → good PR merged → canary rollback → Grafana.
- Resume bullets (fill with REAL numbers from the scorecard):
  - "Built an eval-gated CI/CD and canary pipeline for an AI agent on AWS EKS (Terraform, GitHub Actions OIDC, Argo Rollouts, OpenTelemetry/Grafana)."
  - "Gates caught X of Y injected regressions with Z false blocks; automatic canary rollback in N seconds; eval gate costs about $C per PR."
- Optional: write a blog post about the scorecard.
**Acceptance check:** a fresh clone can follow the README to reach a working `make eval` without asking me anything.

---

## 9. Conventions and guardrails

**Code:** type hints, ruff formatting, small functions, docstrings that explain "why". Tests for every scorer and for compare.py (including edge cases).
**Terraform:** one module per concern, variables with descriptions, no hardcoded account IDs, `terraform fmt` and `tflint` in pre-commit, plan output reviewed before apply.
**Kubernetes:** resource requests/limits on everything, readiness and liveness probes, non-root containers, read-only root filesystem where possible, NetworkPolicies on.
**Security:** least privilege IAM, OIDC trust limited to repo/branch, no wildcard `*` resources unless justified in `docs/DECISIONS.md`, encrypted S3 and ECR, secrets only in Secrets Manager, treat tool output as untrusted (prompt-injection tests included).
**Cost:** tag everything, budget alarm on, destroy cluster after each session, record real costs in `docs/COSTS.md`.
**Git:** branch per phase (`phase-3-aws-foundation`), PRs into `main`, never push directly to `main`.

---

## 10. Definition of done (whole project)

- [ ] `make eval` works locally without AWS.
- [ ] Traces and dashboards work locally and on EKS.
- [ ] `make up` / `make down` create and destroy the EKS stack cleanly.
- [ ] A bad PR is blocked with a clear comment; a good PR passes.
- [ ] A bad canary is rolled back automatically.
- [ ] `results/scorecard.md` has real catch-rate and false-block numbers.
- [ ] README lets a stranger reproduce it.
- [ ] No secrets in Git history (gitleaks clean).

---

## 11. Session prompts (copy-paste to start work)

**Start a phase**
> Read CLAUDE.md and docs/PROGRESS.md. We are on Phase N. List the tasks you will do, the files you will create, and anything you need from me. Do not start until I say go.

**Continue a phase**
> Read docs/PROGRESS.md and continue Phase N from where we stopped. Keep steps small and explain new AWS or AI terms in one line.

**Before any AWS apply**
> Show me the terraform plan summary, the resources that cost money, and the estimated cost per hour. Wait for my approval.

**Close a phase**
> Run the Phase N acceptance check, paste the real output into docs/PROGRESS.md, list what is left or risky, then stop for my review.

**When something fails**
> Explain the error in simple English, show the likely cause, propose the smallest fix, and wait before changing infrastructure.