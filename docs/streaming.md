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

Three questions come up, and the events answer them differently. Pick the method, not the event type:

| Question | Answer |
|---|---|
| Is the run waiting for the user's next message? | `event.is_ready_for_input()`. True once per turn that hands over to the user, in every workflow. |
| Has the run ended? | `event.is_terminal()`, or iteration stops. True on `end_workflow` and on a `workflow_error` the run cannot carry on from; not on a failure the server tolerated (see Gotchas). |
| What is the turn's bookkeeping? | `end_workflow_iteration`. A marker only. Once companions run, it does not hand over to the user. |

```python
event.is_ready_for_input()   # the hand-over to the user: send the next message here
event.is_terminal()          # end_workflow, or a workflow_error that ends the run
```

`is_ready_for_input()` answers "your turn" in every workflow. The server sends `workflow_ready_for_input` only
while [companion threads](guides/companion_threads.md) run in the background. Without them, the stream marks the
turn's `end_workflow_iteration` as the hand-over instead, and marks a turn's `workflow_error` when the server
tolerated the failure, since the run then takes the next message.

Once companion threads are in play, companions keep emitting events while the main thread waits, so a loop that
breaks on `end_workflow_iteration` will cut off mid-turn or race. Send on `is_ready_for_input()`, and stop on
`is_terminal()` or when iteration ends.

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
| `workflow_ready_for_input` | The main thread waits for the user while companions run. Sent only then. |
| `workflow_error` | A node failed. `fatal` is False when the server tolerated it: the turn ends and the run takes the next message. True, or absent, when the run ends (see Gotchas). |
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

Pauses, on durable runs (`event.is_run_paused()`, `event.is_run_resumed()`):

| Type | Emitted when |
|---|---|
| `run_paused` | A person paused the run, or a message was refused while it is paused. Carries `paused_by` and `pause_reason`. |
| `run_resumed` | A person's pause of the run was lifted. Carries `resumed_by`. |

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
    workflow_run_id=None,            # take back a run a stream handed off (see below)
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

## Sending turns

One `async with` block holds a whole conversation. When an event is `is_ready_for_input()`, send the next
message and keep iterating the same stream:

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    async with client.runs.stream(
        workflow_id="wf-123",
        dynamic_variables={"name": "Alice"},
    ) as stream:
        replies = iter(["I'd like to book an appointment.", "Tuesday morning, please."])
        async for event in stream:
            if event.is_ready_for_input():
                reply = next(replies, None)
                if reply is None:
                    await stream.stop()
                else:
                    await stream.send(reply)
```

- `send(message=None, *, dynamic_variables=None, runtime_variables=None, run_input=None)` sends the turn as a
  `resume` frame, the same frame the workflow editor sends. Leave `message` out for a turn that carries none.
- The variables the stream was opened with go with every turn, merged with that turn's own. Edge conditions read
  variables only from the current turn's input, so each turn must carry them.
- Pass a typed `WorkflowRunInput` as `run_input` for a turn that needs more than one message, such as messages for
  other threads. A `message` and a `run_input` together raise `ValueError`.
- The server reads the socket only between turns. A turn sent while one is running waits and is taken when that
  turn ends. `send()` is therefore safe before `stream.run_id` is known: `run_id` is `None` until the server names
  the run.
- While a person has paused the run, the server refuses a turn with a `run_paused` event and drops the message.
  Send it again after `run_resumed`.
- `send()` raises `StreamError` when the stream is not open (outside its `with` block) or the run has ended. When
  the socket was already closed, `code` holds the close code (1000 for a normal close); after iteration has
  reported the end, there is no code. A refusal met while sending is not raised by `send()`: iteration raises its
  typed exception.

The synchronous `Stream` has `send()`, `stop()` and `run_id` with the same behaviour.

## Stopping a run

`stop()` ends the run. The server stores it `cancelled` with `termination_source` `client_stop`, not `completed`.
It sends "Workflow run stopped successfully" and closes normally, so keep iterating to read that last frame;
iteration then ends. Like `send()`, `stop()` takes effect between turns.

Leaving the `with` block closes the socket. The server cancels a run that has not finished (`termination_source`
`websocket_disconnect`), companion threads included, even mid-turn. The exception is a durable run parked on a
pause of its own (a wait, an approval, a signal, an external job): the server hands it off and the run keeps
`waiting`. Take it back, as below.

## Taking a run back

`client.runs.stream(workflow_id=..., workflow_run_id=...)` reopens a run that a stream handed off while it waited
on a pause. It needs durable socket runs on the server; where they are off, every take-back is refused.

```python
async with AsyncWorkflowClient() as client:
    async with client.runs.stream(
        workflow_id="wf-123",
        workflow_run_id=run_id,
    ) as stream:
        replies = iter(["Yes, go ahead."])
        async for event in stream:
            if event.is_ready_for_input():
                reply = next(replies, None)
                await (stream.send(reply) if reply else stream.stop())
