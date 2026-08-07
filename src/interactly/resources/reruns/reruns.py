"""
RerunsResource — re-run a finished workflow run from one of its turns.

Endpoints implemented:
    GET    /v1/workflow-runs/{id}/rerunnable-turns                     → rerunnable_turns
    POST   /v1/workflow-runs/{id}/turns/{turn}/rerun-preflight         → preflight
    POST   /v1/workflow-runs/{id}/turns/{turn}/rerun-token             → create_token
    GET    /v1/workflow-runs/{id}/turns/{turn}/rerun-token/{token}     → preview_token
    PATCH  /v1/workflow-runs/{id}/turns/{turn}/rerun-token/{token}     → amend_token
    POST   /v1/workflow-runs/{id}/turns/{turn}/rerun                   → execute

These replace the removed ``POST /v1/workflows/{id}/runs/{run_id}/checkpoint-run``, which could only
ever replay against the source run's own stored config — the ``EXACT`` case of what happens here.

Two ways to run
---------------
**Execute** — the server runs it and hands back the new run. Use this when you just want the result::

    started = client.reruns.execute(run_id, turn_index=3, message="try this instead")

**Token** — mint a projection, optionally edit it, then start it over the WebSocket. Use this when a
human should see and adjust what carries over before anything runs::

    token = client.reruns.create_token(run_id, turn_index=3)
    client.reruns.amend_token(run_id, 3, token.rerun_token,
                              message_edits=[{"thread_id": "0", "index": 2, "text": "..."}])
    with client.runs.stream(workflow_id=wf_id, rerun_token=token.rerun_token) as stream:
        ...

Both build their state through the same server-side projection, so they cannot disagree about what
carries over.

Call ``preflight`` first whenever the target is a *different* workflow or version — it reports what
would be dropped, with no side effects.

Two preconditions, both enforced server-side and both easy to trip
------------------------------------------------------------------
**1. The run must have a stored config snapshot.** Re-running reconstructs state against the config
the run actually used, so the server needs that config saved on the run. It is written only by the
**WebSocket** driver (``client.runs.stream(...)``). A run driven through the REST
``client.runs.execute(...)`` path carries no snapshot, and every one of its turns reports
``rerunnable=False`` with *"This run predates workflow config snapshots, so its state cannot be
reconstructed."* — the same message older runs get, which makes the cause easy to misread as age.
Check ``rerunnable_turns`` before offering a re-run in a UI.

**2. Feedback needs a finished run.** Ratings and comments on a run still in progress are refused
with HTTP 409 (*"Feedback cannot be left while the run is still in progress"*). Re-run itself is
turn-scoped and does not require the run to be terminal, but the same runs are usually being reviewed
after the fact, so both constraints tend to show up together.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr, is_given
from interactly.types.reruns.rerun import (
    RerunnableTurnsResponse,
    RerunPreflightResponse,
    RerunStartedResponse,
    RerunTokenPreviewResponse,
    RerunTokenResponse,
)

__all__ = ["RerunsResource", "AsyncRerunsResource"]

_PATH = "/v1/workflow-runs"


def _turn_path(workflow_run_id: str, turn_index: int) -> str:
    return f"{_PATH}/{workflow_run_id}/turns/{turn_index}"


def _target_body(
    *,
    target_workflow_id: NotGivenOr[Optional[str]],
    target_version_number: NotGivenOr[Optional[int]],
    history_mode: NotGivenOr[Optional[str]],
    entry_node_logical_id: NotGivenOr[Optional[str]],
    node_id_map: NotGivenOr[Optional[Dict[str, str]]],
    requested_mode: NotGivenOr[Optional[str]],
) -> Dict[str, Any]:
    """Build a ``RerunTargetRequest`` body, omitting anything the caller did not supply.

    Omission matters: the server derives sensible defaults (the source run's own workflow, the
    target's active version, a history mode chosen from how far the configs diverged), and sending an
    explicit ``null`` is not the same as leaving it out.
    """
    body: Dict[str, Any] = {}
    if is_given(target_workflow_id):
        body["target_workflow_id"] = target_workflow_id
    if is_given(target_version_number):
        body["target_version_number"] = target_version_number
    if is_given(history_mode):
        body["history_mode"] = getattr(history_mode, "value", history_mode)
    if is_given(entry_node_logical_id):
        body["entry_node_logical_id"] = entry_node_logical_id
    if is_given(node_id_map):
        body["node_id_map"] = node_id_map
    if is_given(requested_mode):
        body["requested_mode"] = getattr(requested_mode, "value", requested_mode)
    return body


def _amend_body(
    *,
    dynamic_variables: NotGivenOr[Optional[Dict[str, Any]]],
    runtime_variables: NotGivenOr[Optional[Dict[str, Dict[str, Any]]]],
    message_edits: NotGivenOr[Optional[Any]],
    message_appends: NotGivenOr[Optional[Any]],
    message_deletes: NotGivenOr[Optional[Any]],
) -> Dict[str, Any]:
    """Build a ``RerunAmendRequest`` body containing only the verbs the caller used.

    The server sets ``extra="forbid"`` on this body, so sending a key it does not recognise is a hard
    error rather than a silent no-op — which is the right trade when the alternative is telling
    someone their edit was accepted and then behaving as though it never happened.
    """
    body: Dict[str, Any] = {}
    if is_given(dynamic_variables):
        body["dynamic_variables"] = dynamic_variables
    if is_given(runtime_variables):
        body["runtime_variables"] = runtime_variables
    if is_given(message_edits):
        body["message_edits"] = message_edits
    if is_given(message_appends):
        body["message_appends"] = message_appends
    if is_given(message_deletes):
        body["message_deletes"] = message_deletes
    return body


class RerunsResource(SyncAPIResource):
    """Synchronous interface to the workflow-run re-run API."""

    def rerunnable_turns(self, workflow_run_id: str) -> RerunnableTurnsResponse:
        """List which turns of a run can be re-run, and how often each already has been."""
        return self._client.get(
            f"{_PATH}/{workflow_run_id}/rerunnable-turns", cast_to=RerunnableTurnsResponse
        )

    def preflight(
        self,
        workflow_run_id: str,
        turn_index: int,
        *,
        target_workflow_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        target_version_number: NotGivenOr[Optional[int]] = NOT_GIVEN,
        history_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
        entry_node_logical_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        node_id_map: NotGivenOr[Optional[Dict[str, str]]] = NOT_GIVEN,
        requested_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> RerunPreflightResponse:
        """Report what a re-run would carry over and drop. No side effects.

        Worth calling before ``execute`` or ``create_token`` whenever the target is a different
        workflow or version.
        """
        body = _target_body(
            target_workflow_id=target_workflow_id,
            target_version_number=target_version_number,
            history_mode=history_mode,
            entry_node_logical_id=entry_node_logical_id,
            node_id_map=node_id_map,
            requested_mode=requested_mode,
        )
        return self._client.post(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-preflight",
            body=body,
            cast_to=RerunPreflightResponse,
        )

    def create_token(
        self,
        workflow_run_id: str,
        turn_index: int,
        *,
        target_workflow_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        target_version_number: NotGivenOr[Optional[int]] = NOT_GIVEN,
        history_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
        entry_node_logical_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        node_id_map: NotGivenOr[Optional[Dict[str, str]]] = NOT_GIVEN,
        requested_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> RerunTokenResponse:
        """Mint a re-run token carrying the projected state.

        The returned ``rerun_token`` is a credential: pass it to ``client.runs.stream(...)`` to start
        the re-run. It expires, so mint it when you are ready to use it.
        """
        body = _target_body(
            target_workflow_id=target_workflow_id,
            target_version_number=target_version_number,
            history_mode=history_mode,
            entry_node_logical_id=entry_node_logical_id,
            node_id_map=node_id_map,
            requested_mode=requested_mode,
        )
        return self._client.post(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-token",
            body=body,
            cast_to=RerunTokenResponse,
        )

    def preview_token(
        self, workflow_run_id: str, turn_index: int, rerun_token: str
    ) -> RerunTokenPreviewResponse:
        """Show what a token restores — threads, transcript and variables — without starting it."""
        return self._client.get(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-token/{rerun_token}",
            cast_to=RerunTokenPreviewResponse,
        )

    def amend_token(
        self,
        workflow_run_id: str,
        turn_index: int,
        rerun_token: str,
        *,
        dynamic_variables: NotGivenOr[Optional[Dict[str, Any]]] = NOT_GIVEN,
        runtime_variables: NotGivenOr[Optional[Dict[str, Dict[str, Any]]]] = NOT_GIVEN,
        message_edits: NotGivenOr[Optional[Any]] = NOT_GIVEN,
        message_appends: NotGivenOr[Optional[Any]] = NOT_GIVEN,
        message_deletes: NotGivenOr[Optional[Any]] = NOT_GIVEN,
    ) -> RerunTokenPreviewResponse:
        """Edit a projection before it runs, returning the updated preview.

        Indexes address the *displayed* transcript from ``preview_token`` and are all resolved
        against the list as it stood before any edit, so a multi-part amendment is not
        order-dependent. Any amendment marks the projection ``edited``, and a run started from an
        edited projection is reported as ``EDITED`` rather than as a replay.
        """
        body = _amend_body(
            dynamic_variables=dynamic_variables,
            runtime_variables=runtime_variables,
            message_edits=message_edits,
            message_appends=message_appends,
            message_deletes=message_deletes,
        )
        return self._client.patch(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-token/{rerun_token}",
            body=body,
            cast_to=RerunTokenPreviewResponse,
        )

    def execute(
        self,
        workflow_run_id: str,
        turn_index: int,
        *,
        message: NotGivenOr[Optional[str]] = NOT_GIVEN,
        run_async: bool = True,
        target_workflow_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        target_version_number: NotGivenOr[Optional[int]] = NOT_GIVEN,
        history_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
        entry_node_logical_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        node_id_map: NotGivenOr[Optional[Dict[str, str]]] = NOT_GIVEN,
        requested_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> RerunStartedResponse:
        """Re-run a turn server-side and hand back the new run.

        Args:
            message: Optional user message to drive the new run with. **Omit it** to restore the
                conversation and leave it parked awaiting input — the safe default, because
                re-entering the restored node would repeat whatever it already did (a tool node's API
                write, an outbound notification). Supply it to replay the turn against the new config.
            run_async: Execute in the background and answer 202 immediately (the default). A re-run
                onto a different config can take longer than a request may live.
        """
        body = _target_body(
            target_workflow_id=target_workflow_id,
            target_version_number=target_version_number,
            history_mode=history_mode,
            entry_node_logical_id=entry_node_logical_id,
            node_id_map=node_id_map,
            requested_mode=requested_mode,
        )
        if is_given(message):
            body["message"] = message
        return self._client.post(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun",
            body=body,
            params={"async": run_async},
            cast_to=RerunStartedResponse,
        )


class AsyncRerunsResource(AsyncAPIResource):
    """Asynchronous interface to the workflow-run re-run API. Mirrors :class:`RerunsResource`."""

    async def rerunnable_turns(self, workflow_run_id: str) -> RerunnableTurnsResponse:
        """List which turns of a run can be re-run, and how often each already has been."""
        return await self._client.get(
            f"{_PATH}/{workflow_run_id}/rerunnable-turns", cast_to=RerunnableTurnsResponse
        )

    async def preflight(
        self,
        workflow_run_id: str,
        turn_index: int,
        *,
        target_workflow_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        target_version_number: NotGivenOr[Optional[int]] = NOT_GIVEN,
        history_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
        entry_node_logical_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        node_id_map: NotGivenOr[Optional[Dict[str, str]]] = NOT_GIVEN,
        requested_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> RerunPreflightResponse:
        """Report what a re-run would carry over and drop. No side effects."""
        body = _target_body(
            target_workflow_id=target_workflow_id,
            target_version_number=target_version_number,
            history_mode=history_mode,
            entry_node_logical_id=entry_node_logical_id,
            node_id_map=node_id_map,
            requested_mode=requested_mode,
        )
        return await self._client.post(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-preflight",
            body=body,
            cast_to=RerunPreflightResponse,
        )

    async def create_token(
        self,
        workflow_run_id: str,
        turn_index: int,
        *,
        target_workflow_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        target_version_number: NotGivenOr[Optional[int]] = NOT_GIVEN,
        history_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
        entry_node_logical_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        node_id_map: NotGivenOr[Optional[Dict[str, str]]] = NOT_GIVEN,
        requested_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> RerunTokenResponse:
        """Mint a re-run token carrying the projected state."""
        body = _target_body(
            target_workflow_id=target_workflow_id,
            target_version_number=target_version_number,
            history_mode=history_mode,
            entry_node_logical_id=entry_node_logical_id,
            node_id_map=node_id_map,
            requested_mode=requested_mode,
        )
        return await self._client.post(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-token",
            body=body,
            cast_to=RerunTokenResponse,
        )

    async def preview_token(
        self, workflow_run_id: str, turn_index: int, rerun_token: str
    ) -> RerunTokenPreviewResponse:
        """Show what a token restores, without starting it."""
        return await self._client.get(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-token/{rerun_token}",
            cast_to=RerunTokenPreviewResponse,
        )

    async def amend_token(
        self,
        workflow_run_id: str,
        turn_index: int,
        rerun_token: str,
        *,
        dynamic_variables: NotGivenOr[Optional[Dict[str, Any]]] = NOT_GIVEN,
        runtime_variables: NotGivenOr[Optional[Dict[str, Dict[str, Any]]]] = NOT_GIVEN,
        message_edits: NotGivenOr[Optional[Any]] = NOT_GIVEN,
        message_appends: NotGivenOr[Optional[Any]] = NOT_GIVEN,
        message_deletes: NotGivenOr[Optional[Any]] = NOT_GIVEN,
    ) -> RerunTokenPreviewResponse:
        """Edit a projection before it runs, returning the updated preview."""
        body = _amend_body(
            dynamic_variables=dynamic_variables,
            runtime_variables=runtime_variables,
            message_edits=message_edits,
            message_appends=message_appends,
            message_deletes=message_deletes,
        )
        return await self._client.patch(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun-token/{rerun_token}",
            body=body,
            cast_to=RerunTokenPreviewResponse,
        )

    async def execute(
        self,
        workflow_run_id: str,
        turn_index: int,
        *,
        message: NotGivenOr[Optional[str]] = NOT_GIVEN,
        run_async: bool = True,
        target_workflow_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        target_version_number: NotGivenOr[Optional[int]] = NOT_GIVEN,
        history_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
        entry_node_logical_id: NotGivenOr[Optional[str]] = NOT_GIVEN,
        node_id_map: NotGivenOr[Optional[Dict[str, str]]] = NOT_GIVEN,
        requested_mode: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> RerunStartedResponse:
        """Re-run a turn server-side and hand back the new run."""
        body = _target_body(
            target_workflow_id=target_workflow_id,
            target_version_number=target_version_number,
            history_mode=history_mode,
            entry_node_logical_id=entry_node_logical_id,
            node_id_map=node_id_map,
            requested_mode=requested_mode,
        )
        if is_given(message):
            body["message"] = message
        return await self._client.post(
            f"{_turn_path(workflow_run_id, turn_index)}/rerun",
            body=body,
            params={"async": run_async},
            cast_to=RerunStartedResponse,
        )
