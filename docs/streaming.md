# Streaming

The SDK supports real-time streaming of workflow run events over WebSocket using
`client.runs.stream()`. This is the recommended way to run workflows when you
need live output as the workflow progresses.

---

## Basic Usage

`stream()` returns an async context manager. Open it with `async with` and
iterate over events with `async for`:

```python
from interactly import AsyncWorkflowClient
from interactly.types.shared import WorkflowCommand

async with AsyncWorkflowClient() as client:
    async with client.runs.stream(
        workflow_id="wf-123",
        command=WorkflowCommand.START,
    ) as events:
        async for event in events:
            print(f"[{event.type}] {event.output}")
            if event.is_terminal():
                break
```

The `async with` block ensures the WebSocket connection is cleanly closed when you
exit — whether by `break`, exception, or normal exhaustion.

---

## RunEvent Fields

Each `RunEvent` represents a single step in the workflow execution:

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Event type (e.g. `"llm"`, `"tool"`, `"condition"`, `"complete"`). |
| `output` | `Any` | The output produced by this step. |
| `node_logical_id` | `str \| None` | Logical ID of the node that produced this event. |
| `run_id` | `str \| None` | ObjectId of the run. |
| `logical_id` | `str` | Unique ID for this event within the run. |
| `error` | `str \| None` | Error message if this event represents a failure. |
| `message_ids` | `List[str]` | IDs of any messages associated with this event. |

### `is_terminal()`

```python
event.is_terminal()  # -> bool
```

Returns `True` if the event signals the end of the run (type is `"complete"`,
`"error"`, or `"cancelled"`). Use this as your loop exit condition.

---

## Stream Parameters

`stream()` itself takes only run-selection parameters — its full signature is:

```python
async with client.runs.stream(
    workflow_id="wf-123",
    command=WorkflowCommand.START,  # default: WorkflowCommand.START
    run_by="api",                    # default: "api"
    version_number=None,             # optional; defaults to active version
    cast_to=RunEvent,                # default: RunEvent
) as events:
    async for event in events:
        pass
```

It does **not** accept `dynamic_variables` or `runtime_variables`. To supply variables, use one of the
turn-based paths instead:

- **`execute()` / `execute_with_input()`** (HTTP) — accepts `dynamic_variables`, `runtime_variables`,
  and `miscellaneous` (see [Interactive Execution](guides/running_workflows.md#interactive-execution-http)).
- **A runtime handle** — pass them in each turn's `WorkflowRunInput`, or once at
  `aupload_and_get_handle(..., dynamic_variables=...)`. See [Workflow Handles](guides/running_workflows.md#workflow-handles).

`dynamic_variables` fill `{{...}}` placeholders; `runtime_variables` fill `[[...]]` placeholders.

---

## Non-Streaming (HTTP) Execution

For workflows that complete quickly or when you do not need incremental output,
use `execute()` instead:

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    run = await client.runs.execute(
        workflow_id="wf-123",
        dynamic_variables={"name": "Alice"},
        run_by="my-service",
    )
    print(run.status, run.output)
```

`execute()` is a coroutine that blocks until the run completes and returns the final `InteractiveRunResponse`.

> **Typed run I/O:** When `interactly-configs` is installed (`pip install workflow-sdk[configs]`),
> `run.input` and `run.output` are automatically deserialised to `BaseRunInput` and
> `BaseRunOutput` typed Pydantic objects. Without the package they remain plain `dict`.
> See [configs.md](configs.md) for details.

---

## Checkpoint Branching

To replay or branch a conversation from a previous run:

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    new_run = await client.runs.checkpoint(
        workflow_id="wf-123",
        run_id="run-abc",
        resume_turn_index=3,          # replay from turn 3
        start_node_logical_id=None,   # use default start node
    )
```

The checkpoint creates a new run pre-loaded with conversation pairs 0–3 from
the source run and continues execution from that point.

---

## Connection Details

The SDK converts your HTTP `base_url` to a WebSocket URL automatically:
- `https://` → `wss://`
- `http://` → `ws://`

The WebSocket path is `/v1/workflow-runs/ws`. You do not need to construct the
URL manually.

---

## Synchronous alternative

The synchronous `WorkflowClient` uses `with` instead of `async with`:

```python
from interactly import WorkflowClient

client = WorkflowClient()

with client.runs.stream(workflow_id="wf-123") as events:
    for event in events:
        print(f"[{event.type}] {event.output}")
        if event.is_terminal():
            break
```
