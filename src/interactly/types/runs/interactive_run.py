"""
Response model for the interactive turn-by-turn REST execution endpoint.

POST /v1/workflows/{workflow_id}/execute
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._models import BaseAPIModel

__all__ = ["InteractiveRunResponse"]


class InteractiveRunResponse(BaseAPIModel):
    """
    Returned for every POST to ``/v1/workflows/{id}/execute``, both first-turn
    (new session) and subsequent turns (resume).

    Workflow::

        # Turn 1 — new session (omit run_id in request)
        response = client.runs.execute("wf-abc")
        run_id = response.run_id  # echo this on every subsequent call

        # Turn N — resume
        while response.is_waiting_for_input and not response.is_completed:
            user_input = input("You: ")
            response = client.runs.execute(
                "wf-abc",
                run_id=run_id,
                dynamic_variables={"user_message": user_input},
            )

        # Cancel at any time
        client.runs.execute("wf-abc", run_id=run_id, command="stop")
    """

    # Session identifier — ObjectId of the underlying WorkflowRunsModel doc.
    # Echo this on every subsequent turn.
    run_id: str

    # Run-execution status after this turn.
    # Maps to the server's WorkflowStatus enum; see WorkflowExecutionStatus in
    # interactly-configs for the full enum with terminal-state helpers.
    status: str

    # 1-indexed counter of how many execution turns have been completed.
    turn_number: int

    # All events emitted by the workflow runtime during this turn, as raw dicts.
    # For typed access, pass each dict to ``interactly.runtime.events.parse_event``
    # (requires the ``[configs]`` extra), e.g.::
    #     from interactly.runtime.events import parse_event
    #     typed = [parse_event(e) for e in response.events]
    events: List[Dict[str, Any]]

    # True  → the workflow is paused waiting for a user message; send another POST.
    # False → nothing is expected right now (may be running or completed).
    is_waiting_for_input: bool

    # True → the session has reached a terminal state; do not send further POSTs.
    is_completed: bool

    # Present when status == "failed"; contains an error description.
    error: Optional[str] = None

    # BusyWaitForUserMessageEvent payload populated when is_waiting_for_input=True.
    # Provides a hint about what kind of input the workflow expects next.
    next_input_hint: Optional[Dict[str, Any]] = None
