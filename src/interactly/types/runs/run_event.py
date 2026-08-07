"""
Event model for WebSocket streaming events from the workflow run endpoint.

The server streams newline-delimited JSON events. Each event has a ``type``
field and optional payload fields depending on the event type.

Known event types (non-exhaustive — the server may add new types):
    ``start_workflow``            — the run began executing
    ``end_workflow``              — the run finished (terminal)
    ``end_workflow_iteration``    — one workflow iteration completed
    ``workflow_error``            — the run terminated with an error (terminal)
    ``conditional_edge``          — a conditional edge transition was taken
    ``reverse_conditional_edge``  — a global node returned control back to its
                                    caller node (non-terminal navigation event;
                                    carries ``global_node_logical_id``)
    ``workflow_ready_for_input``  — every non-companion thread has settled and the
                                    workflow will accept the next user message. This,
                                    NOT ``end_workflow_iteration``, is the "your turn"
                                    signal once companion threads are in play
    ``companion_step_boundary``   — one companion self-loop step completed
    ``waiting_evaluation_boundary`` — a parked thread's waiting-edges were evaluated
    ``waiting_condition_matched`` — a conditional edge fired while its source node was
                                    parked, with no user message
    ``self_loop_delay``           — waiting before a bounded self-loop retry
    ``self_loop_exhausted``       — a bounded self-loop hit max_retries / expiry_time
    ``node_expired``              — an in-flight execution was terminated by expiry_time
    ``guardrail_escalation_edge`` — the guardrail-strikes threshold escalated the run
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["RunEvent"]


class RunEvent(BaseAPIModel):
    """
    A single streaming event emitted by the workflow run WebSocket.

    Unknown event types are accepted (``extra="allow"`` from BaseAPIModel)
    so new server event types do not break the SDK.
    """

    # The event type identifier (e.g. "start_workflow", "end_workflow").
    type: str

    # Logical ID of the graph node this event relates to (if applicable).
    node_id: Optional[str] = None

    # For ``reverse_conditional_edge`` events: the logical ID of the global node
    # that triggered the reverse navigation back to its caller node.
    global_node_logical_id: Optional[str] = None

    # For LLM events: the text output or streamed token.
    output: Optional[Any] = None

    # Run-level status after this event.
    status: Optional[str] = None

    # Error message for failure events.
    error: Optional[str] = None

    # Additional arbitrary payload from the server.
    data: Optional[Dict[str, Any]] = None

    # Author-facing display id for the event's thread: ``"0"`` for the main thread, or a fork
    # companion's configured ``thread_id``. Derived server-side from the internal
    # ``"<parent>_companion_<id>"``, so it is the id to show a user and to match against a
    # ``[[thread_<id>.<var>]]`` reference.
    thread_reference_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # The initial handshake frame acknowledges the run but carries a
        # ``message`` rather than a ``type``; give it a synthetic type so it
        # validates and callers can format ``event.type`` uniformly.
        if not data.get("type"):
            data["type"] = "run_ack"
        # The server's rich event frames key the node by ``origin_node_logical_id``
        # and the assistant text by ``content``; surface them under the SDK's
        # ``node_id`` / ``output`` fields when not already present.
        if data.get("node_id") is None and data.get("origin_node_logical_id") is not None:
            data["node_id"] = data["origin_node_logical_id"]
        if data.get("output") is None and data.get("content") is not None:
            data["output"] = data["content"]
        return data

    def is_terminal(self) -> bool:
        """
        Return True if this event signals the end of the run.

        Terminal types: ``end_workflow`` (successful completion) and
        ``workflow_error`` (error termination). Navigation events such as
        ``conditional_edge`` and ``reverse_conditional_edge`` are explicitly
        *not* terminal.

        Note that ``end_workflow`` now means **all** threads have ended, companions included. To
        detect "the workflow wants my next message", use :meth:`is_ready_for_input`.
        """
        return self.type in {"end_workflow", "workflow_error"}

    def is_ready_for_input(self) -> bool:
        """Return True when the workflow will accept the next user message.

        Distinct from :meth:`is_terminal` and from ``end_workflow_iteration``. Once companion
        threads are in play the three diverge: an iteration marker is per-turn accounting,
        ``end_workflow`` is true completion of every thread, and this is the moment the main thread
        is parked and waiting. Loops that break on ``end_workflow_iteration`` will hang or race when
        a companion is still emitting.
        """
        return self.type == "workflow_ready_for_input"
