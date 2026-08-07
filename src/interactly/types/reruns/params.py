"""
Request parameter TypedDicts for the re-run endpoints.

The amend payload is a **description of a change**, never state. A client says which thread and which
key; the server does the writing. That is what keeps editing inside the invariant the WebSocket
enforces — a client must never be the source of run state — and it is why there is no "send me the
whole projection back" shape here.

The server rejects unknown keys on the amend body (``extra="forbid"``), so a typo fails loudly rather
than being silently ignored and leaving the user believing an edit was applied.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from typing_extensions import Literal, NotRequired, TypedDict

__all__ = [
    "RerunAmendParams",
    "RerunExecuteParams",
    "RerunMessageAppend",
    "RerunMessageDelete",
    "RerunMessageEdit",
    "RerunTargetParams",
]


class RerunTargetParams(TypedDict):
    """Where a re-run should execute, and how much state it should try to carry.

    ``turn_index`` is deliberately absent — it lives in the path, matching the turn rating and
    comment endpoints so every turn-scoped operation addresses a turn the same way.
    """

    #: Workflow to re-run against. Defaults to the source run's own workflow.
    target_workflow_id: NotRequired[Optional[str]]
    #: Version to re-run against. Defaults to the target workflow's active version.
    target_version_number: NotRequired[Optional[int]]
    #: How much of the source conversation to carry over. Defaults to ``FULL`` when the target config
    #: is identical to the source's and ``USER_AND_ASSISTANT_ONLY`` otherwise.
    history_mode: NotRequired[Optional[str]]
    #: Node to start from. Required in practice only for ``PORTABLE`` re-runs, where no restored
    #: position survives.
    entry_node_logical_id: NotRequired[Optional[str]]
    #: Explicit source-node → target-node mapping for nodes the analyzer could not match on its own.
    #: Overrides automatic matching.
    node_id_map: NotRequired[Optional[Dict[str, str]]]
    #: Insist on a minimum fidelity. If the target cannot support it the request is refused with a
    #: report rather than silently doing something lossier.
    requested_mode: NotRequired[Optional[str]]


class RerunExecuteParams(RerunTargetParams):
    """A re-run the server executes itself, rather than handing back to an editor."""

    #: Optional user message to drive the new run with. Omit it to restore the conversation and leave
    #: it parked awaiting input — the safe default, because re-entering the restored node would
    #: repeat whatever it already did (a tool node's API write, an outbound notification).
    message: NotRequired[Optional[str]]


class RerunMessageEdit(TypedDict):
    """New text for a turn that already exists.

    No role and no id: a client can change what a turn *says*, never who said it or which message it
    is. Rewriting authorship of a record of what happened is not on offer.
    """

    #: Internal thread id, as returned by ``preview_token``.
    thread_id: str
    #: Position in the thread's *displayed* transcript, as returned by ``preview_token`` — not an
    #: index into stored state. System prompts and tool traffic are not displayed but still occupy
    #: positions in storage, so the server resolves this through the same filter that produced it.
    index: int
    #: Replacement text. Cannot be blank; removing a turn is a separate verb.
    text: str


class RerunMessageAppend(TypedDict):
    """A new turn at the end of a thread.

    **No position, deliberately.** With no positional argument there is no positional validation, and
    landing between a tool call and the result answering it becomes impossible to ask for.
    """

    thread_id: str
    #: An added assistant turn is content the model will read back as its own prior output, for a
    #: conversation that did not happen — which is the point, and why the resulting run is labelled
    #: ``EDITED`` rather than a replay.
    role: Literal["user", "assistant"]
    text: str


class RerunMessageDelete(TypedDict):
    """Removal of a turn that already exists.

    Carries a consequence the client cannot see: the server also removes the tool results that
    answered that turn. Tool traffic is never displayed, so a client could not name those messages
    and could not tell whether they were left behind.
    """

    thread_id: str
    #: Resolved against the transcript as it stands *before* any removal, so several deletes in one
    #: request all address the list the caller was shown.
    index: int


class RerunAmendParams(TypedDict):
    """A change to an already-issued re-run projection.

    All indexes are resolved against the transcript as it stands before any of the edits is applied,
    so a multi-part amendment is not order-dependent.
    """

    #: Variable name → value, replacing by key on the projection itself. Distinct from sending
    #: ``dynamic_variables`` when starting a run, which merges on top for that one run; editing here
    #: is durable and visible to the next preview.
    dynamic_variables: NotRequired[Optional[Dict[str, Any]]]
    #: Internal thread id → {variable name: value}. Keyed by thread because each thread has its own
    #: runtime variables and a companion's are not the main thread's.
    runtime_variables: NotRequired[Optional[Dict[str, Dict[str, Any]]]]
    message_edits: NotRequired[Optional[List[RerunMessageEdit]]]
    message_appends: NotRequired[Optional[List[RerunMessageAppend]]]
    message_deletes: NotRequired[Optional[List[RerunMessageDelete]]]
