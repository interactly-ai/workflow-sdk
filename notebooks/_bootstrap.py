"""sys.path bootstrap for the docs notebooks.

Notebooks live in ``notebooks/``. Their first cell runs ``import _bootstrap`` so
the short, library-style import names resolve **without installing the package**::

    import _bootstrap  # noqa: F401
    import interactly
    import interactly_configs
    from interactly import WorkflowClient, WorkflowRuntime

This adds this SDK's ``src`` and ``configs/src`` directories to ``sys.path`` so
``interactly`` and ``interactly_configs`` import like any installed library.
Everything it adds lives **inside this SDK folder** — the SDK is fully
self-contained and depends on nothing outside it.

The preferred experience is a real editable install (no bootstrap needed)::

    pip install -e . -e ./configs
"""

import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_sdk_root = os.path.abspath(os.path.join(_this_dir, ".."))

# Both live inside this SDK folder: ``src`` exposes ``interactly``,
# ``configs/src`` exposes ``interactly_configs``.
_paths = [
    os.path.join(_sdk_root, "src"),
    os.path.join(_sdk_root, "configs", "src"),
]

for _p in _paths:
    if _p not in sys.path:
        sys.path.insert(0, _p)
