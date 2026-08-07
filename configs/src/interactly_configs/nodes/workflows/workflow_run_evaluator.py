from typing import Literal, Optional
from uuid import uuid4

from pydantic import ConfigDict, Field

from interactly_configs.nodes.llm.llm import (
    LLMNodeRunInput,
    WorkerLLMNodeConfig,
    WorkerLLMNodeRunOutput,
)


class WorkflowRunEvalLLMNodeConfig(WorkerLLMNodeConfig):
    """Configuration for nodes that evaluate workflow runs.

    Evaluator nodes are used to assess, summarize and score outputs from workflow runs.
    """

    type: Literal["workflow_run_evaluator"] = Field(
        default="workflow_run_evaluator",
        description="Type of the node. Must be 'workflow_run_evaluator'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default="System",
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default="Evaluation",
        description="Secondary category of the node",
        title="Secondary Category",
    )
    structured_output_schema: Optional[dict] = Field(
        default=None,
        description="Schema for the structured evaluation output. If empty or None, no structured output is expected.",
        title="Structured Output Schema",
    )
    input_runtime_variable_name: Optional[str] = Field(
        default="workflow_run_object",
        description="Runtime variable name from which to read the input to be evaluated. It is expected to contain the 'WorkflowRun' object to be evaluated.",
        title="Input Runtime Variable Name",
    )
    output_runtime_variable_name: Optional[str] = Field(
        default_factory=lambda: f"evaluator_output_{uuid4().hex}",
        description="Runtime variable name to store the structured evaluation output",
        title="Output Runtime Variable Name",
    )
    is_turn_by_turn_evaluator: bool = Field(
        default=False,
        description="Indicates if this evaluator is intended to evaluate each turn in a multi-turn workflow run",
        title="Is Turn-by-Turn Evaluator",
    )
    self_loop: bool = Field(
        default=False,
        description="Evaluator nodes should not have self-loops, so this option is disabled",
        title="Self Loop",
    )
    wait_for_user_message: bool = Field(
        default=False,
        description="Evaluator nodes should not wait for user messages to proceed, so this option is disabled",
        title="Wait for User Message",
    )
    default_error_message: Optional[str] = Field(
        default=None,
        description="Evaluator nodes should not have default error messages, so this option is disabled",
        title="Default Error Message",
    )

    model_config = ConfigDict(
        title="Evaluator Node",
    )

class WorkflowRunEvalLLMNodeRunInput(LLMNodeRunInput):
    """Input model for evaluator node execution."""

    type: Literal["workflow_run_evaluator"] = Field(
        default="workflow_run_evaluator",
        description="Discriminator field which must always be 'workflow_run_evaluator'",
    )

class WorkflowRunEvalLLMNodeRunOutput(WorkerLLMNodeRunOutput):
    """Output model for evaluator node execution."""

    type: Literal["workflow_run_evaluator"] = Field(
        default="workflow_run_evaluator",
        description="Discriminator field which must always be 'workflow_run_evaluator'",
    )
    free_form_output: Optional[str] = Field(
        default=None,
        description="Free-form textual evaluation output from the evaluator node",
        title="Free-form Output",
    )
    structured_output: dict = Field(
        default_factory=dict,
        description="Structured evaluation output from the evaluator node",
        title="Structured Output",
    )
