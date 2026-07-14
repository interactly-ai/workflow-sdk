# Scheduling Workflows

Schedule workflows to run at a future UTC time using one-shot scheduled runs. Use the Schedules API to create, list, update, and cancel scheduled executions.

## Setup

```python
from interactly import AsyncWorkflowClient
from datetime import datetime, timedelta

async with AsyncWorkflowClient() as client:
    # All examples use this pattern
    ...
```

## Create a scheduled run

Schedule a workflow to run at a specific future UTC time.

```python
import asyncio
from datetime import datetime, timedelta
from interactly import AsyncWorkflowClient

async def main():
    async with AsyncWorkflowClient() as client:
        # Schedule for 1 hour from now
        scheduled_time = datetime.utcnow() + timedelta(hours=1)
        
        schedule = await client.schedules.create(
            workflow_id="workflow_123",
            scheduled_time=scheduled_time,
            run_input={"user_id": "user_456", "action": "notify"},
            version=3,  # optional: specific workflow version
            scheduled_by_name="alice@example.com",  # optional: for audit UI
        )
        
        print(f"Scheduled: {schedule.id}")

asyncio.run(main())
```

**Parameters:**
- `workflow_id`: The workflow to schedule.
- `scheduled_time`: A `datetime` object (interpreted as UTC). ISO-formatted string is sent to the API.
- `run_input`: Optional workflow input payload. Can be a dict or a typed config object (see [house style](../03_concepts.md#house-style-async-first-typed-first)).
- `version`: Optional. Specifies the workflow version to use. Defaults to the active version.
- `scheduled_by_name`: Optional. Display name of the scheduling user (for audit purposes in the dashboard).

**Returns:**
A `Schedule` object with `id`, `status`, `scheduled_time`, `workflow_id`, and other metadata.

## List scheduled runs

### List schedules for a specific workflow

```python
async with AsyncWorkflowClient() as client:
    schedules = await client.schedules.list(
        workflow_id="workflow_123",
        status="pending",  # optional: filter by status
        skip=0,
        limit=50,
    )
    
    for schedule in schedules:
        print(f"{schedule.id}: {schedule.scheduled_time} ({schedule.status})")
```

**Parameters:**
- `workflow_id`: The workflow to list schedules for.
- `status`: Optional. Filter by schedule status (e.g., `"pending"`, `"completed"`, `"failed"`). Use `ScheduleStatus` enum.
- `skip`: Offset for pagination (default 0).
- `limit`: Max items per call (1–100, default 50).

**Returns:**
A `list` of `Schedule` objects (not paginated; use `skip`/`limit` for windowing).

### List all team schedules

```python
async with AsyncWorkflowClient() as client:
    all_schedules = await client.schedules.list_all(
        status="pending",  # optional
        skip=0,
        limit=50,
    )
    
    for schedule in all_schedules:
        print(f"{schedule.workflow_id}: {schedule.scheduled_time}")
```

**Parameters:**
Same as `list()`, but covers all workflows in your team.

## Get a single schedule

```python
async with AsyncWorkflowClient() as client:
    schedule = await client.schedules.get("schedule_id_123")
    
    print(f"Workflow: {schedule.workflow_id}")
    print(f"Status: {schedule.status}")
    print(f"Scheduled for: {schedule.scheduled_time}")
```

**Parameters:**
- `schedule_id`: ObjectId of the schedule.

**Returns:**
A single `Schedule` object.

**Raises:**
`NotFoundError` if the schedule does not exist.

## Update a scheduled run

Modify a pending scheduled run. Only `PENDING` schedules can be updated. Changing `scheduled_time` re-creates the underlying AWS EventBridge schedule.

```python
async with AsyncWorkflowClient() as client:
    updated_schedule = await client.schedules.update(
        "schedule_id_123",
        scheduled_time=datetime.utcnow() + timedelta(hours=2),
        run_input={"user_id": "user_789"},
        version=4,
    )
    
    print(f"Updated: {updated_schedule.scheduled_time}")
```

**Parameters:**
- `schedule_id`: The schedule to update.
- `scheduled_time`: New future UTC datetime (optional).
- `run_input`: New workflow input (optional).
- `version`: New workflow version (optional).

All parameters are optional; omitted fields retain their current values.

**Returns:**
The updated `Schedule` object.

## Cancel a scheduled run

```python
async with AsyncWorkflowClient() as client:
    await client.schedules.cancel("schedule_id_123")
    print("Schedule cancelled")
```

**Parameters:**
- `schedule_id`: ObjectId of the schedule to cancel.

**Returns:**
`None` on success.

## Key concepts

### One-shot semantics

Schedules are **one-time runs**. When the `scheduled_time` arrives, the server triggers the workflow once and transitions the schedule to `COMPLETED` or `FAILED`. To repeat a workflow, create multiple schedules.

### Status values

- `PENDING`: Scheduled but not yet executed.
- `COMPLETED`: Run finished (successfully or not).
- `FAILED`: Scheduling system error or the run errored.
- `CANCELLED`: Manually cancelled via `cancel()`.

### UTC times

Always pass `scheduled_time` as a UTC `datetime`. The API interprets it as UTC and triggers execution at that UTC instant.

### Versioning

Pass `version` to use a specific workflow version. Omit it to use the currently active version. Changing the version in `update()` applies only to this scheduled run; the workflow's active version is unchanged.

## See also

- [Workflows guide](workflows_and_versions.md) — creating and managing workflows
- [Runs guide](../api_async.md) — inspecting workflow execution history
- [Running workflows](running_workflows.md) — immediate execution vs. scheduled

## Gotchas

- Scheduling a workflow in the past (or a time that has already passed) may cause unexpected behavior. Always use future times.
- Only `PENDING` schedules can be updated. Once a schedule is `COMPLETED` or `FAILED`, modifications are rejected.
- The `scheduled_by_name` field is for audit/UI purposes only; it does not affect permissions or execution.

## Synchronous alternative

Use `WorkflowClient` instead of `AsyncWorkflowClient`, and drop `async`/`await`:

```python
from interactly import WorkflowClient
from datetime import datetime, timedelta

client = WorkflowClient()
schedule = client.schedules.create(
    workflow_id="workflow_123",
    scheduled_time=datetime.utcnow() + timedelta(hours=1),
)
schedules = client.schedules.list(workflow_id="workflow_123")
client.schedules.cancel("schedule_id_123")
```
