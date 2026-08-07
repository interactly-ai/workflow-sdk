"""Server-side workflow handles.

A :class:`WorkflowHandle` is a tiny client-side object that knows which
workflow on the server you're talking to and remembers the multi-turn
``run_id`` for you between calls.  Build one and drive it turn-by-turn::

    handle = await upload_and_get_handle(client, cfg, dynamic_variables={...})
    async for event in handle.arun(workflow_input):
        ...

All runtime state (turn count, message history, node state) lives on the
server; the handle only persists the ``run_id`` echoed back from the first
turn so subsequent turns resume the same session.
"""

from __future__ import annotations

import asyncio
import copy
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, Iterator, Optional

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from interactly_configs import WorkflowConfigFullyHydrated
    from interactly_configs.workflow_run import WorkflowRunInput

    from interactly._client import AsyncWorkflowClient, WorkflowClient
    from interactly.runtime.events import BaseEvent

__all__ = [
    "AsyncWorkflowHandle",
    "AsyncWorkflowRuntime",
    "WorkflowHandle",
    "WorkflowRuntime",
    "aupload_and_get_handle",
    "upload_and_get_handle",
]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` on top of ``base`` without mutating either.

    ``override`` (caller/per-turn values) wins at the leaf level; ``base``
    (handle defaults) values survive under dicts that ``override`` only
    partially overrides.  Non-dict values are replaced wholesale.
    """
    result = dict(base)
    for key, override_value in override.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            result[key] = _deep_merge(base_value, override_value)
        else:
            result[key] = override_value
    return result


def _merge_dynamic_variables(run_input: "WorkflowRunInput", defaults: Dict[str, Any]) -> "WorkflowRunInput":
    """Return a copy of ``run_input`` with ``defaults`` merged underneath its own ``dynamic_variables``.

    The caller's values take precedence; missing keys are filled in from the
    handle defaults, recursively — a nested dict in ``defaults`` keeps the keys
    the caller did not override.  When ``defaults`` is empty the input is
    returned as-is.  Neither the caller's input nor the handle defaults are
    mutated.
    """
    if not defaults:
        return run_input
    merged = _deep_merge(defaults, run_input.dynamic_variables or {})
    # Use model_copy to avoid mutating the caller's instance.
    return run_input.model_copy(update={"dynamic_variables": merged})


class WorkflowHandle:
    """Synchronous handle to a workflow on the Interactly server.

    A handle is **single-flight**: it tracks one active turn at a time via the
    stored ``run_id``. Do not interleave ``run()`` calls on the same handle from
    multiple threads — start a second concurrent session with a separate handle.
    """

    def __init__(
        self,
        *,
        client: "WorkflowClient",
        workflow_id: str,
        config: "WorkflowConfigFullyHydrated",
        dynamic_variables: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._client = client
        self._workflow_id = workflow_id
        self._config = config
        self._dynamic_variables: Dict[str, Any] = copy.deepcopy(dynamic_variables) if dynamic_variables else {}
        self._run_id: Optional[str] = None

    @property
    def workflow_id(self) -> str:
        return self._workflow_id

    @property
    def config(self) -> "WorkflowConfigFullyHydrated":
        return self._config

    @property
    def run_id(self) -> Optional[str]:
        """The session ID echoed by the server (``None`` until the first ``run`` call)."""
        return self._run_id

    def reset(self) -> None:
        """Forget the current ``run_id`` so the next ``run`` starts a fresh session."""
        self._run_id = None

    def run(self, workflow_input: "WorkflowRunInput") -> Iterator[BaseEvent]:
        """Execute one turn and yield typed events.

        On the first call ``run_id`` is unset and the server creates a new
        session; on subsequent calls the previously returned ``run_id`` is
        echoed back to resume that same session.
        """
        from interactly.runtime.events import parse_event

        merged = _merge_dynamic_variables(workflow_input, self._dynamic_variables)
        response = self._client.runs.execute_with_input(
            self._workflow_id,
            run_input=merged,
            run_id=self._run_id,
        )
        self._run_id = response.run_id
        for raw in response.events:
            yield parse_event(raw)


class AsyncWorkflowHandle:
    """Asynchronous handle to a workflow on the Interactly server."""

    def __init__(
        self,
        *,
        client: "AsyncWorkflowClient",
        workflow_id: str,
        config: "WorkflowConfigFullyHydrated",
        dynamic_variables: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._client = client
        self._workflow_id = workflow_id
        self._config = config
        self._dynamic_variables: Dict[str, Any] = copy.deepcopy(dynamic_variables) if dynamic_variables else {}
        self._run_id: Optional[str] = None
        # Single-flight guard: a second turn must not begin until the first has
        # stored its ``run_id``, otherwise concurrent ``arun`` calls both read
        # ``run_id=None`` and start orphaned server sessions.
        self._turn_lock = asyncio.Lock()

    @property
    def workflow_id(self) -> str:
        return self._workflow_id

    @property
    def config(self) -> "WorkflowConfigFullyHydrated":
        return self._config

    @property
    def run_id(self) -> Optional[str]:
        return self._run_id

    def reset(self) -> None:
        self._run_id = None

    async def arun(self, workflow_input: "WorkflowRunInput") -> AsyncIterator[BaseEvent]:
        """Async variant of :meth:`WorkflowHandle.run`.

        Guarded by a per-handle lock so overlapping ``arun`` calls serialize:
        a second turn waits until the first has recorded its ``run_id``.
        """
        from interactly.runtime.events import parse_event

        merged = _merge_dynamic_variables(workflow_input, self._dynamic_variables)
        async with self._turn_lock:
            response = await self._client.runs.execute_with_input(
                self._workflow_id,
                run_input=merged,
                run_id=self._run_id,
            )
            self._run_id = response.run_id
        for raw in response.events:
            yield parse_event(raw)


# --------------------------------------------------------------------------- #
# Convenience factories                                                       #
# --------------------------------------------------------------------------- #


def upload_and_get_handle(
    client: "WorkflowClient",
    config: "WorkflowConfigFullyHydrated",
    *,
    dynamic_variables: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> WorkflowHandle:
    """Upload a typed workflow config and return a :class:`WorkflowHandle`.

    Equivalent to::

        wf = client.workflows.create_from_config(config, name=..., description=...)
        return client.workflows.handle(wf.id, dynamic_variables=dynamic_variables)
    """
    wf = client.workflows.create_from_config(config, name=name, description=description)
    return client.workflows.handle(wf.id, dynamic_variables=dynamic_variables)


async def aupload_and_get_handle(
    client: "AsyncWorkflowClient",
    config: "WorkflowConfigFullyHydrated",
    *,
    dynamic_variables: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> AsyncWorkflowHandle:
    """Async variant of :func:`upload_and_get_handle`."""
    wf = await client.workflows.create_from_config(config, name=name, description=description)
    return await client.workflows.handle(wf.id, dynamic_variables=dynamic_variables)


# --------------------------------------------------------------------------- #
# Runtime surface                                                             #
# --------------------------------------------------------------------------- #
#
# ``WorkflowRuntime`` / ``AsyncWorkflowRuntime`` give the SDK a ``from_config`` /
# ``arun`` runtime vocabulary::
#
#     # build a runtime from a config and drive it turn-by-turn
#     runtime = await AsyncWorkflowRuntime.from_config(config, client=client)
#     async for event in runtime.arun(workflow_input):
#         ...
#
# Because the SDK executes the workflow remotely, ``from_config`` takes a
# ``client=`` argument to upload the config and drive turns. Everything else —
# ``arun`` / ``run``, ``run_id``, ``reset()`` — is inherited unchanged from the
# handle classes, so these are thin, behaviour-preserving aliases.


class WorkflowRuntime(WorkflowHandle):
    """Synchronous runtime over a remote workflow.

    Executes a workflow remotely against the Interactly Workflow API. Construct
    it with :meth:`from_config`; then drive it with :meth:`run` exactly like a
    :class:`WorkflowHandle` (of which it is a subclass).
    """

    @classmethod
    def from_config(
        cls,
        config: "WorkflowConfigFullyHydrated",
        *,
        client: "WorkflowClient",
        dynamic_variables: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "WorkflowRuntime":
        """Upload a typed config and return a ready-to-run runtime.

        The required ``client=`` keyword is because execution happens remotely.

        Args:
            config:            Typed ``WorkflowConfigFullyHydrated`` to upload.
            client:            The :class:`WorkflowClient` that runs the workflow.
            dynamic_variables: Optional defaults merged under each turn's own
                               ``dynamic_variables``.
            name:              Optional override for the workflow name.
            description:       Optional override for the workflow description.
        """
        workflow = client.workflows.create_from_config(config, name=name, description=description)
        return cls(
            client=client,
            workflow_id=workflow.id,
            config=config,
            dynamic_variables=dynamic_variables,
        )


class AsyncWorkflowRuntime(AsyncWorkflowHandle):
    """Asynchronous runtime over a remote workflow.

    The preferred entry point (async-first). A subclass of
    :class:`AsyncWorkflowHandle`; construct with :meth:`from_config` and drive
    with :meth:`arun`.
    """

    @classmethod
    async def from_config(
        cls,
        config: "WorkflowConfigFullyHydrated",
        *,
        client: "AsyncWorkflowClient",
        dynamic_variables: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "AsyncWorkflowRuntime":
        """Async variant of :meth:`WorkflowRuntime.from_config`."""
        workflow = await client.workflows.create_from_config(config, name=name, description=description)
        return cls(
            client=client,
            workflow_id=workflow.id,
            config=config,
            dynamic_variables=dynamic_variables,
        )


class RuntimeAccessor:
    """``client.runtime`` — build a :class:`WorkflowRuntime` from a typed config.

    Reads like a local library::

        runtime = client.runtime.from_config(config)
        runtime = client.runtime(config)              # shorthand
    """

    def __init__(self, client: "WorkflowClient") -> None:
        self._client = client

    def from_config(
        self,
        config: "WorkflowConfigFullyHydrated",
        *,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "WorkflowRuntime":
        return WorkflowRuntime.from_config(
            config,
            client=self._client,
            dynamic_variables=dynamic_variables,
            name=name,
            description=description,
        )

    __call__ = from_config


class AsyncRuntimeAccessor:
    """``client.runtime`` — build an :class:`AsyncWorkflowRuntime` from a typed config.

    Async-first::

        runtime = await client.runtime.from_config(config)
        runtime = await client.runtime(config)        # shorthand
    """

    def __init__(self, client: "AsyncWorkflowClient") -> None:
        self._client = client

    async def from_config(
        self,
        config: "WorkflowConfigFullyHydrated",
        *,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "AsyncWorkflowRuntime":
        return await AsyncWorkflowRuntime.from_config(
            config,
            client=self._client,
            dynamic_variables=dynamic_variables,
            name=name,
            description=description,
        )

    __call__ = from_config
