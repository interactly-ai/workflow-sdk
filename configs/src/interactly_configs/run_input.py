"""Run input base model and workflow command enum.

The concrete ``WorkflowRunInput`` lives in ``interactly_configs.workflow_run``
(which the package re-exports); this module only provides the shared
``BaseRunInput``.
"""


from pydantic import BaseModel, Field


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
