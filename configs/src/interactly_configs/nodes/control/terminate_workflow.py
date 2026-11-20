from typing import Literal, Optional

from pydantic import Field

from interactly_configs.nodes.control.base import BaseControlNodeConfig, BaseControlNodeRunOutput
from interactly_configs.nodes.node import BaseNodeRunInput, NodeFailurePolicy
from interactly_configs.workflow_outcome import WorkflowOutcome


class TerminateWorkflowNodeConfig(BaseControlNodeConfig):
    """
    Ends the whole run at once, with an outcome (completed, failed or cancelled) and a reason. Every thread ends with
    it, and the run is stored with the status its outcome names.
    """

    type: Literal["terminate_workflow"] = Field(
        default="terminate_workflow", description="Type of the node. Must be 'terminate_workflow'"
    )
    outcome: WorkflowOutcome = Field(
        default="completed",
        description="How the run ends: the status it is stored with (completed, failed or cancelled)",
        title="Outcome",
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            "Why the run ends, recorded with it. May use {{dynamic}} and [[runtime]] variables, filled in when the "
            "node runs, such as 'Patient declined: [[decline_reason]]'."
        ),
        title="Reason",
    )
    on_failure: NodeFailurePolicy = Field(
        default=NodeFailurePolicy.ROUTE,
        description="A Terminate workflow node cannot fail, so it has no failure policy.",
        title="On Failure",
    )


class TerminateWorkflowNodeRunInput(BaseNodeRunInput):
    type: Literal["terminate_workflow"] = Field(
        default="terminate_workflow", description="Discriminator field which must always be 'terminate_workflow'"
    )


class TerminateWorkflowNodeRunOutput(BaseControlNodeRunOutput):
    type: Literal["terminate_workflow"] = Field(
        default="terminate_workflow", description="Discriminator field which must always be 'terminate_workflow'"
    )
