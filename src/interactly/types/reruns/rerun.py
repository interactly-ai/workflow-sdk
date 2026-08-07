"""
Response models for the workflow-run re-run endpoints.

A re-run replays a finished run from one of its turns, optionally against a *different* workflow or
version. How much of the original run's state survives that move is the central question, and it is
what most of these models describe:

* ``RerunMode`` — how much fidelity the target config can support.
* ``RerunPreflightResponse`` — what a re-run *would* carry and drop, with no side effects.
* ``RerunTokenPreviewResponse`` — what a minted token actually restores, for display.

Every field is optional or defaulted, so a server that grows a field does not break an older client.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field

from interactly._models import BaseAPIModel

__all__ = [
    "CarriesOver",
    "DroppedSummary",
    "HistoryMode",
    "NodeMatch",
    "NodeMatchKind",
    "RerunMode",
    "RerunPreflightResponse",
    "RerunStartedResponse",
    "RerunTokenPreviewResponse",
    "RerunTokenResponse",
    "RerunnableTurnsResponse",
    "TurnRerunnability",
]


class RerunMode(str, Enum):
    """How much of the source run's state the target config can preserve.

    Ordered by strictness: ``PORTABLE`` < ``REMAPPED`` < ``EXACT``. Passing one as
    ``requested_mode`` insists on a minimum — if the target cannot support it the server refuses with
    a report rather than silently doing something lossier.
    """

    #: Same config as the source run: every node id and variable carries over untouched.
    EXACT = "EXACT"
    #: A different config whose nodes the analyzer could match (by id, name, or an explicit map).
    REMAPPED = "REMAPPED"
    #: No usable node correspondence: variables and transcript carry over, position does not.
    PORTABLE = "PORTABLE"


class HistoryMode(str, Enum):
    """How much of the source conversation to carry into the re-run."""

    #: Everything, including system messages. Right for a same-config replay.
    FULL = "FULL"
    #: Drop system and tool messages. The default when the config differs, because the target's own
    #: nodes inject their own system prompts and a stale one actively misleads them.
    USER_AND_ASSISTANT_ONLY = "USER_AND_ASSISTANT_ONLY"
    #: Variables only, no transcript — "same facts, fresh conversation".
    NONE = "NONE"


class NodeMatchKind(str, Enum):
    """How a source node was matched to a target node."""

    #: Same logical id on both sides.
    IDENTITY = "identity"
    #: Matched by node name.
    NAME = "name"
    #: Supplied by the caller's ``node_id_map``.
    EXPLICIT = "explicit"


class TurnRerunnability(BaseAPIModel):
    """Whether one turn can be re-run, and how often it already has been."""

    turn_index: int
    rerunnable: bool = False
    #: Why this turn cannot be re-run. Suitable as a disabled control's tooltip.
    reason: Optional[str] = None
    #: How many runs have already been started from this turn.
    rerun_count: int = 0


class RerunnableTurnsResponse(BaseAPIModel):
    """Which turns of a run can be re-run at all."""

    workflow_run_id: Optional[str] = None
    turns: List[TurnRerunnability] = Field(default_factory=list)


class CarriesOver(BaseAPIModel):
    """How much state a re-run would preserve."""

    message_count: int = 0
    variable_count: int = 0


class DroppedSummary(BaseAPIModel):
    """What a re-run would leave behind, named rather than merely counted."""

    node_ids: List[str] = Field(default_factory=list)
    variable_keys: List[str] = Field(default_factory=list)
    state_keys: List[str] = Field(default_factory=list)


class NodeMatch(BaseAPIModel):
    """One source-node → target-node correspondence found by the compatibility analyzer."""

    source_node_logical_id: Optional[str] = None
    target_node_logical_id: Optional[str] = None
    matched_by: Optional[NodeMatchKind] = None
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None


class RerunPreflightResponse(BaseAPIModel):
    """What a re-run would do, computed without any side effects.

    Worth calling before ``execute`` or ``create_token`` whenever the target is a different workflow
    or version: ``dropped`` and ``unmapped_node_ids`` say concretely what would be lost.
    """

    rerunnable: bool = False
    reason: Optional[str] = None
    resolved_mode: Optional[RerunMode] = None
    is_resumable: bool = True
    not_resumable_reason: Optional[str] = None
    entry_node_logical_id: Optional[str] = None
    suggested_entry_nodes: List[str] = Field(default_factory=list)
    node_matches: List[NodeMatch] = Field(default_factory=list)
    unmapped_node_ids: List[str] = Field(default_factory=list)
    unmapped_variable_keys: List[str] = Field(default_factory=list)
    carries_over: CarriesOver = Field(default_factory=CarriesOver)
    dropped: DroppedSummary = Field(default_factory=DroppedSummary)
    warnings: List[str] = Field(default_factory=list)


class RerunTokenResponse(BaseAPIModel):
    """A minted re-run token plus where it came from.

    The token is a credential: it is what authorises starting the re-run over the WebSocket. Treat it
    like one — it goes in the ``start`` frame, not in logs.
    """

    rerun_token: str
    expires_in_seconds: Optional[int] = None
    target_workflow_id: Optional[str] = None
    target_version_number: Optional[int] = None
    resolved_mode: Optional[RerunMode] = None
    entry_node_logical_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    source_workflow_run_id: Optional[str] = None
    turn_index: Optional[int] = None
    restored_message_count: int = 0


class RerunTokenPreviewResponse(BaseAPIModel):
    """What a re-run token restores, for display.

    Deliberately does **not** echo the token back — the caller already holds it, and repeating a
    credential in a response body invites it into logs the request line alone would not reach.
    """

    source_workflow_run_id: Optional[str] = None
    turn_index: Optional[int] = None
    target_workflow_id: Optional[str] = None
    target_version_number: Optional[int] = None

    #: How much state the target config could preserve. Unaffected by editing.
    resolved_mode: Optional[RerunMode] = None
    #: What to display: ``EDITED`` once someone has changed the projection, else ``resolved_mode``.
    effective_mode: Optional[str] = None
    #: Whether a human has changed this projection since it was issued. A run started from an edited
    #: projection is a hypothetical, not a replay.
    edited: bool = False
    #: How many displayed turns were removed. Stored because a removal, unlike an append, leaves
    #: nothing behind in the transcript to count.
    removed_message_count: int = 0

    entry_node_logical_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

    #: Which thread the re-run continues. The others are restored but not resumable — companions are
    #: non-interactive and terminate within their turn.
    resume_thread_id: Optional[str] = None
    #: Per-thread restored conversation and runtime variables.
    threads: List[Dict[str, Any]] = Field(default_factory=list)
    #: Resolved at issue time; the client may override these when starting the run.
    dynamic_variables: Dict[str, Any] = Field(default_factory=dict)
    #: Read from the token store rather than computed, so it stays honest about eviction. ``None``
    #: when there is no expiry or no key — neither is a duration to count down from.
    expires_in_seconds: Optional[int] = None


class RerunStartedResponse(BaseAPIModel):
    """202 body for an asynchronous re-run — the run exists and execution is under way."""

    workflow_run_id: Optional[str] = None
    status: Optional[str] = None
    resolved_mode: Optional[RerunMode] = None
    entry_node_logical_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
