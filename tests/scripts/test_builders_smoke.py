"""Smoke tests for the illustration scripts under ``interactly-python/scripts/``.

Each test imports a script module and invokes its ``build_*_workflow()``
function.  We assert only that the returned config is a
``WorkflowConfigFullyHydrated`` — no network or LLM calls are made.

This catches:
  * regressions in the porter (import rewrites breaking syntax)
  * removed or renamed symbols on the ``interactly.configs`` facade
  * forward-ref / model_rebuild regressions
"""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
from typing import Callable

import pytest

from interactly.configs import WorkflowConfigFullyHydrated

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _script_modules() -> list[str]:
    return sorted(
        f"scripts.{p.stem}"
        for p in SCRIPTS_DIR.glob("wf_*.py")
        if not p.name.startswith("_")
    )


def _find_build_callable(module) -> Callable[[], object] | None:
    for name in dir(module):
        if name.startswith("build_") and name.endswith("workflow"):
            attr = getattr(module, name)
            if callable(attr):
                return attr
    return None


@pytest.mark.parametrize("module_name", _script_modules())
def test_script_builds_a_hydrated_workflow_config(module_name: str) -> None:
    # Arrange
    module = importlib.import_module(module_name)
    build = _find_build_callable(module)
    assert build is not None, f"{module_name} has no build_*_workflow function"

    # Act — silence the noisy print() statements the originals emit.
    with contextlib.redirect_stdout(io.StringIO()):
        result = build()

    # Assert
    config = result[0] if isinstance(result, tuple) else result
    assert isinstance(config, WorkflowConfigFullyHydrated), (
        f"{module_name}.{build.__name__}() returned {type(config).__name__}"
    )
    assert len(config.node_configs) >= 1
