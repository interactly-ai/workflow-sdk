from __future__ import annotations

from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, PrivateAttr

from interactly_configs.comment import CommentConfig
from interactly_configs.evaluation import EvaluationRunInfo
from interactly_configs.nodes.node_unions import NodeRunOutput, NodesRunInputs
from interactly_configs.run_input import BaseRunInput, WorkflowCommand
from interactly_configs.run_output import BaseRunOutput
from interactly_configs.workflow import WorkflowConfigFullyHydrated

class WorkflowStatus(str, Enum):
    NOT_STARTED = "not_started"
    STARTED = "started"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"
    PAUSED = "paused"
    WAITING_FOR_USER_INPUT = "waiting_for_user_input"
    CANCELLED = "cancelled"
    ABORTED_LOOPING_RISK = "aborted_looping_risk"

    @staticmethod
    def is_terminal_run_status(status: Optional[WorkflowStatus]) -> bool:
        return status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.ABORTED_LOOPING_RISK,
        }

    # Statuses that could represent workflows that are stuck and need to be reaped by the stale run reaper.
    @staticmethod
    def is_active_run_status(status: Optional[WorkflowStatus]) -> bool:
        return status in {WorkflowStatus.STARTED, WorkflowStatus.RUNNING, WorkflowStatus.WAITING_FOR_USER_INPUT}
        # We are ignoring PAUSED runs because they are intentionally paused and not necessarily stale.
        # The reaper will not mark them as failed.

class WorkflowRunInput(BaseRunInput):
    """
    Input to the workflow, used to kick off or resume a workflow run.
    """

    command: WorkflowCommand = Field(
        default=WorkflowCommand.START,
        description="Command to execute on the workflow or workflow run",
        title="Workflow Command",
    )
    workflow_id: Optional[str] = Field(
        default=None,
        description="DB Object ID of the workflow to run",
        title="Workflow DB Object ID",
    )

    version_number: Optional[int] = Field(
        default=0,
        description="Version number of the workflow this run is associated with. 0 is the initial version (default).",
        title="Workflow Version Number",
    )
    run_by: Optional[str] = Field(
        default=None,
        description="Identifier of the user or system that initiated the workflow run",
        title="Workflow Run Initiator",
    )

    workflow_run_id: Optional[str] = Field(
        default=None,
        description="ID of the workflow run to resume",
        title="Workflow Run ID",
    )

    team_id: Optional[str] = Field(
        default=None,
        description="Team ID associated with this workflow run, used for vendor credential lookup",
        title="Team ID",
    )

    start_node_logical_id: Optional[str] = Field(
        default=None,
        description="Optional logical ID of the node to start execution from, bypassing the default start node.",
        title="Start Node Logical ID",
    )

    initial_state: Optional[dict] = Field(
        default=None,
        description="Optional serialized WorkflowState to resume execution with context.",
        title="Initial Workflow State",
    )

    thread_to_node_inputs: dict[str, NodesRunInputs] = Field(
        default_factory=dict,
        description="Mapping of thread IDs to node inputs",
        title="Thread to Node Inputs",
    )

class WorkflowRunOutput(BaseRunOutput):
    """
    Output of a workflow run.
    """

    thread_to_node_outputs: dict[str, List[NodeRunOutput]] = Field(
        default_factory=dict,
        description="Mapping of thread IDs to lists of node outputs",
        title="Thread to Node Outputs",
    )

class WorkflowRunInputOutputPair(BaseModel):
    """
    Represents a pair of workflow run input and output.
    """

    run_input: Optional[WorkflowRunInput] = Field(
        default=None,
        description="Input to the workflow run",
        title="Workflow Run Input",
    )
    run_output: Optional[WorkflowRunOutput] = Field(
        default=None,
        description="Output of the workflow run",
        title="Workflow Run Output",
    )
    evaluation: Optional[dict] = Field(
        default=None,
        description="Evaluation result for this specific turn/pair.",
        title="Turn Evaluation Result",
    )
    iteration_end_state_miscellaneous: Optional[dict] = Field(
        default=None,
        description="A lightweight capture of global state details at the end of the iteration, like history trackers and active threads, to allow accurate resumption without serializing the entire state.",
        title="Iteration End State Miscellaneous",
    )

class LLMTokenUsage(BaseModel):
    """
    Token usage information for a workflow run, including total tokens and breakdown by model and provider.
    """

    total_input_tokens: Optional[int] = Field(default=0, description="The number of input/prompt tokens used")
    total_output_tokens: Optional[int] = Field(default=0, description="The number of output/completion tokens used")
    total_tokens: Optional[int] = Field(default=0, description="The total number of tokens used")
    call_count_with_user_keys: Optional[int] = Field(
        default=0, description="The number of LLM calls made using user-provided vendor API keys"
    )
    call_count_with_fallback_keys: Optional[int] = Field(
        default=0, description="The number of LLM calls made using fallback environment API keys"
    )
    call_count: Optional[int] = Field(default=0, description="The number of LLM calls")
    breakdown_by_models: Optional[List[LLMTokenUsageByModel]] = Field(
        default=None, description="Breakdown of token usage by LLM model and provider"
    )
    _in_progress_llm_response_ids: set[str] = PrivateAttr(default_factory=set)

class LLMTokenUsageByModel(BaseModel):
    """
    Token usage by LLM model and provider.
    """

    response_model: Optional[str] = Field(default=None, description="The LLM model used")
    provider: Optional[str] = Field(default=None, description="The provider used for the response")
    total_input_tokens: Optional[int] = Field(default=0, description="The number of input/prompt tokens used")
    total_output_tokens: Optional[int] = Field(default=0, description="The number of output/completion tokens used")
    total_tokens: Optional[int] = Field(default=0, description="The total number of tokens used")
    call_count_with_user_keys: Optional[int] = Field(
        default=0, description="The number of LLM calls made using user-provided vendor API keys"
    )
    call_count_with_fallback_keys: Optional[int] = Field(
        default=0, description="The number of LLM calls made using fallback environment API keys"
    )
    call_count: Optional[int] = Field(default=0, description="The number of LLM calls")

