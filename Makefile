VENV ?= .venv
PY := $(VENV)/bin/python

$(VENV):
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -q -r requirements-dev.txt

COMPOSE ?= docker compose
# Compose Bake needs buildx. The compose plugin alone builds with the docker driver.
export COMPOSE_BAKE ?= false

.PHONY: contracts issues diagrams up down reset
contracts: $(VENV)   ## validate schemas, examples, OpenAPI, agent interface, issues
	$(PY) scripts/validate_contracts.py

issues: $(VENV)      ## regenerate plan/issues.json + docs/plan.md tickets from plan/tickets.yaml
	$(PY) scripts/gen_issues.py

diagrams:            ## render every mermaid block to docs/rendered/<name>.svg + .png (2x)
	bash scripts/render_mermaid.sh

up:                  ## start postgres, api, worker, console, and simulator
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build --wait

down:                ## stop the stack and remove containers and network
	$(COMPOSE) down --remove-orphans

reset:               ## make down, and delete the pgdata volume
	$(COMPOSE) down --remove-orphans --volumes
