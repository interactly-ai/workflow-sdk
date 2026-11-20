"""
Types for pausing a workflow thread durably and resuming it later.

A thread can already park in two ways: waiting for a user message (busy-waiting), or paused by its node. This
module describes the durable kind of pause: what wake condition a pause waits for, what the runtime records
about it on the thread, and what a resume carries back in.

* A **wake condition** says what ends a pause: a person (``manual``), a user's resume of a whole run
  (``run_pause``), external jobs finishing (``external_job``), a time (``timer``) or a named signal
  (``signal``).
* A **pause record** is stored on the paused thread, in ``thread_state.miscellaneous["pause"]``, as a plain
  dict. Keeping the stored form a dict means state snapshots, pickles and checkpoints never hold a class that
  a reader on an older image could not load.
* A **resume input** (``ResumeRunInput``) is a node run input built by the server to resume one paused node.
  Clients may never send one; the run entry points refuse it (``carries_resume_input``).
* A node whose config mixes in ``PausableNodeConfig`` declares that it can pause its thread, which limits where
  a workflow may place it (``node_can_pause``).

Models only, with no runtime imports, so every layer can import them.
"""

import hashlib
import hmac
import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, SecretStr, model_validator

from interactly_configs.nodes.external_job import ExternalJobOutcome
from interactly_configs.nodes.node import BaseNodeRunInput

# Where a thread's pause record lives in its ``ThreadState.miscellaneous``.
#: The furthest a pause's deadline may be from when it is registered: 30 days. A waiting run counts toward its team's
#: concurrency limit and is never reaped as stale, so this is the longest one wait can hold a slot. Upstream defines it
#: beside the pause port (``agentic_workflow_framework/ports/pauses.py``), outside the mirrored paths; the node configs
#: that bound their durations by it import it from here.
MAX_WAITING_SECONDS = 30 * 24 * 60 * 60

PAUSE_RECORD_KEY = "pause"

# Where a thread counts the pauses it has taken, in its ``ThreadState.miscellaneous``: pauses of the run and pauses its
# nodes take alike. The count is part of each pause key (``run_pause_key``, ``node_pause_key``), so two pauses of one
# thread from the same revision never share a key. The name predates node pauses and is kept for stored states.
RUN_PAUSE_SEQUENCE_KEY = "run_pause_sequence"

# What a run entry point answers when a client sends a resume input.
CLIENT_RESUME_INPUT_REJECTED = "Resume inputs are issued by the server and cannot be supplied by a client"

# What a signal key may be. A signal is posted to a URL path that ends in its key, and a wait names the key it waits
# for, so the signal route and the Wait for signal node apply the one rule.
SIGNAL_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,128}")

# ``SIGNAL_KEY_PATTERN`` in words, for the messages that refuse a key.
SIGNAL_KEY_RULE = "1 to 128 letters, digits, _ . : or -"


class PauseEntry(str, Enum):
    """What happens when a pause ends."""

    #: The node that paused is invoked again, with the resume input. A node's own pause.
    REENTER = "reenter"
    #: The next node is invoked fresh. A run pause taken at a node boundary, after the previous node finished.
    ADVANCE = "advance"


class ResumeReason(str, Enum):
    """Why a pause ended."""

    WOKEN = "woken"
    TIMED_OUT = "timed_out"
    RESUMED_BY_USER = "resumed_by_user"


class WakeKind(str, Enum):
    """The kinds of wake condition, matching the ``kind`` discriminator of ``WakeCondition``."""

    MANUAL = "manual"
    RUN_PAUSE = "run_pause"
    EXTERNAL_JOB = "external_job"
    TIMER = "timer"
    SIGNAL = "signal"


class ManualWake(BaseModel):
    """Woken by a person resuming it, from the API, the dashboard or a live session."""

    kind: Literal["manual"] = "manual"
    reason: Optional[str] = Field(default=None, description="Why the node asked a person to resume it")
    notify: bool = Field(
        default=True, description="Whether the run's paused webhook event announces this pause; a node may opt out"
    )


class RunPauseWake(BaseModel):
    """A user paused the whole run; woken only by a user resuming the run."""

    kind: Literal["run_pause"] = "run_pause"


class ExternalJobWake(BaseModel):
    """Woken when the named external jobs are terminal: all of them, or the first one."""

    kind: Literal["external_job"] = "external_job"
    job_ids: List[str] = Field(min_length=1, description="The jobs this pause waits for")
    mode: Literal["all", "any"] = Field(default="all", description="Wake when all jobs end, or when any one does")


