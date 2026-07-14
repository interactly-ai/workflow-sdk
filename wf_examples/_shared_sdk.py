"""Shared helpers for the workflow-authoring examples in ``wf_examples/``.

These helpers drive a server-backed conversation loop via
:class:`AsyncWorkflowHandle`.  They are kept deliberately small so each script
stays easy to read.

This module is also the **single-source ``sys.path`` bootstrap** for
``wf_examples/``. Every example's first line is
``import _shared_sdk``; importing it inserts this SDK's ``src`` and
``configs/src`` directories onto ``sys.path`` so the short ``import interactly`` /
``import interactly_configs`` names resolve without installing the package.
Everything it adds lives inside this SDK folder — nothing outside is required.
Run examples directly, e.g.::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_1.py
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

# --- Single-source sys.path bootstrap (must run before importing interactly) ---
# Everything needed lives inside this SDK folder: ``src`` exposes ``interactly``
# and ``configs/src`` exposes ``interactly_configs``. Nothing outside the SDK is added.
_sdk_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
for _p in (os.path.join(_sdk_root, "src"), os.path.join(_sdk_root, "configs", "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interactly import AsyncWorkflowClient  # noqa: E402

try:
    from langchain_core.messages import HumanMessage  # type: ignore  # noqa: E402
except ImportError:  # pragma: no cover - convenience shim
    HumanMessage = None  # type: ignore[assignment]

from interactly.configs import WorkflowConfigFullyHydrated  # noqa: E402
from interactly.runtime import (  # noqa: E402
    AsyncWorkflowHandle,
    aupload_and_get_handle,
)
from interactly.runtime.events import (  # noqa: E402
    AssistantResponseEvent,
    BusyWaitForUserMessageEvent,
)

__all__ = [
    "get_async_client",
    "make_handle",
    "print_chat_history",
    "chat_loop",
    "HumanMessage",
]


def get_async_client() -> AsyncWorkflowClient:
    """Build an :class:`AsyncWorkflowClient` using ``INTERACTLY_*`` env vars.

    Required env vars:
        INTERACTLY_API_KEY    Bearer token.
    Optional env vars:
        INTERACTLY_BASE_URL   Server URL (default: official endpoint).
        INTERACTLY_TEAM_ID    Team scoping header.
        INTERACTLY_USER_ID    User scoping header.
    """
    return AsyncWorkflowClient(
        api_key=os.environ.get("INTERACTLY_API_KEY"),
        base_url=os.environ.get("INTERACTLY_BASE_URL"),
        team_id=os.environ.get("INTERACTLY_TEAM_ID"),
        user_id=os.environ.get("INTERACTLY_USER_ID"),
    )


async def make_handle(
    config: WorkflowConfigFullyHydrated,
    dynamic_variables: Optional[dict] = None,
    *,
    client: Optional[AsyncWorkflowClient] = None,
) -> AsyncWorkflowHandle:
    """Upload ``config`` and return an :class:`AsyncWorkflowHandle`.

    If ``client`` is omitted a new one is built from environment variables.
    """
    own_client = client or get_async_client()
    return await aupload_and_get_handle(
        own_client,
        config,
        dynamic_variables=dynamic_variables or {},
    )


def print_chat_history(chat_history: list[str]) -> None:
    """Print the rolling chat-history banner used by the original examples."""
    line = "=" * 141
    print(line)
    print("\n\n======================================= Chat History " + "=" * 87)
    print(line)
    for msg in chat_history:
        print(msg)


async def chat_loop(
    handle: AsyncWorkflowHandle,
    dynamic_variables: Optional[dict] = None,
    *,
    user_input_thread_id: str = "0",
) -> None:
    """A drop-in replacement for the per-script ``while True`` loop.

    Reads user input from stdin, sends it as a :class:`HumanMessage` for the
    given thread, prints every event, and tracks an elapsed-time histogram
    over assistant turns.  Type ``<exit>`` to leave.
    """
    if HumanMessage is None:  # pragma: no cover - friendlier error
        raise RuntimeError(
            "chat_loop requires langchain_core. Install it with:\n"
            "    pip install langchain-core"
        )

    # Imported lazily so module import does not require the configs extra
    # for callers that only want ``get_async_client``.
    from interactly.configs import NodesRunInputs, WorkflowRunInput
    from interactly.configs import LLMNodeRunInput

    dynamic_variables = dynamic_variables or {}
    chat_history: list[str] = []
    elapsed_times: list[float] = []
    prev_time = time.time()

    while True:
        print_chat_history(chat_history)
        user_input = input("User Input: ")
        chat_history.append(f"\n USER: {user_input} \n")
        if user_input.strip() == "<exit>":
            break

        user_message = HumanMessage(content=user_input)
        workflow_input = WorkflowRunInput(
            thread_to_node_inputs={
                user_input_thread_id: NodesRunInputs(
                    node_run_inputs=[LLMNodeRunInput(messages=[user_message])],
                ),
            },
            dynamic_variables=dynamic_variables,
        )
        prev_time = time.time()

        loop_count = 0
        async for event in handle.arun(workflow_input):
            loop_count += 1
            print(f"\nEvent received: {type(event).__name__}\n{event.model_dump_json(indent=2)}\n")
            if isinstance(event, BusyWaitForUserMessageEvent):
                chat_history.append(f"\n NODE: {event.origin_node_name} .. is waiting for user input... \n")
            elif isinstance(event, AssistantResponseEvent):
                elapsed = time.time() - prev_time
                chat_history.append(f"\n ASSISTANT (in {elapsed:.2f} sec) ({event.origin_node_name}): {event.content} \n")
                elapsed_times.append(elapsed)
                prev_time = time.time()

            if loop_count > 100:
                print("Quitting because of potential infinite loop")
                break

    if elapsed_times:
        elapsed_times.sort()
        n = len(elapsed_times)
        median = elapsed_times[n // 2] if n % 2 == 1 else (elapsed_times[n // 2 - 1] + elapsed_times[n // 2]) / 2
        average = sum(elapsed_times) / n
        p90 = elapsed_times[int(n * 0.9)]
        p99 = elapsed_times[int(n * 0.99)]
        print(f"Total samples: {n}")
        print(f"All samples (sorted): {elapsed_times}")
        print(
            f"Elapsed First Token Time (ms): Median: {median:.2f}, "
            f"Average: {average:.2f}, 90th Percentile: {p90:.2f}, "
            f"99th Percentile: {p99:.2f}"
        )
