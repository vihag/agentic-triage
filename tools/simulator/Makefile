# Tests for the Splunk simulator. From the repo root, `make contracts` first
# so ../../.venv exists, then:  make -C tools/simulator test
REPO_ROOT := $(abspath ../..)
ENV_FILE := $(REPO_ROOT)/.env
SIMULATOR := $(abspath ./simulator)
PY ?= $(if $(wildcard $(REPO_ROOT)/.venv/bin/python),$(REPO_ROOT)/.venv/bin/python,python3)
ARGS ?=

.PHONY: test send
test:
	PYTHONPATH=src $(PY) -m pytest -q

send:
	@test -f $(ENV_FILE) || (echo "missing $(ENV_FILE); run 'make up' from the repo root first" >&2; exit 1)
	@test -n "$(ARGS)" || (echo "usage: make -C tools/simulator send ARGS=<scenario>" >&2; exit 1)
	@set -a && . $(ENV_FILE) && set +a && \
	  $(SIMULATOR) send $(ARGS) --base-url "$${TRIAGE_API_URL:-http://localhost:8080}" --token "$$SPLUNK_WEBHOOK_TOKEN"
