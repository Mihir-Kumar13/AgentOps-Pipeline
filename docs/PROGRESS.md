# Progress

**Current phase:** Phase 0 — done, waiting for owner review
**Branch:** `phase-0-repo-setup` (not pushed yet)
**Next phase:** Phase 1 (starts only after review)

## Key settings (see docs/DECISIONS.md)
| Setting | Value |
|---|---|
| GitHub repo | `Mihir-Kumar13/AgentOps-Pipeline` |
| AWS region | `ap-south-1` |
| LLM provider (default) | Gemini API, API key (ADR-002) |
| Default branch | `main`, one branch per phase |

## Phase checklist
- [x] Phase 0: Repo setup and ground rules (pending review)
- [ ] Phase 1: Agent + mock tools + eval harness (local, no AWS)
- [ ] Phase 2: Observability, local first
- [ ] Phase 3: AWS foundation with Terraform
- [ ] Phase 4: Deploy agent and observability stack on EKS
- [ ] Phase 5: CI pipeline (build, test, push) with OIDC
- [ ] Phase 6: The eval gate
- [ ] Phase 7: Progressive delivery: canary + auto rollback
- [ ] Phase 8: Scorecard and hardening
- [ ] Phase 9: Documentation and portfolio

---

## Phase 0: Repo setup and ground rules

### Tasks
- [x] Folder skeleton from CLAUDE.md section 4 (`.gitkeep` placeholders)
- [x] `Makefile` with placeholder targets (`help lint test eval up down scorecard`)
- [x] `.gitignore` (Python, Terraform, secrets), `.editorconfig`
- [x] pre-commit: ruff, terraform fmt, yamllint, gitleaks, plus basic hygiene hooks (all revs pinned)
- [x] `docs/PROGRESS.md`, plus stubs for `METRICS.md`, `COSTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`
- [x] Asked owner for GitHub repo, AWS region, and LLM provider (recorded in DECISIONS.md)

### Local tools installed in this phase
- `pre-commit 4.3.0` (via `uv tool install`)
- `gitleaks 8.28.0` (release binary, sha256 verified, in `~/.local/bin`)
- Git hook installed with `pre-commit install`

### Acceptance check (real output, 2026-10-31)
Terminal color codes were removed from the gitleaks lines. Nothing else was changed.

```
$ pre-commit run --all-files
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
check for merge conflicts................................................Passed
check for added large files..............................................Passed
detect private key.......................................................Passed
ruff check...........................................(no files to check)Skipped
ruff format..........................................(no files to check)Skipped
Terraform fmt........................................(no files to check)Skipped
yamllint.................................................................Passed
Detect hardcoded secrets.................................................Passed
exit code: 0

$ gitleaks git --redact
1:59AM INF 5 commits scanned.
1:59AM INF scanned ~39350 bytes (39.35 KB) in 351ms
1:59AM INF no leaks found
exit code: 0

$ make help
  help       Show available targets
  lint       Run all pre-commit hooks on every file
  test       Run unit tests (Phase 1)
  eval       Run the eval harness (Phase 1)
  up         Create the EKS cluster with Terraform (Phase 3)
  down       Destroy the EKS cluster (Phase 3)
  scorecard  Run injected regressions and write results/scorecard.md (Phase 8)
exit code: 0
```

ruff and terraform fmt show "Skipped" because there are no `.py` or `.tf` files yet. They start checking in Phase 1 and Phase 3.

### Left / risky
- Branch is not pushed to GitHub and no PR exists yet. This needs owner approval.
- `awscli` is not installed. It is needed from Phase 3.
- `tflint` (named in CLAUDE.md section 9) is not in pre-commit yet. Add it in Phase 3 when the first `.tf` files exist.
- CLAUDE.md still says Anthropic/Bedrock. It does not match ADR-002 (Gemini).

---

## Later (parked tasks that belong to future phases)
- **Phase 1:** add a `gemini` provider to the LLM wrapper (`LLM_PROVIDER=gemini`), read the key from the `GEMINI_API_KEY` env var, and add Gemini token prices for cost calculation.
- **Phase 3:** add `tflint` to pre-commit, install `awscli` v2, and limit OIDC trust to `Mihir-Kumar13/AgentOps-Pipeline`.
- **Phase 4:** put the Gemini key in Secrets Manager, and let the NetworkPolicy egress reach the Gemini API endpoint.
- **Phase 5:** run `make lint` (pre-commit) in CI.
