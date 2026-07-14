"""Run output model.

Pure-Pydantic, client-safe types for a workflow run's output, including the
``WorkflowExecutionStatus`` enum describing a run's lifecycle state.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class WorkflowExecutionStatus(str, Enum):
    """
    Execution status of a workflow run.

    Use ``WorkflowExecutionStatus.is_terminal()`` to check whether the session
    has reached a final state after which no further execution turns should be sent.
    """

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
    def is_terminal(status: "WorkflowExecutionStatus") -> bool:
        """Return ``True`` if *status* is a terminal (non-continuable) state."""
        return status in {
            WorkflowExecutionStatus.COMPLETED,
            WorkflowExecutionStatus.FAILED,
            WorkflowExecutionStatus.CANCELLED,
            WorkflowExecutionStatus.ABORTED_LOOPING_RISK,
        }


class BaseRunOutput(BaseModel):
    """Base class for run output from workflows or individual nodes."""

    events: List = Field(
        default_factory=list,
        description="List of events that occurred during a node or workflow run",
        title="Node/Workflow Run Events",
    )
