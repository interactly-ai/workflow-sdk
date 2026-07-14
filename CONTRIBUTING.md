# Contributing

Thank you for your interest in contributing to the Interactly Python SDK.

## Setup

```bash
git clone <repo-url>
cd interactly-python
make install
```

## Running tests

```bash
make test       # unit tests only
make test-all   # full matrix via nox
```

## Code style

The project uses `ruff` for linting and formatting and `mypy --strict` for types.

```bash
make format     # auto-format
make lint       # check only
make typecheck  # static analysis
```

All CI checks must pass before a PR is merged.

## Pull requests

- Keep PRs focused on a single concern.
- Add or update tests for every change.
- Update `CHANGELOG.md` under `[Unreleased]`.
