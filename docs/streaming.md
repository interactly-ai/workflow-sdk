# Streaming

The SDK streams workflow run events over WebSocket with `client.runs.stream()`. This is the
recommended way to run workflows when you want live output — and, since it is the only driver that
stores a config snapshot on the run, the only one whose runs can later be [re-run](guides/reruns.md).

---

## Basic Usage

`stream()` returns an async context manager. Open it with `async with` and iterate with `async for`:

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
            if event.is_ready_for_input() or event.is_terminal():
                break
```

The `async with` block ensures the WebSocket is cleanly closed on exit — whether by `break`,
exception, or normal exhaustion.

---

## Knowing when to stop

Three events are easy to confuse, and picking the wrong one is the most common streaming bug:

| Event type | Means | Use it to |
|---|---|---|
| `end_workflow_iteration` | One turn's accounting is done. Other threads may still be running. | Nothing — it is a bookkeeping marker. |
| `workflow_ready_for_input` | Every non-companion thread has settled. | **Send the next user message.** |
| `end_workflow` | Every thread has ended, companions included. | Finish. |

```python
event.is_ready_for_input()   # True for workflow_ready_for_input
event.is_terminal()          # True for end_workflow and workflow_error
```

Once [companion threads](guides/companion_threads.md) are in play these genuinely diverge: companions
keep emitting events while the main thread waits, so a loop that breaks on `end_workflow_iteration`
will cut off mid-turn or race. Break on `is_ready_for_input()` for "the caller's turn", and
`is_terminal()` for "the run is over".

`workflow_ready_for_input` carries `active_companion_thread_ids` — what is still running in the
background at that moment. Note these are **internal** ids: a companion configured as
`thread_id="labpoll"` appears as `"0_companion_labpoll"`. Match on the suffix, not equality.

---

## `RunEvent` fields

Every event is a `RunEvent`. Unknown event types and unknown fields are accepted (`extra="allow"`), so
a server-side addition never breaks an older client.

| Field | Type | Description |
|---|---|---|
| `type` | `str` | Event type — see the catalog below. |
| `output` | `Any \| None` | Text output or streamed token. Mapped from the server's `content`. |
| `node_id` | `str \| None` | Logical ID of the node. Mapped from `origin_node_logical_id`. |
| `thread_reference_id` | `str \| None` | `"0"` for the main thread, or a companion's configured `thread_id`. |
| `status` | `str \| None` | Run status after this event. |
| `error` | `str \| None` | Error message for failure events. |
| `global_node_logical_id` | `str \| None` | For `reverse_conditional_edge`: the global node returning control. |
| `data` | `dict \| None` | Legacy slot. **The server never populates it** — see below. |

Because unknown fields are preserved, event-specific fields not listed above are still reachable — via
attribute access or `model_extra`. That is where they actually arrive: **top-level, not under
`data`**. `self_loop_exhausted` gives you `event.outcome` and `event.total_attempts`;
`waiting_condition_matched` gives you `event.hydrated_condition_expression`. Reaching for
`event.data` gets you `None` every time.

### Event catalog

Lifecycle and navigation:

| Type | Emitted when |
|---|---|
| `start_workflow` / `end_workflow` | The run began / every thread has ended. |
| `end_workflow_iteration` | One turn completed. Carries `iteration_metrics`. |
| `workflow_ready_for_input` | Ready for the next user message. |
| `workflow_error` | The run terminated with an error. |
| `conditional_edge` / `direct_edge` | A transition was taken. |
| `reverse_conditional_edge` | A global node returned control to its caller. |
| `guardrail_escalation_edge` | The guardrail-strikes threshold escalated the run. |

Background work ([companion threads](guides/companion_threads.md),
[waiting evaluation](guides/waiting_evaluation.md)):

| Type | Emitted when |
|---|---|
| `companion_step_boundary` | One companion self-loop step finished. |
| `waiting_evaluation_boundary` | A parked thread's waiting-edges were evaluated. |
| `waiting_condition_matched` | A waiting edge fired with **no user message**. |

Bounded [self-loops](guides/self_loops.md):

| Type | Emitted when |
|---|---|
| `self_loop_delay` | About to wait `time_between_retries`. |
| `self_loop_exhausted` | Stopped on `max_retries` or `expiry_time`. |
| `node_expired` | An in-flight execution was terminated by `expiry_time`. |

---

## Stream parameters

```python
async with client.runs.stream(
    workflow_id="wf-123",
    command=WorkflowCommand.START,   # default
    run_by="api",                    # default
    version_number=None,             # optional; defaults to the active version
    dynamic_variables={"name": "Alice"},   # fills {{...}} placeholders
    runtime_variables={"attempt": 1},      # fills [[...]] placeholders
    run_input=None,                  # optional typed WorkflowRunInput (preferred)
    rerun_token=None,                # redeem a re-run projection
    cast_to=RunEvent,                # default
) as events:
    ...
