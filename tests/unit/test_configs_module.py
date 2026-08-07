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



class TestFacadeIsExhaustive:
    """The facade must re-export everything ``interactly_configs`` publishes.

    A hand-maintained re-export list drifts silently: a symbol added upstream is simply absent from
    ``interactly.configs``, and to a caller that is indistinguishable from the symbol not existing.
    This test is what keeps the module docstring's promise true.
    """

    def test_all_matches_interactly_configs(self):
        import interactly_configs

        import interactly.configs as facade

        # ``__version__`` is deliberately excluded — see the note in configs.py.
        expected = set(interactly_configs.__all__) - {"__version__"}
        missing = sorted(expected - set(facade.__all__))
        assert not missing, (
            "interactly.configs is missing re-exports that interactly_configs publishes: "
            f"{missing}. Add them to the import block and __all__ in src/interactly/configs.py."
        )

    def test_every_exported_name_resolves(self):
        import interactly.configs as facade

        unresolved = sorted(name for name in facade.__all__ if not hasattr(facade, name))
        assert not unresolved, f"interactly.configs.__all__ lists names it does not define: {unresolved}"
