"""
Response models for the read-only questions you can ask about a stored workflow.

* ``client.workflows.lints`` — every advisory lint, run against the whole graph.
* ``client.workflows.realtime_compatibility`` — whether the workflow can run its voice calls on a
  realtime (speech-to-speech) model.
* ``client.workflows.counter_workflow`` / ``generate_counter_workflow`` — the simulated-caller workflow
  generated from this one, and the state of its newest generation run.

Shapes captured from the dev server.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import Field

from interactly._models import BaseAPIModel

__all__ = [
    "WorkflowLintReport",
    "RealtimeCompatibilityFinding",
    "RealtimeCompatibilityReport",
    "CounterGenerationState",
    "ExistingCounterWorkflow",
    "CounterWorkflowStatus",
]


class WorkflowLintReport(BaseAPIModel):
    """Advisory lints for a stored workflow.

    The same checks that run on a fully-hydrated create, but against the whole graph, which is the only
    way to answer the graph-wide ones (a cross-thread reference to a thread that does not exist, a
    waiting condition that could never fire). Run **after super-node expansion**; if expansion fails the
    outer graph is linted anyway and ``super_nodes_expanded`` is ``False``.
    """

    workflow_id: Optional[str] = None
    #: ``None`` means the active version was linted.
    version_number: Optional[int] = None
    super_nodes_expanded: Optional[bool] = None
    warnings: List[str] = Field(default_factory=list)


class RealtimeCompatibilityFinding(BaseAPIModel):
    """One reason a workflow is, or may not be, ready for realtime voice."""

    code: Optional[str] = None
    #: ``blocker``, ``warning`` or ``indeterminate``.
    severity: Optional[str] = None
    message: Optional[str] = None
    #: ``message`` with its location appended, worded identically for every client.
    description: Optional[str] = None
    node_logical_id: Optional[str] = None
    node_name: Optional[str] = None
    edge_logical_id: Optional[str] = None
    #: Set when the finding is inside an expanded super node.
    super_node_path: Optional[Any] = None


class RealtimeCompatibilityReport(BaseAPIModel):
    """Whether a workflow can run its voice calls on a realtime (speech-to-speech) model.

    ``model`` echoes what was asked about: the two realtime protocols differ enough that the same
    workflow can be ready on one model and not another. Without a model, the findings describe what holds
    on either. Analysed after super-node expansion; a super node that could not be expanded is reported
    as ``indeterminate`` rather than assumed fine.
    """

    workflow_id: Optional[str] = None
    version_number: Optional[int] = None
    model: Optional[str] = None
    super_nodes_expanded: Optional[bool] = None
    supported: Optional[bool] = None
    summary: Optional[str] = None
    blockers: List[RealtimeCompatibilityFinding] = Field(default_factory=list)
    warnings: List[RealtimeCompatibilityFinding] = Field(default_factory=list)
    indeterminate: List[RealtimeCompatibilityFinding] = Field(default_factory=list)


class CounterGenerationState(BaseAPIModel):
    """Progress of one counter-workflow generation run.

    Generation runs in the background on the server and makes several LLM calls, so a start returns
    immediately with ``status`` ``pending``; poll ``client.workflows.counter_workflow`` for progress.
    """

    source_workflow_id: Optional[str] = None
    source_version_number: Optional[int] = None
    #: ``pending``, ``running``, ``completed`` or ``failed``.
    status: Optional[str] = None
    instructions: Optional[str] = None
    provider: Optional[str] = None
    num_cases_requested: Optional[int] = None
    #: Updated as batches land, so progress is visible before the run completes.
    num_cases_generated: Optional[int] = None
    generated_workflow_id: Optional[str] = None
    generated_version_number: Optional[int] = None
    warnings: List[str] = Field(default_factory=list)
    #: The failure reason when ``status`` is ``failed``.
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExistingCounterWorkflow(BaseAPIModel):
    """The counter workflow already generated for a workflow."""

    workflow_id: Optional[str] = None
    name: Optional[str] = None
    #: The version holding the newest case set.
    active_version_number: Optional[int] = None
    case_count: Optional[int] = None
    #: The version of the source workflow the cases were written against.
    generated_for_version_number: Optional[int] = None


class CounterWorkflowStatus(BaseAPIModel):
    """Is there a counter workflow for this workflow, and is a generation running? One call answers both."""

    counter_workflow: Optional[ExistingCounterWorkflow] = None
    #: The newest generation run, if any.
    generation: Optional[CounterGenerationState] = None
