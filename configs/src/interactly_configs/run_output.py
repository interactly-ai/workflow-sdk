"""Run output model.

Pure-Pydantic, client-safe types for a workflow run's output, including the
``WorkflowExecutionStatus`` enum describing a run's lifecycle state.
"""

from enum import Enum
from typing import Any, List

from pydantic import BaseModel, Field

# ``events`` HOLDS TWO SHAPES, PERMANENTLY. An entry is a typed event model on a live runtime and a
# plain **dict** once it has been through the server's storage, because an untyped list's items are
# never coerced. Both are legitimate.
#
# DO NOT "FIX" THIS BY TYPING IT ``List[Event]``. Validating this field would reject any event type
# the server has that this package does not — which, for a client that necessarily lags the server,
# is the normal case rather than the exceptional one. It would also make ``interactly_configs.events``
# a hard dependency of every run-output model, creating an import cycle (``Event`` embeds
# ``NodeRunOutput``, which inherits ``BaseRunOutput``).

#: One entry of ``BaseRunOutput.events``. Deliberately ``Any`` — see the note above.
StoredEvent = Any

#: The ``events`` field's type. Identical to a bare ``List`` at runtime and in the JSON schema, so
#: naming it costs nothing and reads as intent rather than as an oversight.
StoredEvents = List[StoredEvent]


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

    # Read/write entries defensively; see the module note above for why this is not ``List[Event]``.
    events: StoredEvents = Field(
        default_factory=list,
        description="List of events that occurred during a node or workflow run",
        title="Node/Workflow Run Events",
    )
