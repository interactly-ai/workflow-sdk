# Companion Threads

Fork a **background thread** off a direct edge. It keeps running — and keeps emitting events — while
the main thread waits for the caller's next message.

The motivating case: a caller asks "are my lab results back yet?" while a companion thread polls the
EHR every few seconds. The conversation carries on, and the moment the result lands the workflow can
move without waiting for the caller to speak again (see
[Evaluate while waiting](waiting_evaluation.md) for that second half).

## Setup

```python
import interactly_configs as ic
```

Companion threads are an **authoring-time** feature: you configure them on an edge, and the runtime
does the rest. There is no `client.companion_threads` resource.

---

## Forking a thread

A companion is a direct edge with `companion_thread_config` set:

```python
poller = ic.NoOpNodeConfig(name="poll lab results")   # stands in for a real polling node
chat = ic.SayLLMNodeConfig(name="chat", wait_for_user_message=True)

edges = [
    # The main thread — exactly one, and it must NOT be a companion.
    ic.DirectEdgeConfig(
        source_node_logical_id=entry.logical_id,
        destination_node_logical_id=chat.logical_id,
    ),
    # The companion fork.
    ic.DirectEdgeConfig(
        source_node_logical_id=entry.logical_id,
        destination_node_logical_id=poller.logical_id,
        companion_thread_config=ic.CompanionThreadConfig(
            is_companion_thread=True,
            thread_id="labpoll",
        ),
    ),
]
```

A node with a **single** outgoing direct edge always continues the main thread, whatever the flag
says. The fork only means anything when a node fans out.

### Reading the flags back

Four helpers read the nested config defensively, so they are safe to call on any edge — including
edges stored before the feature existed:

```python
ic.edge_is_companion(edge)              # True for a flagged direct edge
ic.edge_companion_thread_id(edge)       # "labpoll", or None
ic.edge_evaluates_while_waiting(edge)   # for conditional edges
ic.edge_waiting_evaluation_config(edge) # the config, if enabled
```

---

## Cross-thread variables

Give a companion a `thread_id` and other threads can read its runtime variables:

```
[[thread_labpoll.result_status]]     # any thread reading the companion's variable
[[thread_0.customer_name]]           # the companion reading the main thread
```

The main thread is always `thread_0`. Without a `thread_id` the server mints a uuid at fork time and
the companion is **not addressable** — it still runs, you just cannot reference its variables. If
another thread needs to read it, name it.

### `thread_id` rules

Enforced at save time, so a bad id fails when you create the workflow rather than mid-call:

- Characters `[A-Za-z0-9_-]` only — **no dots** (they separate the id from the variable name).
- Must not contain `_companion_` (the internal delimiter).
- Must not be `"0"` (reserved for the main thread).
- **Unique across the whole workflow.** Two companions sharing an id would collide on the same
  internal thread id at fork time and overwrite each other's state.

---

## The four graph rules

The server validates these when you create the workflow and rejects violations with **HTTP 400**.
They are worth knowing up front because each one is easy to trip while designing a graph.

### 1. Exactly one main edge

If a node has several outgoing direct edges, exactly one must have `is_companion_thread=False` and
all the rest `True`. Two "main" edges would mean two conversations with one caller.

### 2. Companions must be non-interactive

A companion sub-graph must not reach a node with `wait_for_user_message=True`. Companions never
receive user messages and must terminate within their turn, so an interactive node there would park
forever.

### 3. No nested forks

A companion sub-graph may not fan out companion edges of its own. Companions fork from the main
thread only.

### 4. No convergence back onto the main thread

A node reachable from both a companion sub-graph and the main thread is classified globally as a
companion node — which would strip its global-node fan-in even when the *main* thread executes it.
Rather than let that misbehave quietly, the server rejects it. Keep the companion sub-graph separate;
communicate through variables, not by rejoining.

---

## The rule that catches people out

**A node with outgoing direct edges cannot also carry an evaluate-while-waiting conditional edge.**

Direct edges take precedence on the normal transition path, so such an edge would fire *only* in the
background and never after a node execution — divergent behaviour from one config. The server refuses
it.

In practice this means: **fork the companion upstream of the node that waits.**

```
        ┌────────────► poller  (companion thread "labpoll")
        │
     entry
        │
        └────────────► chat  ──[waiting conditional]──► junction
```

`entry` carries the fork. `chat` waits for the caller and carries the waiting edge. If you put both on
`chat`, creation fails with:

```
BadRequestError: Invalid 'evaluate while waiting for user input' edge configuration:
Edge 'e1' has evaluate_while_waiting_config enabled but its source node also has outgoing
direct edges, which take precedence on the normal transition path.
```

---

## Driving a run with companions

### Over WebSocket — nothing to do

The WebSocket driver pumps background work itself while it waits for the next message. Companion
events simply arrive in the stream.

**One thing changes:** `end_workflow_iteration` no longer means "your turn". Use
`is_ready_for_input()`:

```python
async with client.runs.stream(workflow_id=workflow_id) as stream:
    async for event in stream:
        if event.is_ready_for_input():   # workflow_ready_for_input
            break                        # NOW it is safe to send the next message
        if event.is_terminal():          # end_workflow — ALL threads finished
            break
```

