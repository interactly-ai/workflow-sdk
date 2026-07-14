"""
RunsResource — operations on Workflow Run resources.

Endpoints implemented:
    GET    /v1/workflow-runs/schema                            → schema
    GET    /v1/workflow-runs                                   → list (paginated)
    GET    /v1/workflow-runs/{id}                              → get
    DELETE /v1/workflow-runs/{id}                              → delete
    GET    /v1/workflow-runs/{id}/evaluation-result            → evaluation_result
    POST   /v1/workflow-runs/{id}/comments                     → add_comment
    DELETE /v1/workflow-runs/{id}/comments/{logical_id}        → delete_comment
    POST   /v1/workflow-runs/{id}/events/{event_id}/comments   → add_event_comment
    DELETE /v1/workflow-runs/{id}/events/{event_id}/comments/{comment_id} → delete_event_comment
    WS     /v1/workflow-runs/ws                                → stream (context manager)
    POST   /v1/workflows/{id}/execute  (turn 1: new session)  → execute (run_id=None)
    POST   /v1/workflows/{id}/execute  (turn N: resume)       → execute (run_id=<echo>)
    POST   /v1/workflows/{id}/runs/{run_id}/checkpoint-run     → checkpoint
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._streaming import AsyncStream, Stream
from interactly._utils._serialise import serialise_config
from interactly.types.runs.interactive_run import InteractiveRunResponse
from interactly.types.runs.params import RunListParams
from interactly.types.runs.run import Run, RunComment, RunEvaluationResult
from interactly.types.runs.run_event import RunEvent
from interactly.types.shared import WorkflowCommand

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from interactly.configs import WorkflowRunInput  # type: ignore[import]

__all__ = ["RunsResource", "AsyncRunsResource"]

_PATH = "/v1/workflow-runs"
_WS_PATH = "/v1/workflow-runs/ws"


class RunsResource(SyncAPIResource):
    """
    Synchronous interface to the Workflow Runs API.

    Usage::

        # Streaming run (synchronous):
        with client.runs.stream(workflow_id="abc", command=WorkflowCommand.START) as run_stream:
            for event in run_stream:
                print(event.type, event.output)
                if event.is_terminal():
                    break

        # Listing past runs:
        page = client.runs.list(workflow_id="abc", size=50)
        for run in page:
            print(run.id, run.status)
    """

    # ---------------------------------------------------------------------- #
    # Streaming                                                                #
    # ---------------------------------------------------------------------- #

    def stream(
        self,
        *,
        workflow_id: str,
        command: WorkflowCommand = WorkflowCommand.START,
        run_by: str = "api",
        version_number: Optional[int] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        runtime_variables: Optional[Dict[str, Any]] = None,
        run_input: Optional["WorkflowRunInput"] = None,
        cast_to: Type[RunEvent] = RunEvent,
    ) -> Stream[RunEvent]:
        """
        Open a WebSocket connection and stream workflow run events.

        Returns a context manager that yields ``RunEvent`` objects.

        Args:
            workflow_id:       The workflow to run.
            command:           Command to send (default: ``WorkflowCommand.START``).
            run_by:            Identifier for the caller (default: ``"api"``).
            version_number:    Specific version to run (default: active version).
            dynamic_variables: Optional ``{{...}}`` placeholder values sent with the run.
            runtime_variables: Optional ``[[...]]`` placeholder values sent with the run.
            run_input:         Optional typed ``WorkflowRunInput`` (preferred). Its fields
                               (including ``dynamic_variables`` / ``runtime_variables`` /
                               ``thread_to_node_inputs``) are merged into the WS payload,
                               which the server validates as a full ``WorkflowRunInput``.
            cast_to:           Pydantic model to parse each event into.

        Example::

            with client.runs.stream(workflow_id="abc") as events:
                for event in events:
                    print(event)
        """
        ws_base = self._client._ws_base_url()
        ws_url = f"{ws_base}{_WS_PATH}"
        # The gateway authenticates WS upgrades via a single-use ``?token=``
        # session; mint one up front (falls back to header auth when absent).
        token = self._client._mint_ws_session_token()
        if token:
            ws_url = f"{ws_url}?token={token}"
        payload = _build_stream_payload(
            workflow_id=workflow_id,
            command=command,
            run_by=run_by,
            version_number=version_number,
            dynamic_variables=dynamic_variables,
            runtime_variables=runtime_variables,
            run_input=run_input,
        )

        return Stream(
            ws_url=ws_url,
            ws_headers=self._client.ws_headers(),
            payload=payload,
            cast_to=cast_to,
        )

    # ---------------------------------------------------------------------- #
    # REST operations                                                          #
    # ---------------------------------------------------------------------- #

    def list(
        self,
        *,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
    ) -> SyncPage[Run]:
        """List workflow runs with optional filtering (paginated)."""
        params: dict[str, Any] = {"page": page, "size": size}
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        if status is not None:
            params["status"] = status
        if start is not None:
            params["start"] = start.isoformat()
        if end is not None:
            params["end"] = end.isoformat()
        if search is not None:
            params["search"] = search

        raw = self._client.get(_PATH, params=params, cast_to=dict)

        def fetch_page(p: int) -> SyncPage[Run]:
            return self.list(
                workflow_id=workflow_id,
                status=status,
                start=start,
                end=end,
                page=p,
                size=size,
                search=search,
            )

        return SyncPage._from_response(raw, Run, fetch_page)

    def get(self, run_id: str) -> Run:
        """Retrieve a single run by ID."""
        return self._client.get(f"{_PATH}/{run_id}", cast_to=Run)

    def delete(self, run_id: str) -> None:
        """Delete a run record."""
        self._client.delete(f"{_PATH}/{run_id}", cast_to=type(None))

    def evaluation_result(self, run_id: str) -> RunEvaluationResult:
        """Retrieve the evaluation result for a run."""
        return self._client.get(f"{_PATH}/{run_id}/evaluation-result", cast_to=RunEvaluationResult)

    def add_comment(self, run_id: str, *, content: str) -> RunComment:
        """Add a comment to a run."""
        return self._client.post(
            f"{_PATH}/{run_id}/comments",
            body={"content": content},
            cast_to=RunComment,
        )

    def delete_comment(self, run_id: str, comment_logical_id: str) -> None:
        """Delete a comment from a run."""
        self._client.delete(
            f"{_PATH}/{run_id}/comments/{comment_logical_id}",
            cast_to=type(None),
        )

    def add_event_comment(self, run_id: str, event_logical_id: str, *, content: str) -> RunComment:
        """Add a comment to a specific event within a run.

        Args:
            run_id:            ObjectId of the run.
            event_logical_id:  Logical ID of the event (from the run's
                               ``input_output_pairs[].run_output.events[]`` list).
            content:           Text content for the comment.

        Returns:
            The newly created :class:`RunComment`.

        Raises:
            NotFoundError: If the run or event does not exist.
        """
        return self._client.post(
            f"{_PATH}/{run_id}/events/{event_logical_id}/comments",
            body={"content": content},
            cast_to=RunComment,
        )

    def delete_event_comment(
        self, run_id: str, event_logical_id: str, comment_logical_id: str
    ) -> None:
        """Delete a comment from a specific event within a run.

        Args:
            run_id:              ObjectId of the run.
            event_logical_id:    Logical ID of the event that owns the comment.
            comment_logical_id:  Logical ID of the comment to remove.

        Raises:
            NotFoundError: If the run, event, or comment does not exist.
        """
        self._client.delete(
            f"{_PATH}/{run_id}/events/{event_logical_id}/comments/{comment_logical_id}",
            cast_to=type(None),
        )

    def schema(self) -> Dict[str, Any]:
        """Return the JSON schemas for workflow run structures.

        Returns a dict with four keys:
        - ``run_schema`` — schema for the top-level WorkflowRun object
        - ``run_input_schema`` — schema for WorkflowRunInput
        - ``run_output_schema`` — schema for WorkflowRunOutput
        - ``run_input_output_pair_schema`` — schema for WorkflowRunInputOutputPair

        Useful for dynamic form generation and documentation tooling.
        """
        return self._client.get(f"{_PATH}/schema", cast_to=dict)

    # ---------------------------------------------------------------------- #
    # Execution                                                                #
    # ---------------------------------------------------------------------- #

    def execute(
        self,
        workflow_id: str,
        *,
        run_id: Optional[str] = None,
        command: "WorkflowCommand | str" = "start",
        run_by: Optional[str] = None,
        version_number: Optional[int] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        runtime_variables: Optional[Dict[str, Any]] = None,
        miscellaneous: Optional[Dict[str, Any]] = None,
        run_input: Optional["WorkflowRunInput"] = None,
    ) -> InteractiveRunResponse:
        """
        Execute one turn of an interactive workflow session.

        First turn — omit ``run_id``; the server creates a new session and returns
        ``run_id`` in the response.  Echo that ``run_id`` on every subsequent call
        until ``is_completed`` is ``True``.

        Args:
            workflow_id:       ObjectId of the workflow to run.
            run_id:            Session identifier.  Absent on first turn; echoed on all
                               subsequent turns.  Pass the value from the previous response.
            command:           Workflow command. Accepts the typed ``WorkflowCommand`` enum
                               (preferred) or an equivalent string (default ``"start"``;
                               use ``"stop"`` to cancel).
            run_by:            Identifier for the caller (e.g. username).
            version_number:    Specific version to run (defaults to active version).
            dynamic_variables: Key-value pairs replacing ``{{...}}`` placeholders in prompts.
            runtime_variables: Key-value pairs replacing ``[[...]]`` placeholders.
            miscellaneous:     Arbitrary extra data forwarded to the runtime.
            run_input:         Optional typed ``WorkflowRunInput`` (preferred). When given,
                               it is forwarded whole and the loose ``dynamic_variables`` /
                               ``runtime_variables`` / ``miscellaneous`` / ``command`` /
                               ``run_by`` / ``version_number`` kwargs must not be set.

        Returns:
            :class:`InteractiveRunResponse` — inspect ``is_waiting_for_input`` and
            ``is_completed`` to decide whether to continue sending turns.
        """
        body = _build_execute_body(
            run_id=run_id,
            command=command,
            run_by=run_by,
            version_number=version_number,
            dynamic_variables=dynamic_variables,
            runtime_variables=runtime_variables,
            miscellaneous=miscellaneous,
            run_input=run_input,
        )
        return self._client.post(
            f"/v1/workflows/{workflow_id}/execute",
            body=body,
            cast_to=InteractiveRunResponse,
        )

    def execute_with_input(
        self,
        workflow_id: str,
        *,
        run_input: "WorkflowRunInput",
        run_id: Optional[str] = None,
    ) -> InteractiveRunResponse:
        """Execute one turn using a typed ``WorkflowRunInput`` payload.

        Unlike :meth:`execute`, this method forwards the full ``WorkflowRunInput``
        (including ``thread_to_node_inputs``) to the backend.  This is the
        transport used by :class:`WorkflowHandle` for multi-turn interactive
        runs that need to inject per-thread node inputs (LLM messages, etc.).

        Args:
            workflow_id: ObjectId of the workflow to run.
            run_input:   Typed ``WorkflowRunInput`` from ``interactly.configs``.
            run_id:      Session identifier; omit on the first turn, then echo
                         the value returned in the response.

        Returns:
            :class:`InteractiveRunResponse`.
        """
        body: Dict[str, Any] = {"run_input": serialise_config(run_input)}
        if run_id is not None:
            body["run_id"] = run_id
        return self._client.post(
            f"/v1/workflows/{workflow_id}/execute",
            body=body,
            cast_to=InteractiveRunResponse,
        )

    def checkpoint(
        self,
        workflow_id: str,
        run_id: str,
        *,
        resume_turn_index: int,
        start_node_logical_id: Optional[str] = None,
    ) -> Run:
        """
        Trigger a new run branching from a checkpoint of an existing run.

        Copies conversation pairs from the source run up to and including
        ``resume_turn_index``, then continues execution from that point
        (optionally from a specific node).  Useful for replaying or
        branching conversations.

        Args:
            workflow_id:           ObjectId of the workflow.
            run_id:                ObjectId of the source run.
            resume_turn_index:     0-based index of the turn to resume from.
                                   The new run inherits all pairs up to this
                                   index and then continues execution.
            start_node_logical_id: Optional logical ID of the node to start
                                   execution from, bypassing the default
                                   start node.

        Returns:
            The newly created :class:`Run` record (status ``started``).

        Raises:
            NotFoundError:      If the source run does not exist.
            BadRequestError:    If ``resume_turn_index`` is out of range or
                                the source run has no stored workflow config.
        """
        body: Dict[str, Any] = {"resume_turn_index": resume_turn_index}
        if start_node_logical_id is not None:
            body["start_node_logical_id"] = start_node_logical_id
        return self._client.post(
            f"/v1/workflows/{workflow_id}/runs/{run_id}/checkpoint-run",
            body=body,
            cast_to=Run,
        )


class AsyncRunsResource(AsyncAPIResource):
    """
    Async interface to the Workflow Runs API.  All methods are coroutines except
    ``stream()`` which returns an async context manager.

    Usage::

        async with client.runs.stream(workflow_id="abc") as events:
            async for event in events:
                print(event.type, event.output)
    """

    def stream(
        self,
        *,
        workflow_id: str,
        command: WorkflowCommand = WorkflowCommand.START,
        run_by: str = "api",
        version_number: Optional[int] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        runtime_variables: Optional[Dict[str, Any]] = None,
        run_input: Optional["WorkflowRunInput"] = None,
        cast_to: Type[RunEvent] = RunEvent,
    ) -> AsyncStream[RunEvent]:
        """
        Open an async WebSocket connection and stream workflow run events.

        Returns an async context manager that yields ``RunEvent`` objects.
        Accepts optional ``dynamic_variables`` / ``runtime_variables`` or a full
        typed ``run_input`` (preferred); see :meth:`RunsResource.stream`.
        """
        ws_base = self._client._ws_base_url()
        ws_url = f"{ws_base}{_WS_PATH}"
        payload = _build_stream_payload(
            workflow_id=workflow_id,
            command=command,
            run_by=run_by,
            version_number=version_number,
            dynamic_variables=dynamic_variables,
            runtime_variables=runtime_variables,
            run_input=run_input,
        )

        return AsyncStream(
            ws_url=ws_url,
            ws_headers=self._client.ws_headers(),
            payload=payload,
            cast_to=cast_to,
            token_provider=self._client._mint_ws_session_token,
        )

    async def list(
        self,
        *,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
    ) -> AsyncPage[Run]:
        params: dict[str, Any] = {"page": page, "size": size}
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        if status is not None:
            params["status"] = status
        if start is not None:
            params["start"] = start.isoformat()
        if end is not None:
            params["end"] = end.isoformat()
        if search is not None:
            params["search"] = search

        raw = await self._client.get(_PATH, params=params, cast_to=dict)

        async def fetch_page(p: int) -> AsyncPage[Run]:
            return await self.list(
                workflow_id=workflow_id,
                status=status,
                start=start,
                end=end,
                page=p,
                size=size,
                search=search,
            )

        return AsyncPage._from_response(raw, Run, fetch_page)

    async def get(self, run_id: str) -> Run:
        return await self._client.get(f"{_PATH}/{run_id}", cast_to=Run)

    async def delete(self, run_id: str) -> None:
        await self._client.delete(f"{_PATH}/{run_id}", cast_to=type(None))

    async def evaluation_result(self, run_id: str) -> RunEvaluationResult:
        return await self._client.get(f"{_PATH}/{run_id}/evaluation-result", cast_to=RunEvaluationResult)

    async def add_comment(self, run_id: str, *, content: str) -> RunComment:
        return await self._client.post(
            f"{_PATH}/{run_id}/comments",
            body={"content": content},
            cast_to=RunComment,
        )

    async def delete_comment(self, run_id: str, comment_logical_id: str) -> None:
        await self._client.delete(
            f"{_PATH}/{run_id}/comments/{comment_logical_id}",
            cast_to=type(None),
        )

    async def add_event_comment(self, run_id: str, event_logical_id: str, *, content: str) -> RunComment:
        """Add a comment to a specific event within a run."""
        return await self._client.post(
            f"{_PATH}/{run_id}/events/{event_logical_id}/comments",
            body={"content": content},
            cast_to=RunComment,
        )

    async def delete_event_comment(
        self, run_id: str, event_logical_id: str, comment_logical_id: str
    ) -> None:
        """Delete a comment from a specific event within a run."""
        await self._client.delete(
            f"{_PATH}/{run_id}/events/{event_logical_id}/comments/{comment_logical_id}",
            cast_to=type(None),
        )

    async def schema(self) -> Dict[str, Any]:
        """Return the JSON schemas for workflow run structures."""
        return await self._client.get(f"{_PATH}/schema", cast_to=dict)

    async def execute(
        self,
        workflow_id: str,
        *,
        run_id: Optional[str] = None,
        command: "WorkflowCommand | str" = "start",
        run_by: Optional[str] = None,
        version_number: Optional[int] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        runtime_variables: Optional[Dict[str, Any]] = None,
        miscellaneous: Optional[Dict[str, Any]] = None,
        run_input: Optional["WorkflowRunInput"] = None,
    ) -> InteractiveRunResponse:
        """Execute one turn of an interactive workflow session (async).

        Accepts the typed ``WorkflowCommand`` enum (preferred) or a string for
        ``command``, and an optional typed ``run_input`` (mutually exclusive with
        the loose kwargs). See :meth:`RunsResource.execute`.
        """
        body = _build_execute_body(
            run_id=run_id,
            command=command,
            run_by=run_by,
            version_number=version_number,
            dynamic_variables=dynamic_variables,
            runtime_variables=runtime_variables,
            miscellaneous=miscellaneous,
            run_input=run_input,
        )
        return await self._client.post(
            f"/v1/workflows/{workflow_id}/execute",
            body=body,
            cast_to=InteractiveRunResponse,
        )

    async def execute_with_input(
        self,
        workflow_id: str,
        *,
        run_input: "WorkflowRunInput",
        run_id: Optional[str] = None,
    ) -> InteractiveRunResponse:
        """Async variant of :meth:`RunsResource.execute_with_input`."""
        body: Dict[str, Any] = {"run_input": serialise_config(run_input)}
        if run_id is not None:
            body["run_id"] = run_id
        return await self._client.post(
            f"/v1/workflows/{workflow_id}/execute",
            body=body,
            cast_to=InteractiveRunResponse,
        )

    async def checkpoint(
        self,
        workflow_id: str,
        run_id: str,
        *,
        resume_turn_index: int,
        start_node_logical_id: Optional[str] = None,
    ) -> Run:
        """Trigger a new run branching from a checkpoint of an existing run."""
        body: Dict[str, Any] = {"resume_turn_index": resume_turn_index}
        if start_node_logical_id is not None:
            body["start_node_logical_id"] = start_node_logical_id
        return await self._client.post(
            f"/v1/workflows/{workflow_id}/runs/{run_id}/checkpoint-run",
            body=body,
            cast_to=Run,
        )


# --------------------------------------------------------------------------- #
# Module-private helpers                                                       #
# --------------------------------------------------------------------------- #


def _build_stream_payload(
    *,
    workflow_id: str,
    command: WorkflowCommand,
    run_by: str,
    version_number: Optional[int],
    dynamic_variables: Optional[Dict[str, Any]],
    runtime_variables: Optional[Dict[str, Any]],
    run_input: Optional["WorkflowRunInput"],
) -> Dict[str, Any]:
    """Build the WebSocket handshake payload for ``/workflow-runs/ws``.

    The server validates each message as a full ``WorkflowRunInput``, so a typed
    ``run_input`` (preferred) is serialised and used as the base; the loose
    ``dynamic_variables`` / ``runtime_variables`` are layered on top when given.
    When nothing extra is supplied this reduces to today's minimal payload.
    """
    if run_input is not None:
        payload: Dict[str, Any] = dict(serialise_config(run_input))
    else:
        # Seed the default thread so a bare command still produces a valid run
        # (the server rejects inputs with "Found 0 threads").
        payload = {"thread_to_node_inputs": {"0": {"node_run_inputs": []}}}

    payload["workflow_id"] = workflow_id
    payload.setdefault("command", command.value if isinstance(command, WorkflowCommand) else command)
    payload.setdefault("run_by", run_by)
    if version_number is not None:
        payload["version_number"] = version_number
    if dynamic_variables is not None:
        payload["dynamic_variables"] = dynamic_variables
    if runtime_variables is not None:
        payload["runtime_variables"] = runtime_variables
    return payload


def _build_execute_body(
    *,
    run_id: Optional[str],
    command: "WorkflowCommand | str",
    run_by: Optional[str],
    version_number: Optional[int],
    dynamic_variables: Optional[Dict[str, Any]],
    runtime_variables: Optional[Dict[str, Any]],
    miscellaneous: Optional[Dict[str, Any]],
    run_input: Optional["WorkflowRunInput"],
) -> Dict[str, Any]:
    """Build the POST body for ``/execute``, preferring a typed ``run_input``.

    Two mutually-exclusive modes:

    * **Typed** — when ``run_input`` is given, it is serialised and forwarded
      whole; the loose ``command`` / ``run_by`` / ``version_number`` /
      ``dynamic_variables`` / ``runtime_variables`` / ``miscellaneous`` kwargs
      must be left at their defaults.
    * **Loose kwargs** — the backwards-compatible dict path. ``command`` accepts
      the ``WorkflowCommand`` enum (preferred) or a string.
    """
    if run_input is not None:
        _loose_given = any(
            value not in (None, "start")
            for value in (run_by, version_number, dynamic_variables, runtime_variables, miscellaneous)
        ) or command not in ("start", WorkflowCommand.START)
        if _loose_given:
            raise ValueError(
                "Pass either a typed `run_input` or the loose kwargs "
                "(command/run_by/version_number/dynamic_variables/runtime_variables/miscellaneous), not both."
            )
        body: Dict[str, Any] = {"run_input": serialise_config(run_input)}
        if run_id is not None:
            body["run_id"] = run_id
        return body

    command_value = command.value if isinstance(command, WorkflowCommand) else command
    loose_input: Dict[str, Any] = {
        "command": command_value,
        "dynamic_variables": dynamic_variables or {},
        "runtime_variables": runtime_variables or {},
        "miscellaneous": miscellaneous or {},
        # The runtime enters the workflow through a thread, so a bare command
        # (e.g. START with no per-turn inputs) must still seed the default
        # thread "0"; otherwise the server rejects the run with
        # "Found 0 threads in workflow input".
        "thread_to_node_inputs": {"0": {"node_run_inputs": []}},
    }
    if run_by is not None:
        loose_input["run_by"] = run_by
    if version_number is not None:
        loose_input["version_number"] = version_number

    body = {"run_input": loose_input}
    if run_id is not None:
        body["run_id"] = run_id
    return body
