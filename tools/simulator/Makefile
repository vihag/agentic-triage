# Tests for the Splunk simulator. From the repo root, `make contracts` first
# so ../../.venv exists, then:  make -C tools/simulator test
PY ?= python3

.PHONY: test
test:
	PYTHONPATH=src $(PY) -m pytest -q
