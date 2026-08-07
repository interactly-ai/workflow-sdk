from typing import Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
    NodeType,
)


class WorkflowRunFetchNodeConfig(BaseNodeConfig):
    type: Literal["workflow_run_fetch"] = Field(
        default=NodeType.WORKFLOW_RUN_FETCH.value,
        description="Type of the node. Must be 'workflow_run_fetch'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.SYSTEM.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.EVALUATION.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    workflow_run_id: Optional[str] = Field(
        default="{{workflow_run_id}}",
        description="ID of the workflow run to fetch",
        title="Workflow Run ID",
    )

    result_runtime_variable_name: Optional[str] = Field(
        default="workflow_run_object",
        description="Name of the runtime variable to store the result in",
        title="Result Runtime Variable Name",
    )

    model_config = ConfigDict(
        title="Workflow Run Fetch Node Configuration",
    )

class WorkflowRunFetchNodeRunInput(BaseNodeRunInput):
    type: Literal["workflow_run_fetch"] = Field(
        default="workflow_run_fetch", description="Discriminator field which must always be 'workflow_run_fetch'"
    )

class WorkflowRunFetchNodeRunOutput(BaseNodeRunOutput):
    type: Literal["workflow_run_fetch"] = Field(
        default="workflow_run_fetch", description="Discriminator field which must always be 'workflow_run_fetch'"
    )
    fetched_workflow_run: Optional[str] = Field(
        default=None,
        description="The fetched workflow run as a stringified JSON object",
        title="Fetched Workflow Run",
    )
