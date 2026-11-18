VENV ?= .venv
PY := $(VENV)/bin/python

$(VENV):
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -q -r requirements-dev.txt

.PHONY: contracts issues diagrams
contracts: $(VENV)   ## validate schemas, examples, OpenAPI, agent interface, issues
	$(PY) scripts/validate_contracts.py

issues: $(VENV)      ## regenerate plan/issues.json + docs/plan.md tickets from plan/tickets.yaml
	$(PY) scripts/gen_issues.py

diagrams:            ## render every mermaid block to docs/rendered/<name>.svg + .png (2x)
	bash scripts/render_mermaid.sh
