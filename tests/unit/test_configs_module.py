"""
Unit tests for the interactly.configs re-export module (Phase A, Phase D).

These tests verify:
- `interactly.configs` raises ImportError with a helpful message when
  interactly_configs is not installed.
- The module re-exports all expected public symbols when interactly_configs IS
  available (mocked via sys.modules).
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Generator
from unittest.mock import MagicMock

import pytest

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_mock_interactly_configs() -> MagicMock:
    """
    Build a mock interactly_configs module.

    We use MagicMock (not types.ModuleType) so that ANY attribute access —
    including ones we didn't explicitly set — returns a MagicMock rather than
    raising AttributeError.  configs.py imports ~50 symbols from interactly_configs;
    this avoids having to enumerate them all.
    """
    mock_mod = MagicMock(name="interactly_configs")
    mock_mod.__name__ = "interactly_configs"
    mock_mod.__spec__ = None
    return mock_mod


@contextmanager
def _reload_configs_with_mock(mock_configs_mod: MagicMock | None) -> Generator:
    """
    Context manager that:
    1. Temporarily installs (or removes) a mock ``interactly_configs`` in sys.modules.
    2. Reloads ``interactly.configs`` so the module-level import re-runs.
    3. Restores original sys.modules state on exit.
    """
    real_interactly_configs = sys.modules.get("interactly_configs")
    real_interactly_configs_mod = sys.modules.get("interactly.configs")

    try:
        # Install (or remove) the mock
        if mock_configs_mod is None:
            sys.modules.pop("interactly_configs", None)
        else:
            sys.modules["interactly_configs"] = mock_configs_mod

        # Force configs.py to re-run by removing the cached module
        sys.modules.pop("interactly.configs", None)

        yield
    finally:
        # Restore original state
        if real_interactly_configs is None:
            sys.modules.pop("interactly_configs", None)
        else:
            sys.modules["interactly_configs"] = real_interactly_configs

        if real_interactly_configs_mod is None:
            sys.modules.pop("interactly.configs", None)
        else:
            sys.modules["interactly.configs"] = real_interactly_configs_mod


# --------------------------------------------------------------------------- #
# Tests: configs absent                                                         #
# --------------------------------------------------------------------------- #





# --------------------------------------------------------------------------- #
# Tests: configs installed (mocked)                                            #
# --------------------------------------------------------------------------- #


_EXPECTED_SYMBOLS = [
    "WorkflowConfig",
    "BaseNodeConfig",
    "EdgeConfig",
    "DirectEdgeConfig",
    "ConditionalEdgeConfig",
    "ToolConfig",
    "BaseRunInput",
    "BaseRunOutput",
    "WorkflowConfigFullyHydrated",
    "LLMGroupConfig",
    "PromptConfig",
    "MCPServerConfig",
]


class TestConfigsModuleWhenInstalled:
    """When interactly_configs IS available, configs.py re-exports all expected symbols."""

    @pytest.mark.parametrize("symbol", _EXPECTED_SYMBOLS)
    def test_symbol_is_re_exported(self, symbol: str):
        mock_mod = _make_mock_interactly_configs()
        with _reload_configs_with_mock(mock_mod):
            import interactly.configs as cfg_module  # noqa: F401
            assert hasattr(cfg_module, symbol), (
                f"interactly.configs should re-export {symbol!r} when interactly_configs is installed"
            )

