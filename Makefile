# AgentOps Pipeline — task runner.
# Targets marked "Phase N" are placeholders until that phase is built.

.DEFAULT_GOAL := help
.PHONY: help lint test eval up down scorecard

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

lint: ## Run all pre-commit hooks on every file
	pre-commit run --all-files

test: ## Run unit tests (Phase 1)
	@echo "make test: not implemented yet (Phase 1)"

eval: ## Run the eval harness (Phase 1)
	@echo "make eval: not implemented yet (Phase 1)"

up: ## Create the EKS cluster with Terraform (Phase 3)
	@echo "make up: not implemented yet (Phase 3)"

down: ## Destroy the EKS cluster (Phase 3)
	@echo "make down: not implemented yet (Phase 3)"

scorecard: ## Run injected regressions and write results/scorecard.md (Phase 8)
	@echo "make scorecard: not implemented yet (Phase 8)"
