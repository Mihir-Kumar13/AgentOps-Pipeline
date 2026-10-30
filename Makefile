# AgentOps Pipeline — task runner.
# Targets marked "Phase N" are placeholders until that phase is built.

.DEFAULT_GOAL := help
.PHONY: help install lint test eval dataset compose-up compose-down up down scorecard

LLM_PROVIDER ?= mock
N ?= 3
SPLIT ?= all
OUT ?=

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

up: ## Create the EKS cluster with Terraform (Phase 3)
	@echo "make up: not implemented yet (Phase 3)"

down: ## Destroy the EKS cluster (Phase 3)
	@echo "make down: not implemented yet (Phase 3)"

scorecard: ## Run injected regressions and write results/scorecard.md (Phase 8)
	@echo "make scorecard: not implemented yet (Phase 8)"