class TimerWake(BaseModel):
    """Woken at a fixed time."""

    kind: Literal["timer"] = "timer"
    wake_at: datetime = Field(description="When to wake")


class SignalWake(BaseModel):
    """Woken when a named signal is posted to the run."""

    kind: Literal["signal"] = "signal"
    signal_key: str = Field(min_length=1, description="The name the signal is posted under")
    payload_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="JSON schema the posted body must satisfy, if any"
    )


WakeCondition = Annotated[
    Union[ManualWake, RunPauseWake, ExternalJobWake, TimerWake, SignalWake],
    Field(discriminator="kind"),
]


class ManualResumePayload(BaseModel):
    """What a person's resume delivers."""

    kind: Literal["manual"] = "manual"
    resumed_by: Optional[str] = Field(default=None, description="Who resumed it")
    note: Optional[str] = Field(default=None, description="An optional note from that person")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Optional data the person supplied")


class TimerFiredPayload(BaseModel):
    """What a timer delivers."""

    kind: Literal["timer_fired"] = "timer_fired"
    fired_at: datetime = Field(description="When the timer fired")


class SignalPayload(BaseModel):
    """What a posted signal delivers."""

    kind: Literal["signal"] = "signal"
    body: Optional[Any] = Field(default=None, description="The posted body")


class ExternalJobOutcomesPayload(BaseModel):
    """What finished external jobs deliver: one outcome per job."""

    kind: Literal["external_job_outcomes"] = "external_job_outcomes"
    outcomes: List[ExternalJobOutcome] = Field(default_factory=list, description="One outcome per job")


ResumePayload = Annotated[
    Union[ManualResumePayload, TimerFiredPayload, SignalPayload, ExternalJobOutcomesPayload],
    Field(discriminator="kind"),
]


class PauseRecord(BaseModel):
    """
    What the runtime records on a thread when it pauses durably.

    Stored as a plain dict (``to_misc``) and read back with ``from_misc``. The resume token itself is never
    stored, only its SHA-256, so a stored run cannot be used to resume the pause.
    """

    pause_id: str = Field(min_length=1, description="Identifies this pause; a resume must name it")
    pause_key: str = Field(
        min_length=1,
        description="Deterministic key for this pause, stable across rebuilds of the same run, for idempotency",
    )
    node_logical_id: str = Field(min_length=1, description="The node the pause belongs to")
    wake: WakeCondition = Field(description="What ends the pause")
    entry: PauseEntry = Field(description="What happens when the pause ends")
    deadline_at: Optional[datetime] = Field(default=None, description="When the pause times out, if ever")
    token_sha256: Optional[str] = Field(
        default=None, description="SHA-256 of the resume token; none for run pauses, which carry no token"
    )
    attempt: int = Field(default=0, ge=0, description="How many times this node has paused again on resume")
    created_at: datetime = Field(description="When the pause was taken")

    def to_misc(self) -> Dict[str, Any]:
        """The stored form: plain JSON-compatible values only."""
        return self.model_dump(mode="json")

    @classmethod
    def from_misc(cls, stored: Optional[Dict[str, Any]]) -> Optional["PauseRecord"]:
        """Read a stored record back; ``None`` when the thread has none."""
        if not stored:
            return None
        return cls.model_validate(stored)


class ResumeRunInput(BaseNodeRunInput):
    """
    The input that resumes one paused node. Built only by the server.

    * ``node_logical_id`` is required. Run inputs are matched to nodes by id, and a run input with no id is
      taken by any node that accepts a non-exact match, so a resume without one could reach a node that has
      nothing to do with the pause.
    * Its own variable bags must be empty. A node's variables are merged from the first run input matched to
      it, so a resume carrying variables could shadow the ones the turn's ordinary input supplies.
    * ``resume_token`` is contained like ``secret_variables``: excluded from ``model_dump``, JSON and ``repr``,
      kept by ``pickle``. A stored or logged resume input therefore can never be replayed.
    """

    type: Literal["resume"] = Field(default="resume", description="Discriminator field which must always be 'resume'")
    node_logical_id: str = Field(min_length=1, description="The paused node this resume is for")
    pause_id: str = Field(min_length=1, description="The pause being resumed")
    resume_token: Optional[SecretStr] = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Proof that the resume was issued for this pause. Never stored, logged or returned.",
    )
    reason: ResumeReason = Field(default=ResumeReason.WOKEN, description="Why the pause ended")
    payload: Optional[ResumePayload] = Field(default=None, description="What the wake delivered, if anything")

    @model_validator(mode="after")
    def _variables_must_be_empty(self) -> "ResumeRunInput":
        populated = [
            name for name in ("dynamic_variables", "runtime_variables", "secret_variables") if getattr(self, name)
        ]
        if populated:
            raise ValueError(f"A resume input carries no variables of its own; got {', '.join(populated)}")
        return self


