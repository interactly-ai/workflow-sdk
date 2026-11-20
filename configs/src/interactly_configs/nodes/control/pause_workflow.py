from typing import Literal, Optional

from pydantic import Field

from interactly_configs.nodes.control.base import BaseControlNodeConfig, BaseControlNodeRunOutput
from interactly_configs.nodes.node import BaseNodeRunInput
from interactly_configs.pauses import MAX_WAITING_SECONDS, PausableNodeConfig


class PauseWorkflowNodeConfig(PausableNodeConfig, BaseControlNodeConfig):
    """
    Holds the run until a person resumes it, through the dashboard or the run-control API and optionally with data,
    or until its timeout passes.
    """

    type: Literal["pause_workflow"] = Field(
        default="pause_workflow", description="Type of the node. Must be 'pause_workflow'"
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            "Why the run waits for a person, shown with the paused run and sent with its webhook event. May use "
            "{{dynamic}} and [[runtime]] variables, filled in when the node runs, such as 'Approve the refund of "
            "[[amount]]'."
        ),
        title="Reason",
    )
    timeout_seconds: Optional[int] = Field(
        default=None,
        ge=1,
        le=MAX_WAITING_SECONDS,
        description=(
            "How long to wait for a person, in seconds, up to 30 days. When it passes, the node finishes as timed "
            "out, which counts as a failure. Leave empty to wait until someone resumes the run; a run paused for 30 "
            "days is cancelled."
        ),
        title="Timeout (seconds)",
    )
    notify: bool = Field(
        default=True,
        description=(
            "Send the workflow_run_paused webhook event when the run pauses here, even while another branch still "
            "waits on a timer, a signal or a job."
        ),
        title="Notify",
    )
    output_runtime_variable_name: Optional[str] = Field(
        default="pause_result",
        description=(
            "Base name for the variables this node writes: '<name>' (the data the person resumed it with), "
            "'<name>_resumed_by', '<name>_note', '<name>_data', '<name>_timed_out', '<name>_success', and "
            "'<name>_error' when it timed out or could not pause."
        ),
        title="Output Variable Name",
    )


class PauseWorkflowNodeRunInput(BaseNodeRunInput):
    type: Literal["pause_workflow"] = Field(
        default="pause_workflow", description="Discriminator field which must always be 'pause_workflow'"
    )


class PauseWorkflowNodeRunOutput(BaseControlNodeRunOutput):
    type: Literal["pause_workflow"] = Field(
        default="pause_workflow", description="Discriminator field which must always be 'pause_workflow'"
    )
