"""
noxfile.py — multi-Python test matrix and code quality sessions.

Run all sessions:     nox
Run a specific one:   nox -s tests-3.11
Run linting only:     nox -s lint
"""

import nox

PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    """Run the unit test suite."""
    session.install("-e", ".[dev]")
    session.run("pytest", "tests/unit/", "-v", "--tb=short")


@nox.session
def lint(session: nox.Session) -> None:
    """Run ruff linter and formatter check."""
    session.install("ruff")
    session.run("ruff", "check", "src/")
    session.run("ruff", "format", "--check", "src/")


@nox.session
def typecheck(session: nox.Session) -> None:
    """Run mypy static type checking."""
    session.install("-e", ".[dev]")
    session.run("mypy", "src/interactly", "--ignore-missing-imports")


@nox.session
def format(session: nox.Session) -> None:
    """Auto-format source code with ruff."""
    session.install("ruff")
    session.run("ruff", "format", "src/", "tests/")
    session.run("ruff", "check", "--fix", "src/", "tests/")
