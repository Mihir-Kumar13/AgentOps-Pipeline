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
  - Phase 1: the LLM wrapper needs a `gemini` provider next to `mock` (and keeps the `LLM_PROVIDER` env var switch). Cost calculation needs Gemini token prices.
  - Phase 4: the Gemini key is stored in AWS Secrets Manager and synced by External Secrets. It is never in Git.
  - Phase 4: the NetworkPolicy and egress allow-list must allow the Gemini API endpoint.
  - Locally the key comes from an env var (for example `GEMINI_API_KEY` in a git-ignored `.env`).

## ADR-003: Branch model is `main` plus one branch per phase
- **Date:** 2026-10-31 (Phase 0)
- **Decision:** The default branch is `main` (renamed from `master`). Each phase is built on its own branch (`phase-0-repo-setup`, `phase-1-...`) and merged through a PR.
- **Why:** This matches CLAUDE.md section 9. Later, CI and branch protection hang off `main`.
- **GitHub repo:** `Mihir-Kumar13/AgentOps-Pipeline`. The Phase 3 OIDC trust policy will be limited to this repo.
