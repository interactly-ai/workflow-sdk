# Re-runs

Replay a finished run from one of its turns — optionally against a **different** workflow or version.
Useful for "what would this conversation have done if I fixed the prompt?", for reproducing a reported
problem, and for regression-checking a config change against real traffic.

## Setup

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # await client.reruns.<...>
```

The `async with` block opens the client and cleanly closes it on exit. Every example below assumes an
open `client` from this block. (Prefer synchronous code? See
[Synchronous alternative](#synchronous-alternative) at the end.)

---

## Before you start: two preconditions

Both are enforced by the server, neither is visible in the config models, and the first produces an
error message that is easy to misread. Check them before building a re-run flow.

### 1. Only WebSocket-driven runs can be re-run

Re-running reconstructs state against the config the run actually used, so the server needs that
config stored on the run. **It is saved only by the WebSocket driver** — `client.runs.stream(...)`.

A run driven through the REST `client.runs.execute(...)` path carries no snapshot, and every one of
its turns comes back as:

```
rerunnable = False
reason     = "This run predates workflow config snapshots, so its state cannot be reconstructed."
```

That wording suggests the run is simply *old*. It is not — a run created a second ago through
`execute()` says exactly the same thing. If you intend to re-run something later, drive it with
`stream()`.

### 2. Feedback needs a finished run

Ratings and comments (see [Run feedback](run_feedback.md)) are refused with **HTTP 409** while a run is
still in progress. Re-run itself is turn-scoped and does not require a terminal run, but since both
are usually used while reviewing a past conversation, they tend to surface together.

**Always check first**, rather than assuming a turn can be re-run:

```python
turns = await client.reruns.rerunnable_turns(run_id)

for turn in turns.turns:
    if turn.rerunnable:
        print(f"turn {turn.turn_index}: re-runnable ({turn.rerun_count} runs so far)")
    else:
        print(f"turn {turn.turn_index}: no — {turn.reason}")
```

`rerun_count` is how many runs have already been started from that turn — the number behind a
"3 re-runs" chip in a UI.

---

## Two ways to re-run

| | Use when | Entry point |
|---|---|---|
| **Execute** | You just want the result | `reruns.execute(...)` |
| **Token** | A human should see and adjust what carries over first | `reruns.create_token(...)` → `stream(rerun_token=...)` |

Both build their state through the same server-side projection, so they cannot disagree about what
carries over.

---

## Execute: run it and hand back the result

```python
started = await client.reruns.execute(run_id, turn_index=3)

print(started.workflow_run_id)   # the new run
print(started.status)            # "started"
print(started.resolved_mode)     # RerunMode.EXACT
```

### The `message` argument is the important one

```python
# Restore the conversation and PARK, awaiting input. This is the default.
await client.reruns.execute(run_id, turn_index=3)

# Restore, then immediately drive the turn with this message.
await client.reruns.execute(run_id, turn_index=3, message="Actually, make it next Tuesday")
```

Omitting `message` is the safe default for a reason: re-entering the restored node would repeat
whatever it already did — a tool node's API write, an outbound SMS, a booking. Supply `message` only
when you want the turn actually replayed.

By default the server answers **202 immediately** and runs in the background, because a re-run onto a
different config can outlive a request. Pass `run_async=False` to wait.

---

## Token: let a human adjust the projection first

```python
token = await client.reruns.create_token(run_id, turn_index=3)

print(token.rerun_token)             # the credential — see the warning below
print(token.expires_in_seconds)      # e.g. 900
print(token.restored_message_count)  # how much conversation carried over
```

> **`rerun_token` is a credential.** It authorises starting a run with restored state. Pass it in the
> WebSocket `start` frame; don't log it or put it in a URL you share. Mint it when you are ready to
> use it — it expires.

### Preview what it restores

```python
preview = await client.reruns.preview_token(run_id, 3, token.rerun_token)

print(preview.resume_thread_id)   # which thread the re-run continues
print(preview.threads)            # per-thread transcript + runtime variables
print(preview.edited)             # False until someone changes it
```

`preview_token` deliberately does **not** echo the token back — you already hold it, and repeating a
credential in a response body puts it somewhere the request line alone would not.

Note `resume_thread_id`: other threads are restored but not resumable, because companions are
non-interactive and terminate within their own turn.

### Amend before running

Five verbs, all optional, all applied against the transcript **as the preview showed it**:

```python
preview = await client.reruns.amend_token(
    run_id, 3, token.rerun_token,
    dynamic_variables={"customer_tier": "gold"},
    runtime_variables={"0": {"retry_count": 0}},
    message_edits=[{"thread_id": "0", "index": 2, "text": "I need it for six people"}],
    message_appends=[{"thread_id": "0", "role": "user", "text": "and a high chair"}],
    message_deletes=[{"thread_id": "0", "index": 5}],
)

print(preview.edited)          # True
print(preview.effective_mode)  # "EDITED"
```

Things worth knowing:

- **Indexes address the *displayed* transcript**, as returned by `preview_token` — not stored state.
  System prompts and tool traffic are not displayed but still occupy positions in storage; the server
  resolves your index through the same filter that produced the preview.
- **All indexes are resolved before any edit is applied**, so a multi-part amendment is not
  order-dependent.
- **Appends always go to the end.** There is no position argument, which is what makes it impossible
  to land a message between a tool call and the result answering it.
- **Deleting a turn also removes the tool results that answered it.** You cannot see that traffic, so
  you could not have asked for it.
- **You can change what a turn says, never who said it.** There is no `role` on an edit.
- **Unknown keys are rejected**, not ignored. A typo fails loudly rather than silently doing nothing
  while reporting success.

Once amended, the run is labelled `EDITED` rather than a replay — because it is a hypothetical, not a
reproduction.

### Start it

```python
from interactly.types.shared import WorkflowCommand

