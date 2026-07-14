# Monitoring Runs

After a workflow completes, query the run history, inspect outputs, evaluate results, and annotate runs with comments.

## Listing Runs

### Basic listing

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    # First page of all runs
    page = await client.runs.list(page=1, size=20)
    async for run in page:
        print(run.id, run.status, run.created_at)

    # Fetch all pages
    all_runs = await page.list_all()
```

### Filtering by workflow

```python
# Runs for a specific workflow
page = await client.runs.list(workflow_id="wf_123", size=50)
```

### Filtering by status

```python
# Completed runs
page = await client.runs.list(status="completed")

# In-progress runs
page = await client.runs.list(status="started")

# Failed runs
page = await client.runs.list(status="failed")
```

### Filtering by date range

```python
from datetime import datetime, timedelta

now = datetime.utcnow()
week_ago = now - timedelta(days=7)

page = await client.runs.list(start=week_ago, end=now)
```

### Combining filters

```python
# Completed runs for a workflow in the last 7 days
page = await client.runs.list(
    workflow_id="wf_123",
    status="completed",
    start=week_ago,
    end=now,
    size=100
)
```

### Text search

```python
# Search run metadata, inputs, outputs
page = await client.runs.list(search="error")
```

---

## Getting a Single Run

```python
run = await client.runs.get(run_id="run_123")

print(f"Status: {run.status}")
print(f"Workflow: {run.workflow_id}")
print(f"Version: {run.version_number}")
print(f"Created: {run.created_at}")
print(f"Input/Output Pairs: {len(run.input_output_pairs)}")

# Inspect input from the first turn
if run.input_output_pairs:
    pair = run.input_output_pairs[0]
    print(f"Input: {pair.run_input}")
    print(f"Output: {pair.run_output}")
    print(f"Events: {pair.run_output.events}")
```

---

## Run Structure

A `Run` contains:

- **Basic metadata**: `id`, `workflow_id`, `version_number`, `status`, `created_at`, `updated_at`
- **Multi-turn history**: `input_output_pairs` (list of `WorkflowRunInputOutputPair`)
  - Each pair has `run_input` and `run_output`
  - `run_output` contains `events` (list of runtime events)
- **Evaluation**: `evaluation_result` (optional, set after evaluation)
- **Comments**: `comments` (list of `RunComment`)

### Accessing run events

```python
run = await client.runs.get(run_id="run_123")

for pair in run.input_output_pairs:
    print(f"Turn {pair.turn_index}:")
    for event in pair.run_output.events:
        print(f"  Event: {event.type}")
        if hasattr(event, 'output'):
            print(f"    Output: {event.output}")
```

---

## Deleting Runs

Permanently delete a run record.

```python
await client.runs.delete(run_id="run_123")
```

---

## Evaluation Results

Get the evaluation result for a run (computed after completion if an evaluation LLM node is present).

```python
eval_result = await client.runs.evaluation_result(run_id="run_123")

print(f"Evaluation Status: {eval_result.status}")
print(f"Score: {eval_result.score}")
print(f"Feedback: {eval_result.feedback}")
print(f"Evaluation Time: {eval_result.evaluated_at}")
```

The evaluation result contains structured feedback from the workflow's evaluation node (if configured).

---

## Run Comments

Annotate runs with user comments for collaboration and tracking.

### Add a comment to a run

```python
comment = await client.runs.add_comment(
    run_id="run_123",
    content="This run needs review - unexpected output in turn 2"
)

print(f"Comment ID: {comment.logical_id}")
print(f"Author: {comment.created_by}")
print(f"Content: {comment.content}")
print(f"Created: {comment.created_at}")
```

### Delete a comment from a run

```python
await client.runs.delete_comment(
    run_id="run_123",
    comment_logical_id="comment_logical_id"
)
```

---

## Event Comments

Add comments to specific events within a run's event stream.

### Add a comment to an event

```python
# Find the logical_id of an event from the run's output
run = await client.runs.get(run_id="run_123")
event = run.input_output_pairs[0].run_output.events[0]
event_logical_id = event.logical_id

# Add a comment to that event
comment = await client.runs.add_event_comment(
    run_id="run_123",
    event_logical_id=event_logical_id,
    content="LLM output was truncated here"
)

