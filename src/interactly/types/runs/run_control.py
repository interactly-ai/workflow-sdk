"""
Response models for controlling a durable workflow run: pausing, resuming, cancelling and signalling it, and listing
its pauses, signals and external jobs.

A durable run is a scheduled run, a re-run or a background run: one whose state is stored between turns, so it can
wait on a timer, a signal, an external job or a person, and be paused, resumed or cancelled while it does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from interactly._models import BaseAPIModel

__all__ = ["BackgroundRunStarted", "RunControlResult", "RunExternalJob", "RunPause", "RunSignal", "SignalResult"]


class BackgroundRunStarted(BaseAPIModel):
    """A background run that was started: durable, with no user and no socket. Follow it with ``client.runs.get``."""

    workflow_run_id: str
    #: Its status when it was started (``started``). Its first turn runs after the answer, in the background.
    status: Optional[str] = None


class RunControlResult(BaseAPIModel):
    """What a pause, resume or cancel request did."""

    workflow_run_id: str
    #: ``applied``: the request took effect. ``already_requested``: the same request already stood (a pause or a
    #: cancel), so nothing changed.
    outcome: str
    #: The run's status after the request: ``paused`` once a waiting run is paused, while a working run keeps its
    #: status until it reaches its next node.
    status: Optional[str] = None
    #: For a resume of pauses waiting for a person: the ids of the pauses it made ready.
    made_ready: List[str] = Field(default_factory=list)


class SignalResult(BaseAPIModel):
    """What posting a signal did."""

    workflow_run_id: str
    signal_key: str
    #: ``delivered``: a wait for the key took it. ``stored``: kept for a wait that starts later. ``already_received``:
    #: the same body was already waiting under that key.
    outcome: str
    #: Whether this repeats the answer to an earlier post with the same Idempotency-Key.
    replayed: bool = False


class RunPause(BaseAPIModel):
    """One pause of a run. Resume tokens are never returned."""

    pause_id: str
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    pause_key: Optional[str] = None
    #: What ends the pause, by ``kind``: ``manual`` (a person approves it), ``timer``, ``signal``, ``external_job`` or
    #: ``run_pause`` (a person's pause of the whole run).
    wake: Optional[Dict[str, Any]] = None
    #: What happens to the node when the pause ends.
    entry: Optional[str] = None
    #: ``pending_arm``, ``armed``, ``ready``, ``delivering``, ``delivered``, ``cancelled`` or ``failed``.
    state: Optional[str] = None
    deadline_at: Optional[datetime] = None
    ready_reason: Optional[str] = None
    ready_at: Optional[datetime] = None
    delivery_attempts: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def waits_for_person(self) -> bool:
        """Whether this pause waits for a person to approve it: the ones ``resume(pause_ids=...)`` names."""
        return (self.wake or {}).get("kind") == "manual" and self.state == "armed"


class RunSignal(BaseAPIModel):
    """One signal posted to a run. Its body is never returned: it is the sender's data."""

    signal_id: str
    signal_key: Optional[str] = None
    received_at: Optional[datetime] = None
    #: Whether a wait has taken it, and which (by its pause key).
    consumed: Optional[bool] = None
    consumed_by_pause_key: Optional[str] = None
    #: Why a wait refused it (its body failed the wait's schema), if one did.
    rejected_reason: Optional[str] = None
    idempotency_key: Optional[str] = None


class RunExternalJob(BaseAPIModel):
    """One external job a run started, such as an ECS task."""

    job_id: str
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    job_key: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    cluster: Optional[str] = None
    #: The provider's own reference, such as an ECS task ARN.
    external_ref: Optional[str] = None
    ownership: Optional[str] = None
    state: Optional[str] = None
    last_status: Optional[str] = None
    attempt: Optional[int] = None
    #: How the job ended, once it has.
    outcome: Optional[Dict[str, Any]] = None
    launched_at: Optional[datetime] = None
    max_runtime_seconds: Optional[int] = None
    walltime_deadline_at: Optional[datetime] = None
    stop_requested_at: Optional[datetime] = None
    stop_reason: Optional[str] = None
    stop_timeout_kind: Optional[str] = None
    stop_on_run_end: Optional[bool] = None
    last_observed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