class PausableNodeConfig:
    """
    Marker mixed into the config of a node that can pause its thread, which limits where a workflow may place it.

    A pause belongs to a thread, so such a node may be neither:

    * on a classic companion edge (its destination or anything after it): a classic companion shares its parent's
      thread and is not a thread of its own, so its pause would have nowhere to be recorded and would be dropped;
    * a self-loop node: a self-loop re-runs the node on its own schedule, which a pause would freeze mid-loop.

    The workflow runtime and the save-time validator both refuse those shapes. A marker rather than a flag, so it
    holds wherever it sits among a config's bases.
    """


def run_pause_key(run_id: Optional[str], thread_id: str, base_revision: Optional[int], sequence: int) -> str:
    """
    The key of a thread's pause for a pause of the whole run: ``run_pause:{run_id}:{thread_id}:{base_revision}:{seq}``.

    Made from durable values only, so rebuilding the same run from the same revision makes the same key, which is what
    lets a store treat a repeated pause as the one it already holds. ``sequence`` is the thread's own count of run
    pauses (``RUN_PAUSE_SEQUENCE_KEY``). A run with no stored id or revision yet, such as one held only in memory,
    leaves that part empty.
    """
    run_part = "" if run_id is None else run_id
    revision_part = "" if base_revision is None else str(base_revision)
    return f"run_pause:{run_part}:{thread_id}:{revision_part}:{sequence}"


def node_pause_key(
    run_id: Optional[str], thread_id: str, node_logical_id: str, base_revision: Optional[int], sequence: int
) -> str:
    """
    The key of a pause a node takes itself: ``node_pause:{run_id}:{thread_id}:{node_logical_id}:{base_revision}:{seq}``.

    Made from durable values only, as ``run_pause_key`` is, so a turn replayed from the same revision makes the same
    key and a pause port hands back the pause it already registered. ``sequence`` is the thread's count of pauses
    (``RUN_PAUSE_SEQUENCE_KEY``), shared with run pauses, so no two pauses of a thread share a number. A node's
    invocation count is never part of it: that starts again whenever the runtime is rebuilt.
    """
    run_part = "" if run_id is None else run_id
    revision_part = "" if base_revision is None else str(base_revision)
    return f"node_pause:{run_part}:{thread_id}:{node_logical_id}:{revision_part}:{sequence}"


def resume_token_sha256(token: str) -> str:
    """The SHA-256 of a resume token, as ``PauseRecord.token_sha256`` stores it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def resume_mismatch(record: PauseRecord, resume: ResumeRunInput) -> Optional[str]:
    """
    Why ``resume`` does not resume the pause ``record`` describes, or ``None`` when it does.

    A resume must name the pause and its node, and, when the pause was registered with a token, carry that token. The
    reason never contains the token, so it is safe to log.
    """
    if resume.pause_id != record.pause_id:
        return f"it names pause {resume.pause_id!r}, but the thread holds pause {record.pause_id!r}"
    if resume.node_logical_id != record.node_logical_id:
        return f"it names node {resume.node_logical_id!r}, but the pause belongs to node {record.node_logical_id!r}"
    if record.token_sha256 is not None:
        token = resume.resume_token.get_secret_value() if resume.resume_token is not None else None
        if not token:
            return "it carries no resume token"
        if not hmac.compare_digest(resume_token_sha256(token), record.token_sha256):
            return "its resume token does not match"
    return None


def is_signal_key(value: str) -> bool:
    """Whether ``value`` may name a signal (``SIGNAL_KEY_PATTERN``)."""
    return SIGNAL_KEY_PATTERN.fullmatch(value) is not None


def node_can_pause(node_config: Any) -> bool:
    """Whether a node config declares that its node can pause its thread (see ``PausableNodeConfig``)."""
    return issubclass(type(node_config), PausableNodeConfig)


def carries_resume_input(workflow_run_input: Any) -> bool:
    """
    Whether a workflow run input holds a resume input for any thread.

    The run entry points use it to refuse resume inputs from clients: only the server resumes a pause. Typed as
    ``Any`` because the run input model is defined in a module that imports this one.
    """
    thread_inputs = getattr(workflow_run_input, "thread_to_node_inputs", None) or {}
    return any(
        isinstance(node_input, ResumeRunInput)
        for nodes_inputs in thread_inputs.values()
        for node_input in (getattr(nodes_inputs, "node_run_inputs", None) or [])
    )
