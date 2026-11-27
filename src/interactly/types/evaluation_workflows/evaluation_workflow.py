"""
Response models for evaluation workflows: workflows that analyse a finished conversation, never run on a live call.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from interactly._models import BaseAPIModel

__all__ = ["EvaluationTemplate", "AnalysisNodePreset", "EvaluationWorkflowVersion", "EvaluationWorkflow"]


class EvaluationTemplate(BaseAPIModel):
    """A starting point for a new evaluation workflow."""

    template_id: str
    name: Optional[str] = None
    description: Optional[str] = None


class AnalysisNodePreset(BaseAPIModel):
    """A ready-made analysis node, as the dashboard's evaluation palette offers it."""

    preset_id: str
    label: Optional[str] = None
    description: Optional[str] = None
    #: ``conversation_fetch``, ``analysis_llm`` or ``store_analysis``.
    node_type: Optional[str] = None
    #: The node's config, ready to give a node: copy it and change what differs.
    config: Dict[str, Any] = Field(default_factory=dict)


class EvaluationWorkflowVersion(BaseAPIModel):
    """One version of an evaluation workflow."""

    version_number: int
    version_name: Optional[str] = None
    #: Whether the version stores the conversation with its PHI masked: an enabled Store step keeps the masked
    #: messages a step that is not disabled produces.
    has_phi_masking: bool = False


class EvaluationWorkflow(BaseAPIModel):
    """An evaluation workflow of the team, with each of its versions."""

    workflow_id: str
    name: Optional[str] = None
    active_version_number: Optional[int] = None
    versions: List[EvaluationWorkflowVersion] = Field(default_factory=list)
