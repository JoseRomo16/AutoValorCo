# AutoValor CO - developer entrypoints.
# On Windows without GNU make, use the equivalent script: .\make.ps1 <target>

UV ?= uv
RUN := $(UV) run
HOST ?= 127.0.0.1
PORT ?= 8000
PAGES ?= 10

.DEFAULT_GOAL := help
.PHONY: help setup scrape enrich pull-history push-history transform train serve test \
	lint format docker-build docker-up clean

help: ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install Python, browser and frontend dependencies
	$(UV) sync
	$(RUN) playwright install chromium
	$(RUN) pre-commit install
	@if [ -d frontend ]; then \
		cd frontend && npm install; \
	else \
		echo "frontend/ not created yet (F4), skipping npm install"; \
	fi

scrape: ## Capture listings into data/bronze
	$(RUN) python -m autovalor.ingest.cli --vehicle-type all --pages $(PAGES)

enrich: ## Read the detail page of motorcycles without one (BUDGET=N, ~35 min for 500)
	$(RUN) python -m autovalor.ingest.detail_cli $(if $(BUDGET),--budget $(BUDGET),)

pull-history: ## Bring the published captures from the data branch into data/bronze
	$(RUN) python -m autovalor.ingest.history pull

push-history: ## Publish the local captures in data/bronze to the data branch
	$(RUN) python -m autovalor.ingest.history push

transform: ## Run dbt (silver and gold) and the Pandera validations
	$(RUN) python -m autovalor.quality.cli --stage bronze
	$(RUN) dbt build --project-dir dbt --profiles-dir dbt
	$(RUN) python -m autovalor.quality.cli --stage silver --stage gold

train: ## Train the models and log them to MLflow (TRIALS=N to set the Optuna budget)
	$(RUN) python -m autovalor.models.train $(if $(TRIALS),--trials $(TRIALS),)

serve: ## Run the API locally with autoreload
	$(RUN) uvicorn autovalor.api.main:app --reload --host $(HOST) --port $(PORT)

test: ## Run the test suite with coverage
	$(RUN) pytest

lint: ## Run ruff (lint + format check) and mypy
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy

format: ## Apply ruff formatting and autofixes
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

docker-build: ## Build the API image
	docker compose build

docker-up: ## Start the API with docker compose
	docker compose up -d api

clean: ## Remove caches and coverage artifacts
	rm -rf .ruff_cache .mypy_cache .pytest_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
