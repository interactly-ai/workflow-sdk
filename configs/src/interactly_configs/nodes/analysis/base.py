"""Shared base for the analysis node types offered in evaluation workflows."""

from typing import Any, Iterable, Optional

from pydantic import Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    GlobalNodeConfig,
    NodeCategory,
    SelfLoopConfig,
)
from interactly_configs.workflow_type import WorkflowType

# Analysis section -> the conversation field it is saved as; anything else a workflow stores goes under `extras`.
ANALYSIS_SECTION_FIELDS = {
    "summary": "summary",
    "success_evaluation": "successEvaluation",
    "structured_data": "structuredData",
    "dnd": "dnd",
    "callback": "callback",
    "outcome": "outcome",
}
ANALYSIS_SECTION_KEYS = tuple(ANALYSIS_SECTION_FIELDS)


class BaseAnalysisNodeConfig(BaseNodeConfig):
    """Hides the conversational settings an analysis step never uses, so its form shows only what matters."""

    primary_category: Optional[str] = Field(
        default=NodeCategory.ANALYSIS.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    is_guardrail_node: bool = Field(
        default=False,
        description="Analysis steps are never guardrail nodes.",
        title="Is Guardrail Node",
    )
    global_node_config: Optional[GlobalNodeConfig] = Field(
        default=None,
        description="Analysis steps are never global nodes.",
        title="Global Node Configuration",
    )
    self_loop_config: Optional[SelfLoopConfig] = Field(
        default=None,
        description="Analysis steps run once.",
        title="Self Loop",
    )


def misplaced_analysis_steps(node_configs: Iterable[Any], workflow_type: Any) -> Optional[str]:
    """Why these nodes cannot go in a workflow of this type, or None: analysis steps belong to evaluation workflows."""
    if (getattr(workflow_type, "value", workflow_type) or WorkflowType.STANDARD.value) == WorkflowType.EVALUATION.value:
        return None
    names = [node.name or node.type for node in node_configs if isinstance(node, BaseAnalysisNodeConfig)]
    if not names:
        return None
    return f"{', '.join(names)}: analysis steps run only in evaluation workflows, and this workflow is a standard one."
