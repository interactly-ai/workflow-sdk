"""
Request parameter types for workflow endpoints.

All request params are defined as TypedDict so callers get IDE autocomplete
and mypy type checking without instantiating model classes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from typing_extensions import NotRequired, TypedDict

from interactly._types import NOT_GIVEN, NotGivenOr
from interactly.types._config_types import WorkflowConfigOrDict

__all__ = [
    "WorkflowCreateParams",
    "WorkflowUpdateParams",
    "WorkflowListParams",
    "WorkflowConcurrencyParams",
    "WorkflowCloneParams",
    "VersionCreateParams",
    "VersionUpdateParams",
    "VersionConfigUpdateParams",
]


class WorkflowCreateParams(TypedDict):
    """Parameters for ``client.workflows.create()``."""

    name: str
    description: NotRequired[Optional[str]]
    # Workflow configuration graph (nodes + edges). Accepts a typed WorkflowConfig or a plain dict.
    config: NotRequired[Optional[WorkflowConfigOrDict]]


class WorkflowUpdateParams(TypedDict):
    """Parameters for ``client.workflows.update()``.

    Only supplied keys are sent in the PATCH request body.
    Pass NOT_GIVEN (the default) to omit a field entirely.
    """

    name: NotRequired[NotGivenOr[str]]
    description: NotRequired[NotGivenOr[Optional[str]]]


class WorkflowListParams(TypedDict):
    """Query parameters for ``client.workflows.list()``."""

    page: NotRequired[int]
    size: NotRequired[int]
    search: NotRequired[Optional[str]]


class WorkflowConcurrencyParams(TypedDict):
    """Parameters for ``client.workflows.update_concurrency()``."""

    max_concurrent_runs: int


class WorkflowCloneParams(TypedDict):
    """Parameters for ``client.workflows.clone()``."""

    name: NotRequired[Optional[str]]


class VersionCreateParams(TypedDict):
    """Parameters for ``client.workflows.versions.create()``."""

    version_name: NotRequired[Optional[str]]
    mark_as_active: NotRequired[bool]
    source_version_number: NotRequired[Optional[int]]


class VersionUpdateParams(TypedDict):
    """Parameters for ``client.workflows.versions.update()``."""

    version_name: str


class VersionConfigUpdateParams(TypedDict):
    """Parameters for ``client.workflows.versions.update_config()``."""

    config: WorkflowConfigOrDict
