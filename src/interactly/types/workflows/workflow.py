"""
Response model for a single Workflow resource.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field, model_validator

from interactly._models import BaseAPIModel
from interactly._utils._logs import logger

# ``WorkflowStatus`` is re-exported for callers who want to compare
# ``Workflow.status`` against known values; the field itself is typed
# ``Optional[str]`` so server-side additions don't raise ``ValidationError``.
from interactly.types.shared import WorkflowStatus  # noqa: F401

__all__ = ["Workflow", "WorkflowVersion"]

#: Keys only a fully hydrated config has: its settings, nodes and edges side by side.
_HYDRATED_KEYS = frozenset({"workflow_config", "node_configs", "edge_configs"})


class WorkflowVersion(BaseAPIModel):
    """A version snapshot of a workflow's configuration."""

    version_number: int
    version_name: Optional[str] = None
    is_active: bool = False
    created_at: Optional[datetime] = None
    # Type is Dict when interactly_configs is not installed; upgraded to WorkflowConfig by the validator.
    config: Optional[Any] = None
    #: Advisory authoring lints the server returned with this write. The write succeeded either way;
    #: these are things worth fixing, such as a variable a tool needs that is never defined. Empty on
    #: reads and on routes that do not lint.
    warnings: List[str] = Field(default_factory=list)
    #: Global tools this write removed from nodes' ``excluded_global_tools``, as node logical id -> tool keys,
    #: because the write removed those tools from the version. Code holding those nodes should drop the same keys,
    #: or its next save of one of them writes them back. Empty unless the write changed the global tools.
    pruned_global_tool_exclusions: Dict[str, List[str]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Unwrap the server's single-object envelope: ``{"version": {...}, ...}``.
        inner = data.get("version")
        if isinstance(inner, dict) and "version_number" not in data:
            parent_active = data.get("parent_active_version")
            data = _unwrap(data, "version")
            if parent_active is not None and "version_number" in data:
                data["is_active"] = (data["version_number"] == parent_active)

        # A version record holds its settings as ``workflow_config``.
        if data.get("config") is None and isinstance(data.get("workflow_config"), dict):
            data = {**data, "config": data["workflow_config"]}

        raw = data.get("config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import WorkflowConfig as _WC
            from interactly_configs import WorkflowConfigFullyHydrated as _WCFH
        except Exception:
            # interactly_configs not installed — leave the raw dict in place.
            return data

        # A hydrated config (settings plus inlined nodes and edges) says so by its keys. Every field of the hydrated
        # model is optional, so it would also accept plain settings and drop them all: choose by the keys, and keep
        # the raw dict if the chosen model refuses it rather than masking the mismatch.
        model = _WCFH if _HYDRATED_KEYS & set(raw) else _WC
        try:
            data = {**data, "config": model.model_validate(raw)}
        except Exception as err:
            logger.debug("WorkflowVersion.config did not match %s (%s); leaving as raw dict.", model.__name__, err)
        return data


class Workflow(BaseAPIModel):
    """Full representation of a Workflow resource as returned by the API."""

    id: str
    # Optional because incomplete/empty workflows (e.g. created without a config)
    # come back with a null ``workflow_config`` and therefore no name; listing
    # must not crash on them.
    name: Optional[str] = None
    description: Optional[str] = None
    # Typed as ``str`` (not ``WorkflowStatus``) for forward-compat with unknown
    # server values; compare against ``WorkflowStatus`` members as needed.
    status: Optional[str] = None

    # The team this workflow belongs to.
    team_id: Optional[str] = None
    created_by: Optional[str] = None

    # Active version info (if included in the response).
    active_version_number: Optional[int] = None

    # Concurrency limit — maximum simultaneous runs.
    max_concurrent_runs: Optional[int] = None

    # Timestamps.
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Server may include the full version list.
    versions: Optional[List[WorkflowVersion]] = None

    # Present on create/get/update/clone responses (``WorkflowsResponse``);
    # the REST path used to execute this workflow.
    execution_url: Optional[str] = None

    #: Advisory authoring lints the server returned with this write. The write succeeded either way;
    #: these are things worth fixing, such as a variable a tool needs that is never defined. Empty on
    #: reads and on routes that do not lint.
    warnings: List[str] = Field(default_factory=list)
    #: Global tools this write removed from nodes' ``excluded_global_tools``, as node logical id -> tool keys; see
    #: :attr:`WorkflowVersion.pruned_global_tool_exclusions`. Empty unless the write changed the global tools.
    pruned_global_tool_exclusions: Dict[str, List[str]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _flatten_backend_shape(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Unwrap the server's single-object envelope: the create/get/update/clone
        # endpoints return ``{"workflow": {...}, "execution_url": ...}``. Only
        # descend if the wrapper key is present AND the inner object isn't already
        # flattened (so list rows / already-flat payloads pass through untouched).
        inner = data.get("workflow")
        if isinstance(inner, dict) and "_id" not in data and "id" not in data and "workflow_config" not in data:
            data = _unwrap(data, "workflow")

        # Extract ID
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        elif "id" in data:
            data["id"] = str(data["id"])

        # Extract properties from workflow_config
        config = data.get("workflow_config")
        if isinstance(config, dict):
            if "name" in config and "name" not in data:
                data["name"] = config["name"]
            if "description" in config and "description" not in data:
                data["description"] = config["description"]
            if "status" in config and "status" not in data:
                data["status"] = config["status"]

        return data


def _unwrap(envelope: Dict[str, Any], key: str) -> Dict[str, Any]:
    """The record under ``key``, with every other set key of the envelope beside it, unless the record has its own.

    So a key the server adds to the envelope (``execution_url``, ``warnings``, ``pruned_global_tool_exclusions``,
    and whatever comes next) is readable the day it ships, as a field or an extra.
    """
    record = dict(envelope[key])
    for name, value in envelope.items():
        if name != key and name not in record and value is not None:
            record[name] = value
    return record
