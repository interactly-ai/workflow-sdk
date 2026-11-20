# Run Control

Pause, resume and cancel a durable run, approve the steps waiting for a person, send it signals, and see what it
waits on. A durable run is a scheduled run, a re-run or a background run: its state is stored between turns, so it can
wait for hours on a timer, a signal, an external job or a person.

## Setup

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # await client.runs.<...>
```

Run control lives on the runs resource. (Prefer synchronous code? See
[Synchronous alternative](#synchronous-alternative) at the end.)

Pausing, resuming, cancelling and signalling need **Developer access or above**; any role may list a run's pauses,
signals and jobs. A call from a lower role raises `PermissionDeniedError`.

---

## What a run is waiting on

```python
run = await client.runs.get(run_id)
run.status            # "waiting": parked on a timer, a signal or a job; "paused": held for a person
run.pause_requested   # True while a person's pause of the run stands
run.pause_summary     # counts by wake kind, the earliest timer, and manual_pauses: the steps awaiting approval

page = await client.runs.list_pauses(run_id, open_only=True)
for pause in page:
    print(pause.pause_id, pause.node_id, pause.wake["kind"], pause.state, pause.waits_for_person)
```

`wake["kind"]` says what ends each pause: `manual` (a person approves it), `timer`, `signal`, `external_job`, or
`run_pause` (a person's pause of the whole run). `waits_for_person` is true for the ones an approval names.

## Pausing and cancelling

```python
result = await client.runs.pause(run_id, reason="Checking the dose")
result.outcome   # "applied", or "already_requested" if a person's pause already stood
result.status    # "paused" for a waiting run; a working run keeps its status until it reaches its next node

await client.runs.cancel(run_id, reason="No longer needed")   # stored as cancelled; can't be undone
```

A working run is never interrupted mid-node: it finishes the node it is running, then pauses or stops.

## Resuming: two scopes, never mixed

```python
# 1. Lift a person's pause of the run. Steps waiting for approval keep waiting.
await client.runs.resume(run_id, note="All clear")

# 2. Approve steps waiting for a person (Pause Workflow nodes), and only them.
result = await client.runs.resume(run_id, pause_ids=[pause.pause_id], note="Approved", data={"dose_mg": 5})
result.made_ready   # the pauses approved

await client.runs.resume(run_id, all_waiting_for_person=True)   # approve every one at once
```

`note` and `data` reach the nodes that resume: a Pause Workflow node writes them to its output variables.

## Signals

A Wait for signal node waits for a signal under its key. Send one with any JSON body:

```python
result = await client.runs.send_signal(run_id, "lab.result", {"value": 7.2})
result.outcome   # "delivered": a wait took it; "stored": kept for a wait that starts later;
                 # "already_received": the same body already waits under that key
```

A signal may arrive before its wait starts: it is stored, and the wait takes it when it gets there. The node may
check the body against a schema, and a body that fails it raises `UnprocessableEntityError`.

Every post carries an `Idempotency-Key`, so a retry never delivers a signal twice. The SDK makes one per call. Pass
your own to make a retry safe across calls too, such as after a crash:

```python
result = await client.runs.send_signal(run_id, "lab.result", {"value": 7.2}, idempotency_key=f"lab-{order_id}")
result.replayed  # True when this repeats an earlier post with that key: you get the first post's answer
```

```python
async for signal in await client.runs.list_signals(run_id):
    print(signal.signal_key, signal.consumed, signal.consumed_by_pause_key)   # bodies are never returned
```

## External jobs

```python
jobs = await (await client.runs.list_external_jobs(run_id)).list_all()
for job in jobs:
    print(job.provider, job.external_ref, job.state, job.outcome)
```

## Paging

The three lists page by cursor: there is no total, and each page holds up to `limit` rows (100 by default, at most
500). Iterate a page, or call `list_all()` for every row. See [Pagination](../pagination.md#cursor-pages).

## When the server says try again

A request that arrives while the run is changing gets **409 with `Retry-After`**: nothing was recorded, and the SDK
retries it within `max_retries`. Every other 409 is raised as `ConflictError`.

A **503** means the server's store for durable runs is unavailable. It is raised at once as `InternalServerError`;
its `Retry-After` (30 seconds) is on `error.response.headers`, and whether to wait that long is yours to decide.

---

## Synchronous alternative

```python
from interactly import WorkflowClient

client = WorkflowClient()

client.runs.pause(run_id, reason="Checking the dose")
pending = [p for p in client.runs.list_pauses(run_id, open_only=True).list_all() if p.waits_for_person]
client.runs.resume(run_id, pause_ids=[p.pause_id for p in pending], data={"approved": True})
client.runs.send_signal(run_id, "lab.result", {"value": 7.2}, idempotency_key="lab-42")
client.runs.cancel(run_id)
```

---

## See also

- [Monitoring runs](monitoring_runs.md) — finding runs and reading their state
- [Webhooks](webhooks.md) — `workflow_run_paused` and `workflow_run_resumed`, to be told instead of polling
- [Error handling](../error_handling.md) — `ConflictError`, `PermissionDeniedError` and the rest

## Gotchas

- **Only durable runs.** A voice call, a chat session or a streamed run can't be paused or signalled: 409.
- **Resuming the run does not approve steps.** Lifting a person's pause leaves Pause Workflow nodes waiting; approve
  them with `pause_ids` or `all_waiting_for_person`.
- **A repeated resume is a 409.** Once nothing is paused in that scope, there is nothing to resume.
- **A signal key holds one body until a wait takes it.** Posting a different body under the same key raises
  `ConflictError`; the first one stands.
- **Signal keys** are 1 to 128 letters, digits, `_`, `.`, `:` or `-`.
- **Lists are cursor-paged, without a total.** A full page may be followed by an empty one.
