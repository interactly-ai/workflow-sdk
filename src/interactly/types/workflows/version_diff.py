"""
Response models for a workflow version diff (``client.workflows.versions.diff``).

These mirror the server's ``VersionDiffResult`` shape: a flat list of node and
edge diffs, each carrying a ``status`` (``added`` / ``removed`` / ``modified``)
and, for modified entries, the field-level ``changes`` that were detected.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._models import BaseAPIModel

__all__ = ["FieldDiff", "NodeDiff", "EdgeDiff", "VersionDiff"]


class FieldDiff(BaseAPIModel):
    """A single field-level change within a node or edge config.

    ``path`` is a dotted path into the config (e.g. ``main_response_config.prompt``).
    """

    path: str
    old_value: Any = None
    new_value: Any = None


class NodeDiff(BaseAPIModel):
    """Change to a single node between two versions."""

    logical_id: str
    name: Optional[str] = None
    node_type: Optional[str] = None
    # Typed as ``str`` (not a ``Literal``) for forward-compat with unknown
    # server values; expected values are "added", "removed", "modified".
    status: str
    # Populated only for ``status == "modified"``; empty for added/removed nodes.
    changes: List[FieldDiff] = []


class EdgeDiff(BaseAPIModel):
    """Change to a single edge between two versions."""

    logical_id: str
    name: Optional[str] = None
    edge_type: Optional[str] = None
    status: str
    changes: List[FieldDiff] = []


class VersionDiff(BaseAPIModel):
    """Structured diff between two workflow versions.

    ``nodes`` / ``edges`` are flat lists of diff entries (each with its own
    ``status``); ``summary`` holds the aggregate counts
    (``nodes_added``/``nodes_removed``/``nodes_modified``/``edges_*``/
    ``workflow_config_changes``).
    """

    version1_number: int
    version1_name: Optional[str] = None
    version2_number: int
    version2_name: Optional[str] = None
    workflow_config_changes: List[FieldDiff] = []
    nodes: List[NodeDiff] = []
    edges: List[EdgeDiff] = []
    summary: Dict[str, int] = {}
