SHELL := /bin/sh

.PHONY: harness-check

harness-check:
	python3 scripts/harness_check.py
