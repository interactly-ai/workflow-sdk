"""Re-export alias for backwards compatibility.

The server uses ``base_defs.py``; the client canonical version is ``base.py``.
All new node configs that import from ``interactly_configs.base_defs`` will
resolve to the same class.
"""

from interactly_configs.base import BaseEntityConfig  # noqa: F401

__all__ = ["BaseEntityConfig"]
