"""
Response model for a single Workflow resource.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel
from interactly._utils._logs import logger

# ``WorkflowStatus`` is re-exported for callers who want to compare
# ``Workflow.status`` against known values; the field itself is typed
# ``Optional[str]`` so server-side additions don't raise ``ValidationError``.
from interactly.types.shared import WorkflowStatus  # noqa: F401

__all__ = ["Workflow", "WorkflowVersion"]


class WorkflowVersion(BaseAPIModel):
    """A version snapshot of a workflow's configuration."""

    version_number: int
    version_name: Optional[str] = None
    is_active: bool = False
    created_at: Optional[datetime] = None
    # Type is Dict when interactly_configs is not installed; upgraded to WorkflowConfig by the validator.
    config: Optional[Any] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Unwrap the server's single-object envelope: ``{"version": {...}}``
        inner = data.get("version")
        if isinstance(inner, dict) and "version_number" not in data:
            parent_active = data.get("parent_active_version")
            data = dict(inner)
            if parent_active is not None and "version_number" in data:
                data["is_active"] = (data["version_number"] == parent_active)

        raw = data.get("config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import WorkflowConfig as _WC
            from interactly_configs import WorkflowConfigFullyHydrated as _WCFH
        except Exception:
            # interactly_configs not installed — leave the raw dict in place.
            return data

        # The versions endpoint may return a hydrated config (inlined nodes), so
        # prefer the fully-hydrated shape and fall back to the lighter one. Keep
        # the raw dict if neither matches rather than silently masking mismatches.
        try:
            data["config"] = _WCFH.model_validate(raw)
        except Exception as hydrated_err:
            try:
                data["config"] = _WC.model_validate(raw)
            except Exception as base_err:
                logger.debug(
                    "WorkflowVersion.config did not match WorkflowConfigFullyHydrated (%s) "
                    "or WorkflowConfig (%s); leaving as raw dict.",
                    hydrated_err,
                    base_err,
                )
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
            execution_url = data.get("execution_url")
            data = dict(inner)
            if execution_url is not None and "execution_url" not in data:
                data["execution_url"] = execution_url

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
