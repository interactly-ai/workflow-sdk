"""Where a workflow, tool or LLM configuration is used: the answer of the ``/usage`` routes."""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from interactly._models import BaseAPIModel

__all__ = ["UsageEntry", "UsageReport"]


class UsageEntry(BaseAPIModel):
    """One workflow that references the item, and the versions of it that do."""

    workflow_id: str
    name: Optional[str] = None
    #: Every version that references the item, the active one or not: a version pinned by a schedule, a
    #: simulation or an assistant still runs.
    version_numbers: List[int] = Field(default_factory=list)


class UsageReport(BaseAPIModel):
    """The team's workflows that reference an item, sorted by name. A delete doesn't consult it: deleting the item
    still succeeds, and leaves each of these workflows with a reference that no longer resolves."""

    used_by: List[UsageEntry] = Field(default_factory=list)
