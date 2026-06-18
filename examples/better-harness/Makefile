.PHONY: demo-validate demo-eval demo-run demo-inspect demo-clean help

DEMO_CONFIG  := demo/experiment.toml
DEMO_OUTPUT  := runs/task-assistant-demo
DEMO_EVALS   := demo/evals
DEMO_WORKSPACE := demo/workspace
MAX_ITERATIONS := 4

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Demo: Smart Task Assistant
# ---------------------------------------------------------------------------

demo-validate: ## Validate the demo experiment config
	uv run better-harness validate $(DEMO_CONFIG)

demo-eval: ## Run evals directly to verify baseline (all should fail)
	cd $(DEMO_EVALS) && uv sync --group test && PYTHONPATH=../workspace uv run --project . pytest tests/ -v

demo-run: ## Run the full optimization loop
	uv run better-harness run $(DEMO_CONFIG) \
		--output-dir $(DEMO_OUTPUT) \
		--max-iterations $(MAX_ITERATIONS)

demo-inspect: ## Inspect the latest run results
	uv run better-harness inspect $(DEMO_OUTPUT)

demo-clean: ## Remove demo run artifacts
	rm -rf $(DEMO_OUTPUT)

# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

install: ## Install project dependencies
	uv sync --extra dev

test: ## Run better-harness unit tests
	uv run pytest

lint: ## Run linter
	uv run ruff check .

lint-fix: ## Run linter with auto-fix
	uv run ruff check --fix .
