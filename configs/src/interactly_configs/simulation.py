from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

class SimulationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class SimulationWorkflowDetails(BaseModel):
    workflow_id: Optional[str] = Field(
        default=None,
        description="DB Object ID of the workflow this simulation is associated with",
        title="Workflow DB Object ID",
    )
    version_number: Optional[int] = Field(
        default=0,
        description="Version number of the workflow this simulation is associated with. 0 is the initial version (default).",
        title="Workflow Version Number",
    )
    version_name: Optional[str] = Field(
        default=None,
        description="Version name of the workflow this simulation is associated with",
        title="Workflow Version Name",
    )
    dynamic_variables: Optional[dict] = Field(
        default_factory=dict,
        description="Dynamic variables to apply to the workflow",
        title="Workflow Dynamic Variables",
    )
    name: Optional[str] = Field(
        default=None,
        description="Name of the selected workflow",
        title="Selected Workflow Name",
    )
    total_events: Optional[int] = Field(
        default=0,
        description="Total number of events processed in the selected workflow",
        title="Total Events",
    )
    total_nodes: Optional[int] = Field(
        default=0,
        description="Total number of nodes in the selected workflow",
        title="Total Nodes",
    )
    total_duration_seconds: Optional[int] = Field(
        default=0,
        description="Total duration in seconds for the selected workflow",
        title="Total Duration Seconds",
    )
    run_id: Optional[str] = Field(
        default=None,
        description="Workflow Run ID of the executed workflow",
        title="Workflow Run ID",
    )

class SimulationConfig(BaseModel):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "simulation_" + str(uuid4()),
        description="Unique identifier for the simulation",
        title="Simulation Logical ID",
    )
    status: Optional[SimulationStatus] = Field(
        default=SimulationStatus.PENDING,
        description="Status of the simulation configuration (reflects latest run)",
        title="Simulation Status",
    )
    name: Optional[str] = Field(
        default=None,
        description="Name of the simulation",
        title="Simulation Name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the simulation",
        title="Simulation Description",
    )
    selected_workflow: Optional[SimulationWorkflowDetails] = Field(
        default_factory=SimulationWorkflowDetails,
        description="Details about the selected workflow execution",
        title="Selected Workflow Details",
    )
    counter_workflow: Optional[SimulationWorkflowDetails] = Field(
        default_factory=SimulationWorkflowDetails,
        description="Details about the counter workflow execution",
        title="Counter Workflow Details",
    )
    timeout_seconds: Optional[int] = Field(
        default=120,  # 2 minutes
        description="Maximum time in seconds to run the simulation",
        title="Timeout Seconds",
    )
    max_events: Optional[int] = Field(
        default=3000,
        description="Maximum number of events to process in the simulation",
        title="Max Events",
    )
    number_of_simulations: Optional[int] = Field(
        default=1,
        description="Number of times to run the simulation",
        title="Number of Simulations",
    )
    max_concurrent_runs: Optional[int] = Field(
        default=1,
        description="Maximum number of concurrent simulation runs allowed",
        title="Max Concurrent Runs",
    )
    assistant_starts_first: Optional[bool] = Field(
        default=True,
        description="If True, the assistant workflow will kick off first, else it will be the user workflow.",
        title="Assistant Starts First",
    )
    stop_on_failure: Optional[bool] = Field(
        default=False,
        description="Whether to stop the simulation on failure",
        title="Stop on Failure",
    )
    status: Optional[SimulationStatus] = Field(
        default=SimulationStatus.PENDING,
        description="Current status of the simulation",
        title="Simulation Status",
    )
    run_by: Optional[str] = Field(
        default=None,
        description="Identifier of the user or system that initiated the workflow simulation",
        title="Workflow Simulation Initiator",
    )

class SimulationCommand(str, Enum):
    DATA = "data"
    STOP = "stop"

class SimulationInput(BaseModel):
    """
    Input to the workflow copilot, used to kick off or resume a workflow copilot.
    """

    command: SimulationCommand = Field(
        default=SimulationCommand.DATA,
        description="Command to execute on the workflow copilot",
        title="Workflow Copilot Command",
    )
    simulation_id: Optional[str] = Field(
        default=None,
        description="Database ID of the simulation to run or control",
        title="Simulation ID",
    )
    simulation_config: Optional[SimulationConfig] = Field(
        default_factory=SimulationConfig,
        description="Configuration for the simulation",
        title="Simulation Configuration",
    )

class SimulationEvent(BaseModel):
    """
    Event model for the workflow simulation.
    """

    type: Literal["simulation_general_event", "selected_workflow_event", "counter_workflow_event"] = Field(
        default="simulation_general_event",
        description="Type of the workflow event",
        title="Workflow Event Type",
    )

    simulation_logical_id: Optional[str] = Field(
        default=None,
        description="Logical ID of the simulation",
        title="Simulation Logical ID",
    )

    simulation_id: Optional[str] = Field(
        default=None,
        description="Database ID of the simulation",
        title="Simulation ID",
    )

    message: Optional[str] = Field(
        default=None,
        description="Message describing the event",
        title="Event Message",
    )

    run_id: Optional[str] = Field(
        default=None,
        description="Workflow Run ID associated with the event",
        title="Workflow Run ID",
    )

    payload: Optional[Any] = Field(
        default=None,
        description="Payload of the workflow event",
        title="Workflow Event Payload",
    )
