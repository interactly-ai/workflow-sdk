"""Run input base model and workflow command enum.

The concrete ``WorkflowRunInput`` lives in ``interactly_configs.workflow_run``
(which the package re-exports); this module only provides the shared
``BaseRunInput`` and ``WorkflowCommand``.
"""

from enum import Enum

from pydantic import BaseModel, Field


class WorkflowCommand(str, Enum):
    """Commands that can be sent to the workflow execution endpoint."""

    START = "start"
    DATA = "data"
    RESUME = "resume"
    PAUSE = "pause"
    STOP = "stop"


class BaseRunInput(BaseModel):
    """Base class for run input to workflows or individual nodes."""

    dynamic_variables: dict = Field(
        default_factory=dict,
        description=(
            "Dynamic variable values that will replace the '{{...}}' placeholders "
            "in prompts, condition strings, tool signatures, etc."
        ),
        title="Dynamic Variables",
    )
    runtime_variables: dict = Field(
        default_factory=dict,
        description=(
            "Runtime variables that will replace the '[[...]]' placeholders "
            "in prompts, condition strings, tool signatures, etc."
        ),
        title="Runtime Variables",
    )
    miscellaneous: dict = Field(
        default_factory=dict,
        description="Miscellaneous run-input data",
        title="Miscellaneous Run Input Data",
    )
