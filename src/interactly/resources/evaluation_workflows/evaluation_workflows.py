"""
EvaluationWorkflowsResource — evaluation workflows: workflows that analyse a finished conversation (a summary, a
success verdict, structured data) and store what they find. They are never run on a live call.

Endpoints:
    GET    /v1/evaluation-workflows/templates       → templates
    GET    /v1/evaluation-workflows/node-presets    → node_presets
    POST   /v1/evaluation-workflows/from-template   → create_from_template
    GET    /v1/evaluation-workflows                 → list

An evaluation workflow is a workflow like any other once created: ``client.workflows`` reads, versions, exports and
deletes it, and ``client.workflows.list(workflow_type="evaluation")`` lists it among the team's workflows.
"""

from __future__ import annotations

from typing import Any, Dict, List

from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly.types.evaluation_workflows.evaluation_workflow import (
    AnalysisNodePreset,
    EvaluationTemplate,
    EvaluationWorkflow,
)
from interactly.types.workflows.workflow import Workflow

__all__ = ["EvaluationWorkflowsResource", "AsyncEvaluationWorkflowsResource"]

_PATH = "/v1/evaluation-workflows"


class EvaluationWorkflowsResource(SyncAPIResource):
    """Synchronous interface to the Evaluation Workflows API."""

    def templates(self) -> List[EvaluationTemplate]:
        """The templates a new evaluation workflow can start from."""
        raw = self._client.get(f"{_PATH}/templates", cast_to=dict)
        return [EvaluationTemplate.model_validate(t) for t in raw.get("templates", [])]

    def node_presets(self) -> List[AnalysisNodePreset]:
        """The ready-made analysis nodes, in the order a workflow usually uses them."""
        raw = self._client.get(f"{_PATH}/node-presets", cast_to=dict)
        return [AnalysisNodePreset.model_validate(p) for p in raw.get("presets", [])]

    def create_from_template(self, *, template_id: str, name: str) -> Workflow:
        """Create an evaluation workflow from a template.

        Args:
            template_id: A template's ``template_id``, from :meth:`templates`.
            name:        The new workflow's name.

        Returns:
            The created :class:`Workflow`, with version 0 active.

        Raises:
            NotFoundError:   no template with this id.
            BadRequestError: the template uses a node type this server has not enabled.
        """
        return self._client.post(
            f"{_PATH}/from-template", body=_create_body(template_id, name), cast_to=Workflow
        )

    def list(self) -> List[EvaluationWorkflow]:
        """The team's evaluation workflows, by name, each with its versions and whether they mask PHI. Not paged."""
        raw = self._client.get(_PATH, cast_to=dict)
        return [EvaluationWorkflow.model_validate(w) for w in raw.get("workflows", [])]


class AsyncEvaluationWorkflowsResource(AsyncAPIResource):
    """Asynchronous interface to the Evaluation Workflows API."""

    async def templates(self) -> List[EvaluationTemplate]:
        """The templates a new evaluation workflow can start from."""
        raw = await self._client.get(f"{_PATH}/templates", cast_to=dict)
        return [EvaluationTemplate.model_validate(t) for t in raw.get("templates", [])]

    async def node_presets(self) -> List[AnalysisNodePreset]:
        """The ready-made analysis nodes, in the order a workflow usually uses them."""
        raw = await self._client.get(f"{_PATH}/node-presets", cast_to=dict)
        return [AnalysisNodePreset.model_validate(p) for p in raw.get("presets", [])]

    async def create_from_template(self, *, template_id: str, name: str) -> Workflow:
        """Create an evaluation workflow from a template; see :meth:`EvaluationWorkflowsResource.create_from_template`."""
        return await self._client.post(
            f"{_PATH}/from-template", body=_create_body(template_id, name), cast_to=Workflow
        )

    async def list(self) -> List[EvaluationWorkflow]:
        """The team's evaluation workflows, by name, each with its versions. Not paged."""
        raw = await self._client.get(_PATH, cast_to=dict)
        return [EvaluationWorkflow.model_validate(w) for w in raw.get("workflows", [])]


def _create_body(template_id: str, name: str) -> Dict[str, Any]:
    return {"template_id": template_id, "name": name}
