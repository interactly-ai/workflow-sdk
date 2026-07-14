"""
Response models for super nodes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["SuperNodeSummary", "SuperNodeDetail", "SuperNodeDependent", "SuperNodeExpandPreview"]


class SuperNodeSummary(BaseAPIModel):
    """Lightweight representation of a published super node."""

    workflow_id: str
    workflow_version_number: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    num_input_fields: int


class SuperNodeDetail(BaseAPIModel):
    """Full super node definition including interface and hydrated workflow config."""

    workflow_id: str
    workflow_version_number: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    super_node_interface: Optional[Dict[str, Any]] = None
    # Type is Dict when interactly_configs is not installed; upgraded to WorkflowConfigFullyHydrated by the validator.
    encapsulated_workflow_config: Optional[Any] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_encapsulated_workflow_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw = data.get("encapsulated_workflow_config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import WorkflowConfigFullyHydrated as _WCFH

            data["encapsulated_workflow_config"] = _WCFH.model_validate(raw)
        except Exception:
            pass
        return data


class SuperNodeDependent(BaseAPIModel):
    """A workflow that embeds a given super node."""

    workflow_id: str
    name: Optional[str] = None
    description: Optional[str] = None


class SuperNodeExpandPreview(BaseAPIModel):
    """Preview of a workflow with all super nodes inlined as flat nodes/edges."""

    workflow_id: str
    version_number: Optional[int] = None
    # Type is Dict when interactly_configs is not installed; upgraded to WorkflowConfigFullyHydrated by the validator.
    expanded_config: Optional[Any] = None
    super_node_origins: List[str] = []
    expansion_report: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_expanded_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw = data.get("expanded_config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import WorkflowConfigFullyHydrated as _WCFH

            data["expanded_config"] = _WCFH.model_validate(raw)
        except Exception:
            pass
        return data