```

`run_input` takes a typed `WorkflowRunInput` and is the preferred way to supply a full turn — its
fields are merged into the payload, which the server validates as a complete `WorkflowRunInput`.
`dynamic_variables` / `runtime_variables` are layered on top when both are given.

### Starting a re-run

```python
token = await client.reruns.create_token(run_id, turn_index=3)

async with client.runs.stream(
    workflow_id="wf-123",
    rerun_token=token.rerun_token,
) as events:
    ...
```

Only meaningful on a `start` frame. See [Re-runs](guides/reruns.md).

---

## Close codes and errors

Most closures are the end of the stream. Two are the server **rejecting your start frame**, and the
SDK raises a specific exception for each rather than a generic failure:

| Close code | Exception | Meaning |
|---|---|---|
| 1000 | — | Normal closure. The iterator simply ends. |
| **4006** | `InvalidStreamInputError` | The frame carried `initial_state`. A client is never the source of run state — use a `rerun_token` instead. |
| **4007** | `RerunTokenError` | The token expired, was minted for a different workflow or version, or the workflow changed since. |
| anything else | `StreamError` | Abnormal termination. |

Both subclass `StreamError`, so an existing `except StreamError` keeps working:

```python
from interactly import InvalidStreamInputError, RerunTokenError, StreamError

try:
    async with client.runs.stream(workflow_id=wf_id, rerun_token=token) as events:
        async for event in events:
            ...
except RerunTokenError:
    token = (await client.reruns.create_token(run_id, 3)).rerun_token   # mint a fresh one
except StreamError as exc:
    print("stream failed:", exc)
```

---

## Non-streaming (HTTP) execution

For quick workflows, or when you do not need incremental output:

```python
response = await client.runs.execute(
    workflow_id="wf-123",
    dynamic_variables={"name": "Alice"},
    run_by="my-service",
)

print(response.status, response.turn_number)
for event in response.events:
    print(event)
```

`execute()` returns an `InteractiveRunResponse`: `run_id`, `status`, `turn_number`, `events`,
`is_waiting_for_input`, `is_completed`, `error`, `next_input_hint`, plus `has_background_work` and
`has_active_companions`.

**Two things the REST path does not do**, both of which matter:

1. **It does not advance background work.** A run with companion threads or waiting-evaluation edges
   will not progress unless you pump it — see
   [Companion threads](guides/companion_threads.md#driving-a-run-with-companions).
2. **It does not store a config snapshot**, so its runs can never be re-run. If you might want to
   replay a conversation later, drive it with `stream()`.

---

## Connection details

The SDK converts your HTTP `base_url` to a WebSocket URL automatically (`https://` → `wss://`,
`http://` → `ws://`) and appends `/v1/workflow-runs/ws`. You never construct the URL yourself.

Where the gateway authenticates WebSocket upgrades with a single-use session token rather than the
bearer header, the SDK mints one and appends it as `?token=`, falling back to header auth when no
session endpoint is available.

---

## Synchronous alternative

The synchronous client uses `with` instead of `async with`:

```python
from interactly import WorkflowClient

client = WorkflowClient()

with client.runs.stream(workflow_id="wf-123") as events:
    for event in events:
        print(f"[{event.type}] {event.output}")
        if event.is_ready_for_input() or event.is_terminal():
            break
```

---

## See also

- [Running workflows](guides/running_workflows.md) — stream vs. execute vs. handle
- [Companion threads](guides/companion_threads.md) — background threads and pumping
- [Re-runs](guides/reruns.md) — replaying a finished run
- [Error handling](error_handling.md) — the exception hierarchy
