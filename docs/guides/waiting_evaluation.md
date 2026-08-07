# Evaluate While Waiting

Let a conditional edge fire **while its source node is parked waiting for the caller** — with no user
message required.

## The problem it solves

A conditional edge is normally evaluated at exactly one moment: immediately after each execution of
its source node. So a `say_llm` node with `self_loop` and `wait_for_user_message=True` parks
indefinitely, and a runtime variable that changes in the background — written by a polling node in a
[companion thread](companion_threads.md), say — cannot move the conversation forward on its own.

That is the gap this closes. The caller asks "are my results back?", the assistant says "let me check",
and when the companion thread writes the result the workflow advances **by itself**.

## Setup

```python
import interactly_configs as ic
```

Like companion threads, this is authoring-time configuration; there is no resource to call.

---

## Enabling it

```python
edge = ic.ConditionalEdgeConfig(
    source_node_logical_id=chat.logical_id,
    destination_node_logical_id=deliver_result.logical_id,
    condition=ic.ConditionConfig(
        condition_expression="isPresent([[thread_labpoll.result_status]])",
    ),
    evaluate_while_waiting_config=ic.EvaluateWhileWaitingConfig(
        enabled=True,
        trigger_node_logical_ids=[poller.logical_id],
    ),
)
```

Leaving `evaluate_while_waiting_config` unset (the default) preserves the classic behaviour exactly:
evaluated only after each source-node execution.

---

## Trigger modes

**What arms an evaluation** — the difference between doing work when something changed and polling
blindly.

### `ON_NODE_COMPLETION` (default, recommended)

Armed when a nominated node completes another execution, in any thread. Nothing happens until the node
that can actually change the expression's inputs has run.

```python
ic.EvaluateWhileWaitingConfig(
    enabled=True,
    trigger_mode=ic.WaitingEvaluationTriggerMode.ON_NODE_COMPLETION,
    trigger_node_logical_ids=[poller.logical_id],
    min_seconds_between_evaluations=1.0,   # optional debounce
)
```

Typically the trigger is the companion-thread node that updates the variable the expression reads.

### `ON_EVERY_BACKGROUND_TICK`

Armed on every background pass — blind polling. Only for when you genuinely cannot name a trigger
node.

```python
ic.EvaluateWhileWaitingConfig(
    enabled=True,
    trigger_mode=ic.WaitingEvaluationTriggerMode.ON_EVERY_BACKGROUND_TICK,
    min_seconds_between_evaluations=5.0,   # REQUIRED, and must be > 0
)
```

**The debounce is mandatory here, not advisory.** This mode is always armed, so with no debounce it
evaluates on every background pass: the driver loop spins as fast as the event loop allows, each pass
appends an event to the run record, and the runtime is re-serialized on every voice silence tick. The
server rejects `0` and `None` outright rather than warning.

---

## Bounding the loop

```python
ic.EvaluateWhileWaitingConfig(
    enabled=True,
    trigger_node_logical_ids=[poller.logical_id],
    max_transitions_per_wait=3,   # default
)
```

`max_transitions_per_wait` caps how many times this edge may fire during a single uninterrupted wait,
and resets when a user message arrives. It guards against a background hop loop in which the caller is
never given a turn — the workflow talking to itself while someone waits on the line.

---

## The validation rules

All enforced at save time, returning **HTTP 400**. Each exists because the alternative is a
conversation that hangs, which is far harder to diagnose than a rejected save.

| # | Rule | Why |
|---|---|---|
| 1 | Must use `condition_expression` | There has to be something to evaluate. |
| 2 | `condition_freeform` is rejected | A natural-language condition needs an LLM call *per evaluation*. Rejected rather than ignored, so you cannot believe one is being polled. |
| 3 | `ON_NODE_COMPLETION` requires trigger nodes | Otherwise it silently degrades to a blind poll. |
| 4 | Trigger node ids must exist | A typo is a permanent hang. |
| 5 | Trigger nodes must not wait for user input | Their completion is only recorded when they *execute*, not when they park — so an interactive node is an unreliable trigger. Name a non-interactive node, typically the companion's. |
| 6 | `ON_EVERY_BACKGROUND_TICK` requires a debounce > 0 | See above. |
| 7 | Not on reverse (global-node) or super-node exit edges | These manipulate the global-node caller stack in ways this path does not yet reproduce. |
| 8 | The source node must wait for user input | Otherwise the config can never fire. |
| 9 | **The source node must have no outgoing direct edges** | Direct edges take precedence on the normal transition path, so the edge would fire only in the background and never after a node execution. |

Rule 9 is the one that catches people out. It means **the companion fork must originate upstream of
the parked node**:

```
        ┌────────────► poller  (companion thread "labpoll")
        │
     entry
        │
        └────────────► chat  ──[waiting conditional]──► deliver_result
```

Put the fork on `chat` and creation fails, because `chat` would then have both an outgoing direct edge
and the waiting conditional edge.

---

## Watching it happen

Two event types tell you what the background evaluator did:

| Type | Meaning |
|---|---|
| `waiting_condition_matched` | The expression became true and the edge was taken, with no user message. |
| `waiting_evaluation_boundary` | A parked thread's edges were evaluated. `transitioned` says whether anything moved. |

```python
async for event in stream:
    if event.type == "waiting_condition_matched":
        print("advanced without a user message")
    if event.is_ready_for_input():
        break
```

`waiting_condition_matched` carries the authored `condition_expression`, the
`hydrated_condition_expression` as actually evaluated (after variable substitution), which
`trigger_mode` armed it, and `transitions_this_wait`. When a condition is not firing as expected, the
hydrated expression is the field to look at — it shows what the variables actually resolved to.

> Non-transitioning `waiting_evaluation_boundary` events are **not** persisted to the run record. They
> recur on every background pass while a thread is parked, so keeping them would grow the run document
> without bound. They still arrive on the wire.

---

## Driving it

Over WebSocket, nothing to do — the driver pumps while it waits.

Over REST you must pump, and a pump can return **main-thread assistant output** if a condition matched:

```python
responses = await client.runs.drive_background_work(workflow_id, run_id, interval_seconds=1.0)

for r in responses:
    for event in r.events:
        print(event)   # may include assistant messages, with no user turn sent
```

See [Companion threads → driving a run](companion_threads.md#driving-a-run-with-companions).

---

## Synchronous alternative

The configuration is identical — it is data, not calls. Driving differs only in the client:

```python
from interactly import WorkflowClient

client = WorkflowClient()
client.runs.drive_background_work(workflow_id, run_id, interval_seconds=1.0)
```

---

## See also

- [Companion threads](companion_threads.md) — the background thread that changes the variable
- [Self-loops](self_loops.md) — making that thread poll repeatedly
- [Nodes, edges & tools](nodes_edges_tools.md) — conditional edges and expressions

## Gotchas

- **Fork upstream of the parked node** (rule 9).
- **Freeform conditions are rejected**, not ignored — they would cost an LLM call per evaluation.
- **Do not name an interactive node as a trigger.** Its completion is recorded only when it executes,
  not when it parks.
- **`ON_EVERY_BACKGROUND_TICK` without a debounce is refused.** Prefer `ON_NODE_COMPLETION`.
- **A REST-driven run needs pumping** or the condition is never evaluated.
- **`max_transitions_per_wait` resets on each user message**, so it bounds one wait, not the run.
