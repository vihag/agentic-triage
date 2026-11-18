VENV ?= .venv
PY := $(VENV)/bin/python

$(VENV): requirements-dev.txt services/api/requirements.txt
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -q -r requirements-dev.txt -r services/api/requirements.txt

COMPOSE ?= docker compose
# Compose Bake needs buildx. The compose plugin alone builds with the docker driver.
export COMPOSE_BAKE ?= false

.PHONY: contracts issues diagrams up down reset python-ci
contracts: $(VENV)   ## validate schemas, examples, OpenAPI, agent interface, issues
	$(PY) scripts/validate_contracts.py

issues: $(VENV)      ## regenerate plan/issues.json + docs/plan.md tickets from plan/tickets.yaml
	$(PY) scripts/gen_issues.py

diagrams:            ## render every mermaid block in docs/ to docs/rendered/*.svg
	bash scripts/render_mermaid.sh

up:                  ## start postgres, api, worker, console, and simulator
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build --wait

down:                ## stop the stack and remove containers and network
	$(COMPOSE) down --remove-orphans

reset:               ## make down, and delete the pgdata volume
	$(COMPOSE) down --remove-orphans --volumes

python-ci: $(VENV)   ## ruff, mypy, and pytest (excludes e2e)
	$(PY) -m ruff check .
	$(PY) -m mypy
	$(PY) -m pytest -m "not e2e"
