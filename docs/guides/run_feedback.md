# Run Feedback

Rate and comment on finished runs — at the level of a whole turn, or of a single event inside it.
This is the reviewing layer: how a human marks which conversations went well, and which need
attention.

## Setup

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # await client.runs.<...>
```

Feedback lives on the runs resource, not a separate one. (Prefer synchronous code? See
[Synchronous alternative](#synchronous-alternative) at the end.)

---

## Before you start: the run must be finished

Ratings and comments on a run that is **still in progress** are refused:

```python
from interactly import ConflictError

try:
    await client.runs.set_turn_rating(run_id, 0, "up")
except ConflictError as exc:
    print(exc)
    # Feedback cannot be left while the run is still in progress.
    # Wait for the run to finish and try again.
```

Check `run.status` first, or drive the run to a terminal state before reviewing it.

---

## Ratings

Three values, deliberately: a plain up/down cannot distinguish "fine" from "exactly right", and that
distinction is what makes a review set useful later.

```python
import interactly_configs as ic

ic.RatingValue.DOWN       # "down"
ic.RatingValue.UP         # "up"
ic.RatingValue.STRONG_UP  # "strong_up"
```

`ic.RATING_SCORES` maps them to numeric weights (`-1`, `1`, `2`) for aggregation. The **string** is
what gets stored, never the score — a score is derivable, and keeping the name means new values can be
added without re-interpreting old records.

### Rate a turn

```python
result = await client.runs.set_turn_rating(run_id, turn_index=2, value="up")

for rating in result.ratings:
    print(rating["value"], rating["createdBy"])
```

### Rate a single event

For finer-grained review — one bad assistant response inside an otherwise fine turn:

```python
result = await client.runs.set_event_rating(run_id, event_logical_id, value=ic.RatingValue.STRONG_UP)
```

Both accept the enum or the plain string.

### At most one rating per user per target

Re-rating **replaces** your record rather than appending. `createdBy` is effectively the identity key
within a target's rating list, so there is no "remove then add" dance.

### Remove a rating

```python
await client.runs.delete_turn_rating(run_id, turn_index=2)
await client.runs.delete_event_rating(run_id, event_logical_id)
```

---

## Comments

```python
result = await client.runs.add_turn_comment(run_id, turn_index=2, content="Missed the callback number")

for comment in result.comments:
    print(comment["logical_id"], comment["content"])
```

Content is **trimmed** before storage, and a whitespace-only comment is refused — rather than being
stored as a comment nobody can see. The cap is 5,000 characters
(`ic.MAX_COMMENT_LENGTH`), which is roughly ten dense paragraphs.

> Why a cap at all: comments are embedded in the run document, which already carries every event of
> every turn and is the thing under storage pressure. This is not a document store.

```python
await client.runs.delete_turn_comment(run_id, turn_index=2, comment_logical_id=comment_id)
```

Run-level and event-level comments have their own methods:

```python
await client.runs.add_comment(run_id, content="Reviewed — no action needed")
await client.runs.add_event_comment(run_id, event_logical_id, content="This is the bad reply")
await client.runs.delete_comment(run_id, comment_logical_id)
await client.runs.delete_event_comment(run_id, event_logical_id, comment_logical_id)
```

---

## Every write returns the whole list

Not just your record:

```python
result = await client.runs.set_turn_rating(run_id, 2, "up")

result.ratings         # every rating on that turn, one per user
result.comments        # every comment (on the comment endpoints)
result.feedback_users  # {user_id: FeedbackUser} for the authors above
```

That is what lets a UI render aggregate counts and author names immediately, without a refetch. The
response is scoped to the mutated target rather than the whole run — a thumbs-up does not justify
shipping back every event of every turn.

```python
for rating in result.ratings:
    author = result.feedback_users.get(rating["createdBy"])
    name = f"{author.firstName} {author.lastName}" if author else "unknown"
    print(f"{name}: {rating['value']}")
```

`FeedbackUser` carries only `id`, `firstName`, `lastName`, `email` — a run response should not become
an access path to the user directory. Ids that no longer resolve are simply absent from the map, so
look them up with `.get()` rather than `[]`.

Fetching a run brings the same map:

```python
run = await client.runs.get(run_id)
run.feedback_users
```

---

## Reading feedback back

Turn-level feedback lives on each input/output pair:

```python
run = await client.runs.get(run_id)

for i, pair in enumerate(run.input_output_pairs):
    if pair.ratings or pair.comments:
        print(f"turn {i}: {[r.value for r in pair.ratings]}")
        for comment in pair.comments:
            print(f"  — {comment.content}")
```

Event-level feedback lives on the events inside `pair.run_output.events`.

---

## A review loop

Rate what you find, then re-run the ones that went wrong:

```python
page = await client.runs.list(workflow_id=workflow_id, status="completed", size=50)

async for run in page:
    detail = await client.runs.get(run.id)
    if detail.error:
        await client.runs.set_turn_rating(run.id, 0, ic.RatingValue.DOWN)
        await client.runs.add_turn_comment(run.id, 0, f"Failed: {detail.error}")

        # Only WS-driven runs can be re-run — see the re-runs guide.
        turns = await client.reruns.rerunnable_turns(run.id)
        if any(t.rerunnable for t in turns.turns):
            await client.reruns.execute(run.id, turn_index=0)
```

See [Re-runs](reruns.md) for what `rerunnable` depends on.

---

## Synchronous alternative

```python
from interactly import WorkflowClient

client = WorkflowClient()

result = client.runs.set_turn_rating(run_id, 2, "up")
client.runs.add_turn_comment(run_id, 2, "Missed the callback number")
client.runs.delete_turn_rating(run_id, 2)
```

---

## See also

- [Monitoring runs](monitoring_runs.md) — finding runs worth reviewing
- [Re-runs](reruns.md) — replaying the ones that went wrong
- [Error handling](../error_handling.md) — `ConflictError` and the rest

## Gotchas

- **Feedback needs a finished run** — an in-flight run gives you 409.
- **Re-rating replaces**; it does not append. There is no duplicate to clean up.
- **Blank comments are refused**, and content is trimmed before storage.
- **`feedback_users` can miss an id** if the user no longer resolves. Use `.get()`.
- **Turn index, not turn id.** `turn_index` is the 0-based position in `input_output_pairs`.
- **Ratings are per user.** `result.ratings` is everyone's, not just yours — filter by `createdBy` if
  you want your own.
