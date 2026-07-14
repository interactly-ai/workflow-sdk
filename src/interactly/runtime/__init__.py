"""SDK runtime: workflow runtimes and typed event types.

The runtime provides a ``from_config`` / ``arun`` surface that executes a
workflow remotely against the Interactly Workflow API. The only difference from
an in-process runtime is the ``client=`` argument.

Async-first usage (preferred)::

    from interactly import AsyncWorkflowClient
    from interactly.runtime import AsyncWorkflowRuntime
    from interactly.runtime.events import AssistantResponseEvent

    runtime = await AsyncWorkflowRuntime.from_config(config, client=client)
    async for event in runtime.arun(workflow_input):
        if isinstance(event, AssistantResponseEvent):
            print(event.content)

Synchronous mirror::

    from interactly import WorkflowClient
    from interactly.runtime import WorkflowRuntime

    runtime = WorkflowRuntime.from_config(config, client=client)
    for event in runtime.run(workflow_input):
        ...

``WorkflowHandle`` / ``AsyncWorkflowHandle`` and the
``upload_and_get_handle`` / ``aupload_and_get_handle`` factories remain available
as lower-level / back-compatible aliases.
"""

from interactly.runtime.handle import (
    AsyncRuntimeAccessor,
    AsyncWorkflowHandle,
    AsyncWorkflowRuntime,
    RuntimeAccessor,
    WorkflowHandle,
    WorkflowRuntime,
    aupload_and_get_handle,
    upload_and_get_handle,
)

__all__ = [
    "AsyncRuntimeAccessor",
    "AsyncWorkflowHandle",
    "AsyncWorkflowRuntime",
    "RuntimeAccessor",
    "WorkflowHandle",
    "WorkflowRuntime",
    "aupload_and_get_handle",
    "upload_and_get_handle",
]