class LLMLatencyStatsByModel(BaseModel):
    """
    Latency stats by LLM model and provider.
    """

    response_model: Optional[str] = Field(default=None, description="The LLM model used")
    provider: Optional[str] = Field(default=None, description="The provider used for the response")
    call_count: Optional[int] = Field(default=0, description="The number of LLM calls")
    total_latency_milliseconds: Optional[int] = Field(
        default=0, description="The total latency across all calls in milliseconds"
    )
    average_latency_milliseconds: Optional[float] = Field(
        default=0.0, description="The average latency per call in milliseconds"
    )

class LLMLatencyStats(BaseModel):
    """
    Latency statistics for a workflow run, including total calls, average latency, and breakdown by model.
    """

    call_count: Optional[int] = Field(default=0, description="The number of LLM calls")
    total_latency_milliseconds: Optional[int] = Field(
        default=0, description="The total latency across all calls in milliseconds"
    )
    average_latency_milliseconds: Optional[float] = Field(
        default=0.0, description="The average latency per call in milliseconds"
    )
    breakdown_by_models: Optional[List[LLMLatencyStatsByModel]] = Field(
        default=None, description="Breakdown of latency stats by LLM model and provider"
    )
    _processed_llm_response_ids: set[str] = PrivateAttr(default_factory=set)

class WorkflowRun(BaseModel):
    """
    Represents a workflow run, which is a specific execution of a workflow.
    """

    logical_id: Optional[str] = Field(
        default_factory=lambda: "workflow_run_" + str(uuid4()),
        description="Unique ID associated with this particular run of the workflow",
        title="Workflow Run Logical ID",
    )
    workflow_id: Optional[str] = Field(
        default=None,
        description="ID of the workflow being run",
        title="Workflow ID",
    )

    version_number: Optional[int] = Field(
        default=0,
        description="Version number of the workflow this run is associated with. 0 is the initial version (default).",
        title="Workflow Version Number",
    )

    status: WorkflowStatus = Field(
        default=WorkflowStatus.NOT_STARTED,
        description="Current status of the workflow run",
        title="Workflow Run Status",
    )
    termination_source: Optional[str] = Field(
        default=None,
        description="Describes what caused the run to reach a terminal state (especially FAILED). "
        "None for normal completions. Well-known values: 'execution_error', 'stale_run_reaper', 'finally_safety_net'.",
        title="Termination Source",
    )
    input_output_pairs: List[WorkflowRunInputOutputPair] = Field(
        default_factory=list,
        description="List of input-output pairs. Each pair corresponds to each contiguous execution segment of the workflow",
        title="Workflow Run Input-Output Pairs",
    )
    run_by: Optional[str] = Field(
        default=None,
        description="Identifier of the user or system that initiated the workflow run",
        title="Workflow Run Initiator",
    )
    comments: List[CommentConfig] = Field(
        default_factory=list,
        description="List of comments associated with the workflow run",
        title="Workflow Run Comments",
    )
    llm_token_usage: Optional[LLMTokenUsage] = Field(
        default=None,
        description="LLM token usage for this run",
        title="LLM Token Usage",
    )
    llm_latency_stats: Optional[LLMLatencyStats] = Field(
        default=None,
        description="LLM latency statistics for this run",
        title="LLM Latency Stats",
    )
    version_name: Optional[str] = Field(
        default="Initial Version",
        description="Version name of the workflow this run is associated with",
        title="Workflow Version Name",
    )
    workflow_config_fully_hydrated: Optional[WorkflowConfigFullyHydrated] = Field(
        default=None,
        description="Fully hydrated workflow configuration at the time of execution",
        title="Workflow Config Fully Hydrated",
    )
    workflow_run_id: Optional[str] = Field(
        default=None,
        description="DB Object ID of this workflow run",
        title="Workflow Run DB Object ID",
    )
    miscellaneous: Optional[dict] = Field(
        default=None,
        description="Miscellaneous metadata that can be used by the workflow run",
        title="Miscellaneous",
    )

    source_workflow_run_id: Optional[str] = Field(
        default=None,
        description="For evaluation runs, this is the id of the original workflow run being evaluated. For checkpoint resumed runs, this is the id of the parent run being cloned.",
        title="Source Workflow Run ID",
    )

    checkpoint_source_turn_index: Optional[int] = Field(
        default=None,
        description="For checkpoint resumed runs, this stores the turn index of the parent run that was cloned.",
        title="Checkpoint Source Turn Index",
    )

    carried_over_llm_token_usage: Optional[LLMTokenUsage] = Field(
        default=None,
        description="For checkpoint resumed runs, this stores the token usage incurred up to the checkpoint index from the source run.",
        title="Carried Over LLM Token Usage",
    )

    carried_over_llm_latency_stats: Optional[LLMLatencyStats] = Field(
        default=None,
        description="For checkpoint resumed runs, this stores the latency stats incurred up to the checkpoint index from the source run.",
        title="Carried Over LLM Latency Stats",
    )

    is_evaluation_run: bool = Field(
        default=False,
        description="Flag indicating if this workflow run is an evaluation run triggered automatically after another workflow run completed",
        title="Is Evaluation Run",
    )

    evaluation_run_info: Optional[EvaluationRunInfo] = Field(
        default=None,
        description="Information about the evaluation triggered for this workflow run. Populated after evaluation completes. Only present for source workflow runs that have been evaluated.",
        title="Evaluation Run Info",
    )
