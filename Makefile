.PHONY: install test lint format typecheck clean

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

lint:
	$(VENV)/bin/ruff check src/ tests/

format:
	$(VENV)/bin/ruff format src/ tests/
	$(VENV)/bin/ruff check --fix src/ tests/

typecheck:
	PYTHONPATH="$(PWD)/src:$(PWD)/configs/src:$$PYTHONPATH" $(VENV)/bin/mypy src/interactly --ignore-missing-imports

# ------------------------------------------------------------------ #
# Build                                                                #
# ------------------------------------------------------------------ #

clean:
	rm -rf $(VENV) dist/ build/ *.egg-info .mypy_cache .pytest_cache .ruff_cache Pipfile Pipfile.lock
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
