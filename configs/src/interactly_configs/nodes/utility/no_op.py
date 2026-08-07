"""No-op utility node — runs and succeeds without doing anything else."""

from typing import Literal, Optional

from pydantic import Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
)


class NoOpNodeConfig(BaseNodeConfig):
    """
    A node that runs and succeeds without doing anything else.

    Use it as a placeholder for an unbuilt step, as a fan-in junction so several
    branches can converge on a single outgoing edge, or as a deterministic
    zero-cost stand-in in tests.

    This is not the same as setting ``disabled=True``. A disabled node is skipped
    entirely and emits no events at all, so downstream conditional edges have
    nothing to branch on. A no-op node runs: it emits the usual start/end node
    events and writes a success flag to the thread state.
    """

    type: Literal["no_op"] = Field(
        default="no_op",
        description="Type of the node. Must be 'no_op'",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.SYSTEM.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.UTILITY.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    note: Optional[str] = Field(
        default=None,
        description=(
            "Free-text note explaining why this placeholder is here "
            "(e.g. 'TODO: replace with the eligibility check'). Never read at runtime."
        ),
        title="Note",
    )
    output_runtime_variable_name: Optional[str] = Field(
        default="no_op_result",
        description=(
            "Base name for the runtime variables written by this node. "
            "'<name>' is set to None and '<name>_success' is set to the run outcome, "
            "so conditional edges can branch on this node."
        ),
        title="Output Variable Name",
    )
    delay_seconds: Optional[float] = Field(
        default=0.0,
        description=(
            "Testing only. Number of seconds to wait before finishing, used to simulate a slow node. "
            "Leave at 0 for a real placeholder."
        ),
        title="Delay Seconds",
    )
    simulate_failure: bool = Field(
        default=False,
        description=(
            "Testing only. When true the node still completes normally but reports success=False, "
            "so failure branches can be exercised without a real failing integration. "
            "The workflow is never aborted by this flag."
        ),
        title="Simulate Failure",
    )


class NoOpNodeRunInput(BaseNodeRunInput):
    type: Literal["no_op"] = Field(
        default="no_op",
        description="Discriminator field which must always be 'no_op'",
    )


class NoOpNodeRunOutput(BaseNodeRunOutput):
    type: Literal["no_op"] = Field(
        default="no_op",
        description="Discriminator field which must always be 'no_op'",
    )
    success: bool = Field(
        default=False,
        description="Indicates whether the node completed successfully",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message, only set when simulate_failure is enabled",
    )
