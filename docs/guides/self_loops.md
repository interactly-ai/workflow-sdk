# Self-Loops & Retries

Re-execute a node until it succeeds, a conditional edge matches, or a bound is reached — with the
bound enforced by the runtime rather than by hope.

Useful for polling an external system, retrying a flaky HTTP call, and driving a
[companion thread](companion_threads.md) that checks something repeatedly in the background.

## Setup

```python
import interactly_configs as ic
```

Authoring-time configuration; there is no resource to call.

---

## Two different things called "self loop"

These are unrelated, and the naming is unfortunate. Getting them confused is the most common mistake
here.

| | `SelfLoopConfig` (this page) | `self_loop: bool` on LLM nodes |
|---|---|---|
| Applies to | **any** node | LLM nodes only |
| Governs | re-executing the node's own work | looping back while waiting for the next user message |
| Bounded by | `max_retries` / `expiry_time` | the conversation |
| Field | `self_loop_config` | `self_loop` |

They do not interact. A `say_llm` node can have both.

---

## Adding a bounded loop

```python
node = ic.HttpRequestNodeConfig(
    name="check eligibility",
    self_loop_config=ic.SelfLoopConfig(
        enabled=True,
        max_retries=5,          # up to 6 executions total
        time_between_retries=2, # seconds between attempts
    ),
)
```

The node re-executes until **whichever comes first**:

1. an outgoing conditional edge matches — the loop's exit, and the normal way out;
2. `max_retries` re-executions have happened; or
3. the `expiry_time` wall-clock budget for the whole loop elapses.

Outgoing conditional edges are re-evaluated after every execution, which is what decides between
"exit" and "go again".

### At least one bound is required

```python
ic.SelfLoopConfig(enabled=True)                     # ValidationError
ic.SelfLoopConfig(enabled=True, max_retries=3)      # fine
ic.SelfLoopConfig(enabled=True, expiry_time=30)     # fine
ic.SelfLoopConfig(enabled=True, max_retries=3, expiry_time=30)  # fine — whichever hits first
```

This is validated **client-side**, in the SDK, so a loop that could never terminate fails at
construction rather than on the server or — worse — in production.

### Bounds

| Field | Range | Meaning |
|---|---|---|
| `max_retries` | 0–100 | Re-executions **after** the first attempt. Total attempts = `max_retries + 1`. |
| `expiry_time` | 1–3600 s | Wall-clock budget for the whole loop. |
| `time_between_retries` | 0–300 s | Delay between the end of one execution and the start of the next. |

---

## Branching on how the loop ended

When the loop stops **without** a matching exit edge, the runtime publishes a `self_loop_outcome`
runtime variable — `"max_retries"` or `"expiry_time"` — so you can route the two failures differently:

```python
edges = [
    # The happy exit: the condition finally became true.
    ic.ConditionalEdgeConfig(
        source_node_logical_id=check.logical_id,
        destination_node_logical_id=proceed.logical_id,
        condition=ic.ConditionConfig(condition_expression="[[eligibility_status]] == 'approved'"),
    ),
    # Gave up after N attempts.
    ic.ConditionalEdgeConfig(
        source_node_logical_id=check.logical_id,
        destination_node_logical_id=apologise.logical_id,
        condition=ic.ConditionConfig(condition_expression="[[self_loop_outcome]] == 'max_retries'"),
    ),
    # Ran out of time.
    ic.ConditionalEdgeConfig(
        source_node_logical_id=check.logical_id,
        destination_node_logical_id=escalate.logical_id,
        condition=ic.ConditionConfig(condition_expression="[[self_loop_outcome]] == 'expiry_time'"),
    ),
]
```

Without such an edge an exhausted loop simply stops there, which reads as the workflow stalling.

---

## `expiry_time` cannot interrupt CPU-bound work

An execution still running when the budget elapses is **terminated** — but only if it can be. A
CPU-bound inline-Python body with no `await` points cannot be interrupted mid-execution, so expiry
reliably bounds I/O-bound work (HTTP calls, EHR lookups) and does not reliably bound a tight compute
loop.

If a node might spin on CPU, bound it with `max_retries` as well.

---

## Watching a loop run

| Event | Meaning |
|---|---|
| `self_loop_delay` | About to wait `time_between_retries`. Carries `delay_seconds`, `attempt_number`. |
| `self_loop_exhausted` | Stopped on a bound. Carries `outcome` and `total_attempts`. |
| `node_expired` | An in-flight execution was terminated by `expiry_time`. |
| `companion_step_boundary` | One step of a companion's loop finished (companion threads only). |

```python
async for event in stream:
    if event.type == "self_loop_exhausted":
        print(f"gave up: {event.data}")
    if event.is_ready_for_input():
        break
```

---

## Polling in the background

The combination this was built for — a companion thread that polls, with the main conversation
carrying on:

```python
poller = ic.HttpRequestNodeConfig(
    name="poll lab results",
    self_loop_config=ic.SelfLoopConfig(
        enabled=True,
        max_retries=20,
        expiry_time=300,          # give up after five minutes either way
        time_between_retries=15,
    ),
)

# Fork it as a companion, UPSTREAM of the node that waits for the caller.
ic.DirectEdgeConfig(
    source_node_logical_id=entry.logical_id,
    destination_node_logical_id=poller.logical_id,
    companion_thread_config=ic.CompanionThreadConfig(
        is_companion_thread=True, thread_id="labpoll",
    ),
)
```

Pair it with an [evaluate-while-waiting edge](waiting_evaluation.md) so the conversation advances the
moment the result lands.

**Always give a companion loop a bound.** An unbounded one keeps the run alive indefinitely, and
because it is a background thread nobody is waiting on it to notice.

---

## Synchronous alternative

`SelfLoopConfig` is data — identical either way. Only driving the run differs; see
[Companion threads](companion_threads.md#synchronous-alternative).

---

## See also

- [Companion threads](companion_threads.md) — running the loop in the background
- [Evaluate while waiting](waiting_evaluation.md) — reacting to what the loop finds
- [Nodes, edges & tools](nodes_edges_tools.md) — node types and conditional edges

## Gotchas

- **`self_loop_config` and `self_loop` are different features.** See the table above.
- **`enabled=True` with no bound raises** at construction. That is deliberate.
- **`max_retries` counts retries, not attempts.** `max_retries=5` runs the node six times.
- **Add a `self_loop_outcome` edge**, or an exhausted loop looks like a stall.
- **`expiry_time` cannot interrupt CPU-bound inline Python.** Add `max_retries` too.
- **Never leave a companion loop unbounded** — nothing is waiting on it to notice.