```

- A take-back names the run and nothing else. `version_number`, `run_input`, `rerun_token`, or a command other than
  `WorkflowCommand.START` raises `ValueError` before connecting. `dynamic_variables` and `runtime_variables` are
  allowed, and go with each later turn.
- The first event acknowledges the take-back ("Workflow run taken back"), and carries `workflow_run_status` and
  `restored_messages`.
- A refusal raises from iteration:

| Close code | Exception | Refused when |
|---|---|---|
| 4010 | `TakeBackRefusedError` | Durable socket runs are off. Or the run belongs to another workflow, was not started from a live socket, has ended, is being cancelled, is open in another editor, has no stored state, or the server is carrying it on right now (retry shortly). A closed editor tab lets go within a minute or two. |
| 4030 | `TakeBackForbiddenError` | The caller's role is below developer. |
| 4040 | `StreamNotFoundError` | No such workflow or run on this team. |
| 1008 | `StreamPermissionError` | The caller is a viewer. |

## Close codes and errors

The run socket closes with one code per outcome. Code 1000 is the run ending, and iteration stops. Every other
code raises the exception below, a `StreamError` subclass carrying `code`, `reason` and `server_message`.
`server_message` is the full text of the `workflow_error` frame the server sent just before closing, when it sent
one: a close reason holds only 123 bytes.

| Close code | Exception | Meaning |
|---|---|---|
| 1000 | — | The run ended. Iteration stops. |
| 1008 | `StreamPermissionError` | The caller's role may not run workflows: a viewer, or a role the server does not know. Needs developer access or above. |
| 1011 | `StreamServerError` | The server failed while handling the run. |
| 4000 | `StreamRejectedError` | The start frame was malformed, the requested version does not exist, or the workflow's configuration or runtime could not load. A misused take-back start frame also lands here. |
| 4001 | `UnrunnableWorkflowError` | The workflow's nodes belong to a different version than the one requested. Fix the workflow; retrying the same frame will not help. |
| 4002 | `UnrunnableWorkflowError` | The workflow has no nodes. |
| 4003 | `ConcurrencyLimitError` | The team or workflow is already running as many runs as it may. Retry later. |
| 4005 | `UnrunnableWorkflowError` | A super node in the workflow could not be expanded. |
| 4006 | `InvalidStreamInputError` | The frame carried `initial_state`. A client is never the source of run state; use a `rerun_token` instead. |
| 4007 | `RerunTokenError` | The token expired, was minted for a different workflow or version, or the workflow changed since. Mint a fresh one. |
| 4009 | `RunChangedElsewhereError` | A person paused, resumed or cancelled the run, or another session carried it on. `server_message` gives its status. |
| 4010 | `TakeBackRefusedError` | The run could not be taken back. See above. |
| 4030 | `TakeBackForbiddenError` | The caller's role is below developer, for a take-back. |
| 4040 | `StreamNotFoundError` | The workflow or run does not exist for this team. |
| 4400 | `ResumeInputRejectedError` | The frame carried a resume input. Approve a pause with `client.runs.resume` instead. |

A close code not in this table raises a plain `StreamError`, with `code` and `reason` set. A viewer's socket is
accepted and closed at once, often before the start frame goes out; iteration still reports that close, so a
viewer gets `StreamPermissionError` (1008) even then.

The two start-frame rejections are the ones most code handles. Both subclass `StreamError`, so an existing
`except StreamError` keeps working:

```python
from interactly import AsyncWorkflowClient, RerunTokenError, StreamError

async with AsyncWorkflowClient() as client:
    try:
        async with client.runs.stream(workflow_id=wf_id, rerun_token=token) as events:
            async for event in events:
                ...
    except RerunTokenError:
        token = (await client.reruns.create_token(run_id, turn_index=3)).rerun_token   # mint a fresh one
    except StreamError as exc:
        print("stream failed:", exc.code, exc.server_message or exc.reason)
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
- [Run control](guides/run_control.md) — pausing, resuming and signalling durable runs
- [Error handling](error_handling.md) — the exception hierarchy

## Gotchas

- **A `workflow_error` does not always end the run.** On the run socket, a node failure the server tolerates ends
  the turn with a `workflow_error` marked `fatal: false` and leaves the socket open; the run takes the next
  message. The stream marks that error `is_ready_for_input()`, and `is_terminal()` is False for it. The server sends
  it before it checks the workflow's error limits (`num_errors_tolerated`, `num_consecutive_errors_tolerated`,
  `stop_workflow_on_error`). When they end the run after all, one more `workflow_error` follows, with no `fatal` flag
  and the whole reason, and the socket closes with 1011, which iteration raises as `StreamServerError`. So a turn
  sent on a tolerated error can still meet the end of the run. An error from an older server, which sends no flag,
  counts as terminal.
- **Leaving the `with` block cancels the run**, companion threads included, even mid-turn. Iterate until the run
  ends, or call `stop()` first.
- **`send()` mid-turn waits.** The turn is taken when the current one ends, not at once.
- **`stop()` is stored `cancelled`**, not `completed`. Check `termination_source` (`client_stop`) to tell it apart.
- **A refusal met while sending is raised by iteration**, not by `send()`.
- **A take-back needs durable socket runs on the server.** Where they are off, every take-back raises
  `TakeBackRefusedError`, so check the server before relying on one.
- **Event fields are top-level attributes**, not `event.data`, which the server never populates.
