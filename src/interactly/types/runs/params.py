"""
Request parameter TypedDicts for workflow run endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from typing_extensions import NotRequired, TypedDict

from interactly.types.shared import WorkflowCommand

__all__ = ["RunListParams", "RunStreamParams", "RunCommentParams", "RunExecuteParams"]


class RunListParams(TypedDict):
    """Query parameters for ``client.runs.list()``."""

    workflow_id: NotRequired[Optional[str]]
    status: NotRequired[Optional[str]]
    run_by: NotRequired[Optional[str]]
    start: NotRequired[Optional[datetime]]
    end: NotRequired[Optional[datetime]]
    page: NotRequired[int]
    size: NotRequired[int]
    search: NotRequired[Optional[str]]
    #: Only runs re-run FROM this run.
    source_workflow_run_id: NotRequired[Optional[str]]
    #: Narrows the above to one turn; ignored without it.
    source_turn_index: NotRequired[Optional[int]]


class RunStreamParams(TypedDict):
    """
    Payload sent over the WebSocket to initiate a workflow run.

    Maps directly to the ``WorkflowRunInput`` schema expected by the server.
    """

    workflow_id: str
    command: WorkflowCommand
    # Identifies the caller — use "api" for programmatic runs.
    run_by: NotRequired[str]
    # If omitted the server uses the currently active version.
    version_number: NotRequired[Optional[int]]
    #: Redeems a re-run projection minted by ``client.reruns.create_token``. Only valid on a
    #: ``start`` frame; an expired or mismatched token closes the socket with code 4007.
    rerun_token: NotRequired[Optional[str]]


class RunCommentParams(TypedDict):
    """Body for ``client.runs.add_comment()``."""

    content: str


class RunExecuteParams(TypedDict):
    """
    Body for a single turn of ``client.runs.execute()``.

    First turn — omit ``run_id``.
    Subsequent turns — echo the ``run_id`` returned in the previous response.
    Cancel — echo ``run_id`` and set ``command = "stop"``.
    """

    run_id: NotRequired[Optional[str]]
    command: NotRequired[str]  # WorkflowCommand value; defaults to "start"
    run_by: NotRequired[Optional[str]]
    version_number: NotRequired[Optional[int]]
    dynamic_variables: NotRequired[Dict[str, Any]]
    runtime_variables: NotRequired[Dict[str, Any]]
    miscellaneous: NotRequired[Dict[str, Any]]
