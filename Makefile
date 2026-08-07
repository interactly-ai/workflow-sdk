.PHONY: install test lint format typecheck clean sync-check parity-check schema-check refs-check api-docs api-docs-check

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

# ------------------------------------------------------------------ #
# Setup                                                                #
# ------------------------------------------------------------------ #

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install httpx pydantic pydantic-settings typing-extensions anyio websockets
	$(PIP) install pytest pytest-asyncio respx mypy ruff nox pre-commit types-requests
	# Notebook + config dependencies
	$(PIP) install langchain-core nest-asyncio python-dotenv ipykernel nbclient nbformat
	# Editable-install the local SDK and its vendored configs (self-contained; no external paths)
	$(PIP) install -e . -e ./configs

# ------------------------------------------------------------------ #
# Testing                                                              #
# ------------------------------------------------------------------ #

test:
	PYTHONPATH="$(PWD)/src:$(PWD)/configs/src:$$PYTHONPATH" $(VENV)/bin/pytest tests/unit/ -v --tb=short

test-all:
	PYTHONPATH="$(PWD)/src:$(PWD)/configs/src:$$PYTHONPATH" $(VENV)/bin/nox -s tests

# ------------------------------------------------------------------ #
# Code quality                                                         #
# ------------------------------------------------------------------ #

# `configs/` is included deliberately: it is its own ruff settings root, and leaving it unlinted is
# how a stray `ruff check configs/ --fix` silently rewrote the vendored mirror into PEP 604 style and
# took `make parity-check` from 0 differences to 1194. Linting it here keeps its ruleset honest.
lint:
	$(VENV)/bin/ruff check src/ tests/ configs/src configs/tests

format:
	$(VENV)/bin/ruff format src/ tests/ configs/src configs/tests
	$(VENV)/bin/ruff check --fix src/ tests/ configs/src configs/tests

typecheck:
	PYTHONPATH="$(PWD)/src:$(PWD)/configs/src:$$PYTHONPATH" $(VENV)/bin/mypy src/interactly --ignore-missing-imports

# ------------------------------------------------------------------ #
# Sync checks — is the SDK still in step with the workflow service?    #
# ------------------------------------------------------------------ #
# parity-check compares the vendored configs against the interactly-ai
#   SOURCE tree. Needs the monorepo; skips cleanly without it.
# schema-check compares them against a RUNNING server's JSON schemas.
#   Needs INTERACTLY_BASE_URL + INTERACTLY_API_KEY; skips cleanly without.
# They catch different drift — run both. Reports land in docs/_sync/.

PARITY_REPORT ?= docs/_sync/config-parity.md
SCHEMA_REPORT ?= docs/_sync/schema-drift.md

parity-check:
	PYTHONPATH="$(PWD)/src:$(PWD)/configs/src:$$PYTHONPATH" \
		$(PYTHON) tests/tools/config_parity.py -o $(PARITY_REPORT)

schema-check:
	PYTHONPATH="$(PWD)/src:$(PWD)/configs/src:$$PYTHONPATH" \
		$(PYTHON) tests/tools/schema_sync.py -o $(SCHEMA_REPORT)

# Both run even when the first reports drift: these are reports, and stopping at the first
# non-zero exit would hide the other half. `-` tells make to ignore the exit status. The individual
# targets keep their real exit codes, so they still work as gates in CI (plan Phase 6.2).
sync-check:
	-@$(MAKE) parity-check
	-@$(MAKE) schema-check

# refs-check resolves every interactly/interactly_configs symbol used in
#   wf_examples/, notebooks/ and docs/ against the INSTALLED packages. Renaming
#   a class or deleting an enum member breaks those files without touching a
#   single unit test, and this catches it offline in under a second.
#   Run it after every Phase 2 rename or enum deletion.
refs-check:
	PYTHONPATH="$(PWD)/src:$(PWD)/configs/src:$$PYTHONPATH" \
		$(PYTHON) tests/tools/symbol_refs.py --verbose

# api-docs regenerates docs/api_{sync,async}.md from the client classes.
#   The tables are pure introspection, so hand-editing them is how they rot.
#   api-docs-check is the CI gate: it regenerates into a scratch copy and fails
#   if the committed pages differ, i.e. someone added an endpoint and forgot.
api-docs:
	$(PYTHON) wf_examples/internal/gen_api_reference.py

api-docs-check:
	@cp docs/api_async.md /tmp/api_async.before && cp docs/api_sync.md /tmp/api_sync.before
	@$(PYTHON) wf_examples/internal/gen_api_reference.py >/dev/null
	@if ! diff -q /tmp/api_async.before docs/api_async.md >/dev/null || \
	    ! diff -q /tmp/api_sync.before docs/api_sync.md >/dev/null; then \
		echo "docs/api_{sync,async}.md are stale — commit the regenerated files (make api-docs)"; \
		exit 1; \
	fi
	@echo "API reference is up to date."

# ------------------------------------------------------------------ #
# Build                                                                #
# ------------------------------------------------------------------ #

clean:
	rm -rf $(VENV) dist/ build/ *.egg-info .mypy_cache .pytest_cache .ruff_cache Pipfile Pipfile.lock
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
