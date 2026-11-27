"""
Shared enumerations used across multiple resource types.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["WorkflowStatus", "WorkflowCommand", "RunStatus"]


class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow definition."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class WorkflowCommand(str, Enum):
    """Commands that can be sent to the workflow execution endpoint."""

    START = "start"
    DATA = "data"
    RESUME = "resume"
    PAUSE = "pause"
    STOP = "stop"


class RunStatus(str, Enum):
    """Execution status of a workflow run."""

    NOT_STARTED = "not_started"
    STARTED = "started"
    RUNNING = "running"
    PAUSED = "paused"
    #: A durable run parked between turns until a timer, a signal or an external job wakes it. A run waiting for a
    #: person to approve it is PAUSED instead.
    WAITING = "waiting"
    WAITING_FOR_USER_INPUT = "waiting_for_user_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABORTED_LOOPING_RISK = "aborted_looping_risk"
