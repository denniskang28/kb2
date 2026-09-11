SHELL := /bin/sh
PYTHON ?= python3
RUNTIME := $(PYTHON) scripts/local_runtime.py

.PHONY: harness-check local-up local-health local-stop local-clean test-contract test-parser-ocr-normalization test-integration test

harness-check:
	python3 scripts/harness_check.py

local-up:
	$(RUNTIME) up

local-health:
	$(RUNTIME) health

local-stop:
	$(RUNTIME) stop

local-clean:
	$(RUNTIME) clean --confirm "$(CONFIRM)"

test-contract:
	$(PYTHON) -m pytest -m "not integration" tests/contract

test-parser-ocr-normalization:
	$(PYTHON) -m pytest tests/integration/test_parser_ocr_normalization.py

test-integration:
	$(PYTHON) -m pytest -m integration tests/integration

test: test-contract test-parser-ocr-normalization harness-check
