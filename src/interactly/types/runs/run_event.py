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
                                    workflow will accept the next user message. Sent only
                                    while fork companions run on; ``is_ready_for_input()``
                                    is the "your turn" signal for every workflow
    ``companion_step_boundary``   — one companion self-loop step completed
    ``waiting_evaluation_boundary`` — a parked thread's waiting-edges were evaluated
    ``waiting_condition_matched`` — a conditional edge fired while its source node was
                                    parked, with no user message
    ``self_loop_delay``           — waiting before a bounded self-loop retry
    ``self_loop_exhausted``       — a bounded self-loop hit max_retries / expiry_time
    ``node_expired``              — an in-flight execution was terminated by expiry_time
    ``guardrail_escalation_edge`` — the guardrail-strikes threshold escalated the run
    ``run_paused``                — a person paused the run through the run-control API; carries
                                    ``paused_by``, ``pause_reason``, ``workflow_run_status`` and a
                                    ``message``. The socket stays open, and a message sent while
                                    the run is paused is refused with another ``run_paused`` frame
    ``run_resumed``               — a person's pause of the run was lifted; carries ``resumed_by``
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import PrivateAttr, model_validator

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

    # Set by the stream that read this event, when the turn it ends hands over to the user without the server saying
    # so (no workflow_ready_for_input, as when no fork companion runs). See is_ready_for_input().
    _ends_turn_awaiting_user: bool = PrivateAttr(default=False)

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
        """Return True at the moment the run waits for the user's next message: the time to ``send()`` it.

        It fires once per turn that hands over to the user. The server says so with ``workflow_ready_for_input`` only
        while fork companions run on in the background. Without them it sends nothing of the kind, so a stream marks
        the turn's last event instead (its ``end_workflow_iteration``) when the turn left a main thread waiting for a
        message, and marks a take-back's acknowledgement when the run it took back waits for its user. An event read
        outside a stream answers by its type alone.

        Distinct from :meth:`is_terminal` and from ``end_workflow_iteration``. Once companion
        threads are in play the three diverge: an iteration marker is per-turn accounting,
        ``end_workflow`` is true completion of every thread, and this is the moment the main thread
        is parked and waiting. Loops that break on ``end_workflow_iteration`` will hang or race when
        a companion is still emitting.
        """
        return self.type == "workflow_ready_for_input" or self._ends_turn_awaiting_user

    def is_run_paused(self) -> bool:
        """Return True when a person paused the run, or refused a message because the run is paused.

        Not terminal: the socket stays open and the run carries on once resumed (``client.runs.resume``), at which
        point a ``run_resumed`` event arrives. Seen only on a server where streamed runs are durable.
        """
        return self.type == "run_paused"

    def is_run_resumed(self) -> bool:
        """Return True when a person's pause of the run was lifted and the run carries on."""
        return self.type == "run_resumed"