print(f"Comment: {comment.content}")
```

### Delete a comment from an event

```python
await client.runs.delete_event_comment(
    run_id="run_123",
    event_logical_id="event_logical_id",
    comment_logical_id="comment_logical_id"
)
```

---

## Run Schema

Get the JSON Schemas for run structures (useful for form generation, documentation).

```python
schema = await client.runs.schema()

# Returns:
# {
#     "run_schema": {...},
#     "run_input_schema": {...},
#     "run_output_schema": {...},
#     "run_input_output_pair_schema": {...}
# }
```

---

## Common Analysis Patterns

### Find failed runs for a workflow

```python
page = await client.runs.list(workflow_id="wf_123", status="failed")

async for run in page:
    print(f"Run {run.id}: {run.error_message}")
```

### Get the latest 10 completed runs

```python
page = await client.runs.list(status="completed", size=10)

async for run in page:
    print(f"Run {run.id} finished at {run.updated_at}")
```

### Count runs by status

```python
statuses = ["started", "completed", "failed"]
counts = {}

for status in statuses:
    page = await client.runs.list(status=status, size=1)
    counts[status] = page.total  # or iterate and count manually

for status, count in counts.items():
    print(f"{status}: {count}")
```

### Extract node outputs from a run

```python
run = await client.runs.get(run_id="run_123")

for pair in run.input_output_pairs:
    for event in pair.run_output.events:
        # NodeEvent has .node_logical_id and .node_output
        if hasattr(event, 'node_logical_id'):
            print(f"Node {event.node_logical_id}: {event.node_output}")
```

### Inspect LLM usage across a run

```python
run = await client.runs.get(run_id="run_123")

total_tokens = 0
for pair in run.input_output_pairs:
    for event in pair.run_output.events:
        # LLM node events have .llm_usage_info
        if hasattr(event, 'llm_usage_info') and event.llm_usage_info:
            tokens = event.llm_usage_info.total_tokens
            total_tokens += tokens
            print(f"LLM used {tokens} tokens")

print(f"Total: {total_tokens} tokens")
```

---

## Key Parameters & Options

| Parameter | Type | Notes |
|-----------|------|-------|
| `workflow_id` | str | Filter to a specific workflow |
| `status` | str | "started", "completed", "failed", etc. |
| `start` | datetime | Start of date range (inclusive) |
| `end` | datetime | End of date range (inclusive) |
| `page` | int | 1-indexed, default 1 |
| `size` | int | Items per page, default 20 |
| `search` | str | Full-text search on content |
| `run_id` | str | ObjectId of the run |
| `event_logical_id` | str | Logical ID of the event within the run |
| `comment_logical_id` | str | Logical ID of the comment to delete |
| `content` | str | Comment text |

---

## Gotchas

- **Pagination**: The async `list()` method returns an `AsyncPage` object — `await page.list_all()` collects all pages, and `async for run in page:` iterates them. (The synchronous client returns a `SyncPage`, whose `.list_all()` is a plain call.)
- **Comments are immutable**: Once added, you can only delete them; there is no edit operation.
- **Event logical IDs**: Only accessible from within the run's event list (`pair.run_output.events[i].logical_id`), not queryable separately.
- **Evaluation results are sparse**: Not all runs have evaluation results; only workflows with evaluation nodes produce them.
- **Large runs**: If a run has thousands of event pairs, loading it in memory may be slow. Consider filtering by date or paginating the listing.

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient

client = WorkflowClient()

# List completed runs for a workflow
page = client.runs.list(workflow_id="wf_123", status="completed", size=20)
for run in page:
    print(run.id, run.status)

all_runs = page.list_all()

# Inspect a single run
run = client.runs.get(run_id="run_123")
print(run.status, len(run.input_output_pairs))
```

---

## See also

- [Running Workflows](running_workflows.md) — how to execute workflows and capture events
- [Workflows and Versions](workflows_and_versions.md) — understand the workflow structure
- [Streaming](../streaming.md) — real-time event streaming during execution
- [Runtime Events](../runtime.md) — reference for event types and structure
- [API Reference](../api_async.md) — endpoint documentation
- [Pagination](../pagination.md) — detailed pagination patterns
```