# AgentOps Pipeline — task runner.
# Targets marked "Phase N" are placeholders until that phase is built.

.DEFAULT_GOAL := help
.PHONY: help install lint test eval dataset compose-up compose-down obs-up obs-down alerts-test up down scorecard

LLM_PROVIDER ?= mock
N ?= 3
SPLIT ?= all
OUT ?=
OBS_COMPOSE = docker compose -f docker-compose.yml -f observability/compose/docker-compose.yml
PROMETHEUS_IMAGE = prom/prometheus:v3.15.1

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-13s %s\n", $$1, $$2}'

install: ## Create .venv with pinned dependencies (needs uv)
	uv sync --frozen

lint: ## Run all pre-commit hooks on every file
	pre-commit run --all-files

test: ## Run unit tests
	uv run pytest

eval: ## Run evals: make eval [LLM_PROVIDER=gemini] [N=1] [SPLIT=dev] [OUT=results/x.json]
	LLM_PROVIDER=$(LLM_PROVIDER) uv run python -m evals.runner --n $(N) --split $(SPLIT) $(if $(OUT),--out $(OUT))

dataset: ## Rebuild evals/dataset/scenarios.jsonl from the builder
	uv run python -m evals.dataset.build_scenarios

compose-up: ## Build and run agent + mock-tools locally (http://localhost:8080)
	docker compose up --build -d --wait

compose-down: ## Stop the local stack
	docker compose down

obs-up: ## Run agent + mock-tools + OTel Collector, Tempo, Prometheus, Loki, Grafana (localhost:3000)
	$(OBS_COMPOSE) up --build -d --wait

obs-down: ## Stop the local observability stack (trace/metric data is discarded)
	$(OBS_COMPOSE) down

alerts-test: ## Validate alert rules and run their promtool unit tests (via the Prometheus image)
	docker run --rm -v "$(CURDIR)/observability/alerts:/alerts:ro" --entrypoint promtool $(PROMETHEUS_IMAGE) check rules /alerts/agent-rules.yml
	docker run --rm -v "$(CURDIR)/observability/alerts:/alerts:ro" -w /alerts/tests --entrypoint promtool $(PROMETHEUS_IMAGE) test rules agent-rules.test.yml

up: ## Create the EKS cluster with Terraform (Phase 3)
	@echo "make up: not implemented yet (Phase 3)"

down: ## Destroy the EKS cluster (Phase 3)
	@echo "make down: not implemented yet (Phase 3)"

scorecard: ## Run injected regressions and write results/scorecard.md (Phase 8)
	@echo "make scorecard: not implemented yet (Phase 8)"