Three events that are easy to conflate:

| Event | Means |
|---|---|
| `end_workflow_iteration` | One turn's accounting is done. Companions may still be running. |
| `workflow_ready_for_input` | Every non-companion thread has settled. **Send the next message.** |
| `end_workflow` | Every thread has ended, companions included. |

A loop that breaks on `end_workflow_iteration` will race or hang once companions are in play.

### Over REST — you must pump

The REST driver does **not** advance background work on its own. The intended shape is:

```python
response = await client.runs.execute(workflow_id, command=WorkflowCommand.START)

if response.has_background_work:
    responses = await client.runs.drive_background_work(
        workflow_id, response.run_id,
        interval_seconds=1.0,
        max_iterations=60,
    )
    for r in responses:
        for event in r.events:
            print(event)
```

`drive_background_work` polls until nothing remains, and is **bounded** — a companion can legitimately
run for a long time, so it returns after `max_iterations` rather than blocking forever. Check the last
response's `has_background_work` to tell "finished" from "ran out of iterations". It returns *every*
response, so no events are lost.

For one step at a time, `pump_companions()` is the primitive underneath.

> `has_background_work` is the flag to poll on. `has_active_companions` is retained for backward
> compatibility and is a strict subset — it misses parked threads with armed waiting-evaluations.

> **⚠️ Needs a server build that includes `interactly-ai@6b09ada25`.**
>
> Before that fix the REST path did not run companions at all: `execute()` returned as soon as the
> main thread parked, and the companion's first node emitted `start_node_run` and was then abandoned
> — no `end_node_run`, `has_background_work` stuck at `False`, nothing for `pump_companions()` to
> advance, and a later user turn did not resurrect it. The cause was the REST turn loop breaking out
> of the runtime generator on the busy-wait event, which cancelled the drain loop mid-companion.
>
> **Check `has_background_work` rather than assuming.** If it is `False` on a run you know has a
> companion, you are talking to a server that predates the fix — drive that workflow over `stream()`,
> which was never affected.

**A pump can produce main-thread output.** If a waiting condition matches during the pump, the
workflow advances and the response carries assistant messages — even though no user message was sent.

---

## Reading companion events

Every event carries `thread_reference_id`: `"0"` for the main thread, or the companion's configured
id.

```python
async for event in stream:
    if event.thread_reference_id == "labpoll":
        print("background:", event.type)
    elif event.thread_reference_id == "0":
        print("main:", event.output)
```

Companion-specific event types:

| Type | Meaning |
|---|---|
| `companion_step_boundary` | One companion self-loop step finished. A safe checkpoint point. |
| `waiting_evaluation_boundary` | A parked thread's waiting-edges were evaluated. |
| `workflow_ready_for_input` | Carries `active_companion_thread_ids` — what is still running. |

`active_companion_thread_ids` holds **internal** ids: a companion configured as `thread_id="labpoll"`
appears as `"0_companion_labpoll"`. Match on the suffix, not equality.

Event-specific fields arrive as **top-level attributes**, not under `event.data` — `RunEvent` is
`extra="allow"`, and `data` is never populated by the server. So `self_loop_exhausted` gives you
`event.outcome` and `event.total_attempts` directly.

---

## Synchronous alternative

```python
from interactly import WorkflowClient

client = WorkflowClient()

response = client.runs.execute(workflow_id, command=WorkflowCommand.START)
if response.has_background_work:
    client.runs.drive_background_work(workflow_id, response.run_id, interval_seconds=1.0)
```

---

## See also

- [Evaluate while waiting](waiting_evaluation.md) — letting a companion's result move the conversation
- [Self-loops](self_loops.md) — making a companion poll repeatedly
- [Nodes, edges & tools](nodes_edges_tools.md) — edge types and the NoOp node
- [`wf_examples/wf_example_progression_24.md`](../../wf_examples/wf_example_progression_24.md) — a complete worked graph

> **Not the same "companion" as `CompanionEdgeConfig`.** That is an *edge type* pairing a Say agent
> with a silent Worker agent inside one turn (see
> [example 6](../../wf_examples/wf_example_progression_6.md)). `CompanionThreadConfig` is a *setting
> on a direct edge* that forks a genuinely concurrent background thread. Same word, unrelated
> mechanisms.
- [Streaming](../streaming.md) — the event protocol

## Gotchas

- **Fork upstream of the node that waits**, never on it. See the rule above.
- **`end_workflow_iteration` is not "your turn."** Use `is_ready_for_input()`.
- **REST runs need pumping**, and need a server build with `interactly-ai@6b09ada25`. `stream()`
  was never affected.
- **`active_companion_thread_ids` holds internal ids** (`0_companion_labpoll`), not your `thread_id`.
- **Event extras are top-level attributes**, not `event.data`.
- **An unnamed companion is unaddressable.** Set `thread_id` if anything needs to read its variables.
- **Companion sub-graphs cannot rejoin the main thread.** Communicate via variables instead.
- **A companion that never terminates keeps the run alive.** Bound it with
  [`SelfLoopConfig`](self_loops.md).