async with client.runs.stream(
    workflow_id=workflow_id,
    command=WorkflowCommand.START,
    rerun_token=token.rerun_token,
) as stream:
    async for event in stream:
        print(event.type, event.output)
        if event.is_ready_for_input() or event.is_terminal():
            break
```

If the token has expired, was minted for a different workflow or version, or the workflow changed
since it was created, the socket closes with code **4007** and the SDK raises `RerunTokenError`. Mint
a fresh one and retry.

---

## Re-running against a *different* config

This is where re-runs earn their keep: take yesterday's real conversation and replay it against the
prompt you just fixed.

```python
preflight = await client.reruns.preflight(
    run_id, turn_index=3,
    target_workflow_id=new_workflow_id,
    target_version_number=4,
)

print(preflight.rerunnable)                    # can it happen at all
print(preflight.resolved_mode)                 # how much fidelity is achievable
print(preflight.carries_over.message_count)    # what survives
print(preflight.dropped.node_ids)              # what does not — named, not just counted
print(preflight.unmapped_node_ids)             # nodes with no counterpart in the target
print(preflight.warnings)
```

**`preflight` has no side effects.** Call it before `execute` or `create_token` whenever the target is
a different workflow or version — `dropped` and `unmapped_node_ids` tell you concretely what would be
lost.

### Fidelity modes

`resolved_mode` is the server's verdict on how much state the target config can preserve:

| Mode | Meaning |
|---|---|
| `EXACT` | Same config as the source run. Every node id and variable carries over untouched. |
| `REMAPPED` | Different config, but nodes were matched — by id, by name, or by your `node_id_map`. |
| `PORTABLE` | No usable node correspondence. Variables and transcript carry over; position does not. |

Strictness runs `PORTABLE` < `REMAPPED` < `EXACT`. Pass `requested_mode` to insist on a minimum — if
the target cannot support it the request is **refused with a report** rather than silently doing
something lossier:

```python
await client.reruns.execute(run_id, 3, target_workflow_id=other_id, requested_mode="EXACT")
```

For `PORTABLE` re-runs there is no restored position, so name where to start:

```python
await client.reruns.execute(
    run_id, 3,
    target_workflow_id=other_id,
    entry_node_logical_id="node_triage",
)
```

`preflight.suggested_entry_nodes` proposes candidates.

### Helping the matcher

When the analyzer cannot match a renamed or ambiguous node, say so explicitly:

```python
await client.reruns.preflight(
    run_id, 3,
    target_workflow_id=other_id,
    node_id_map={"node_old_greeting": "node_new_greeting"},
)
```

`preflight.node_matches` shows what it worked out on its own, and `matched_by` says how
(`identity` / `name` / `explicit`).

### How much conversation to carry

```python
await client.reruns.execute(run_id, 3, history_mode="USER_AND_ASSISTANT_ONLY")
```

| Mode | Carries |
|---|---|
| `FULL` | Everything, including system messages. Right for a same-config replay. |
| `USER_AND_ASSISTANT_ONLY` | Drops system and tool messages. |
| `NONE` | Variables only — "same facts, fresh conversation". |

Left unset, the server picks: `FULL` when the target config is identical to the source's, and
`USER_AND_ASSISTANT_ONLY` otherwise — because the target's own nodes inject their own system prompts,
and a stale one from the old config actively misleads them.

---

## Finding the runs a re-run produced

```python
page = await client.runs.list(source_workflow_run_id=run_id)
print(f"{page.total} runs were re-run from {run_id}")

page = await client.runs.list(source_workflow_run_id=run_id, source_turn_index=3)
```

`source_turn_index` is ignored on its own — a turn index means nothing without the run it belongs to.

---

## Synchronous alternative

Every method exists on the synchronous client with the same name and arguments:

```python
from interactly import WorkflowClient

client = WorkflowClient()

turns = client.reruns.rerunnable_turns(run_id)
if any(t.rerunnable for t in turns.turns):
    preflight = client.reruns.preflight(run_id, 3)
    started = client.reruns.execute(run_id, 3)
```

---

## See also

- [Run feedback](run_feedback.md) — rating and commenting on the runs you are reviewing
- [Monitoring runs](monitoring_runs.md) — finding the run you want to re-run
- [Streaming](../streaming.md) — the WebSocket protocol and its close codes
- [Error handling](../error_handling.md) — `RerunTokenError`, `BadRequestError`

## Gotchas

- **A REST-driven run can never be re-run.** See the precondition above. The reason string blames the
  run's age, which is misleading.
- **`rerun_token` expires.** Mint it when you are about to use it, not when you build the page.
- **Amend indexes are display positions, not storage positions.** Take them from `preview_token`, not
  from your own count of messages.
- **A deleted turn takes its tool results with it.** That is usually what you want, but it means the
  resulting conversation may differ more than the visible diff suggests.
- **`requested_mode` refuses rather than degrades.** That is deliberate — a silently lossier re-run
  looks like a valid result.
- **Omitting `message` parks the run.** If nothing seems to happen after `execute`, that is why: the
  run is restored and waiting.
