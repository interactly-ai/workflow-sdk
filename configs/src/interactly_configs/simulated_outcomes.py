"""
What a node that would wait returns in a simulation, in place of waiting.

The Wait, Pause workflow, Wait for signal and ECS nodes need a durable pause, which a simulation can't hold, so in a
simulation they finish with an error the workflow routes on and do nothing. A workflow that uses one could therefore not
be simulated end to end. A simulation's config may give such a node an outcome; the node then finishes with it, as if
its wait had ended that way, without waiting and without doing its work (no ECS task is launched, no timer is set).

Kept apart from ``configs/simulation.py``, which imports the runtime's events, so the runtime's execution profile can
carry these without importing the runtime back.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SimulatedOutcomeKind(str, Enum):
    """How the simulated wait ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class SimulatedNodeOutcome(BaseModel):
    """
    The outcome one waiting node finishes with in a simulation.

    The node writes what it writes when its wait really ends that way: a Wait its fire time, a Wait for signal the
    signal's body (``result``) or that it timed out, a Pause workflow the data a person supplied (``result``, an
    object), a Run ECS task its status and exit code. ``result``, ``error`` and ``outputs`` fill or override the rest.
    """

    node_logical_id: str = Field(
        ...,
        min_length=1,
        description="The logical id of the node this outcome is for.",
        title="Node Logical ID",
    )
    outcome: SimulatedOutcomeKind = Field(
        default=SimulatedOutcomeKind.SUCCEEDED,
        description="How the node's wait ends: it succeeded, it failed, or it timed out.",
        title="Outcome",
    )
    result: Optional[Any] = Field(
        default=None,
        description=(
            "The node's result: a signal's body for Wait for signal, the data a person supplied for Pause workflow (an "
            "object), the task summary's fields for Run ECS task. Other nodes write it as their result."
        ),
        title="Result",
    )
    error: Optional[str] = Field(
        default=None,
        description="The error a failed or timed-out node reports. Without one, it says the outcome was simulated.",
        title="Error Message",
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Further variables, named by suffix: 'exit_code' writes the node's output variable followed by "
            "'_exit_code'. They override what the outcome itself writes."
        ),
        title="More Outputs",
    )


def simulated_outcomes_by_node(outcomes: Optional[List[SimulatedNodeOutcome]]) -> Dict[str, SimulatedNodeOutcome]:
    """The outcomes keyed by node logical id. Refuses a node given two, which would leave which one applies to chance."""
    by_node: Dict[str, SimulatedNodeOutcome] = {}
    for outcome in outcomes or []:
        if outcome.node_logical_id in by_node:
            raise ValueError(f"Node {outcome.node_logical_id!r} is given more than one simulated outcome")
        by_node[outcome.node_logical_id] = outcome
    return by_node
