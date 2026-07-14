# Running Workflows

There are three ways to run a workflow: **streaming** (WebSocket, real-time events), **interactive HTTP** (turn-by-turn), and **handles** (pre-loaded, session-aware). Choose streaming for watching all events unfold, interactive execution for turn-by-turn control, or handles for multi-turn conversations with persistent state.

## Streaming (WebSocket)

The streaming API opens a persistent WebSocket connection that pushes `RunEvent` objects as the workflow executes. Ideal for real-time feedback and monitoring.

```python
from interactly import AsyncWorkflowClient, WorkflowCommand

async with AsyncWorkflowClient() as client:
    async with client.runs.stream(
        workflow_id="wf_123",
        command=WorkflowCommand.START
    ) as stream:
        async for event in stream:
            print(f"Event: {event.type}")
            if hasattr(event, 'output'):
                print(f"Output: {event.output}")
            if event.is_terminal():
                break
```

### Stream parameters

```python
stream = client.runs.stream(
    workflow_id="wf_123",
    command=WorkflowCommand.START,  # default; use "stop" to cancel
    run_by="api",                    # caller identifier
    version_number=2,                # optional; defaults to active version
    cast_to=RunEvent                 # Pydantic model for typed events (default)
)
```

### Stream vs execute trade-offs

| Aspect | Streaming | Interactive HTTP |
|--------|-----------|------------------|
| **Real-time** | Yes (WebSocket) | No (polling) |
| **Setup** | More complex (WebSocket) | Simple HTTP |
| **Session management** | Server-initiated closure | Manual `run_id` echo |
| **Large outputs** | Streaming frames | Full response body |
| **Ideal for** | Live monitoring, chat UIs | Turn-by-turn workflows |

---

## Interactive Execution (HTTP)

The `execute()` method runs one turn of a workflow session over HTTP and returns the result. Multi-turn workflows require echoing the `run_id` to resume the session.

### Single-turn execution

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    response = await client.runs.execute(
        workflow_id="wf_123",
        command="start"  # or WorkflowCommand.START
    )

    print(f"Status: {response.status}")
    print(f"Is waiting for input? {response.is_waiting_for_input}")
    print(f"Is completed? {response.is_completed}")
    print(f"Events: {response.events}")
    print(f"Run ID: {response.run_id}")  # Save this for the next turn
```

### Multi-turn execution

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    # Turn 1: Start the session
    response = await client.runs.execute(
        workflow_id="wf_123",
        command="start"
    )
    run_id = response.run_id
    print(f"Turn 1 response: {response.status}")

    # Turn 2+: Resume with the same run_id
    while not response.is_completed:
        response = await client.runs.execute(
            workflow_id="wf_123",
            run_id=run_id,  # Echo the run_id to resume
            command="start",
            dynamic_variables={"user_input": "Some reply"}
        )
        print(f"Turn response: {response.status}")
        if response.is_completed:
            break
```

### Passing variables

```python
response = await client.runs.execute(
    workflow_id="wf_123",
    command="start",
    run_by="user_123",
    version_number=2,  # optional; use active by default
    dynamic_variables={
        "customer_name": "Alice",
        "order_id": "ORD-456"
    },
    runtime_variables={
        "session_token": "abc123"
    },
    miscellaneous={
        "metadata": {"source": "API"}
    }
)
```

---

## Typed Execution (WorkflowRunInput)

For multi-turn runs that inject per-thread node inputs (LLM messages, etc.), use `execute_with_input()` with a typed `WorkflowRunInput`:

```python
from interactly import AsyncWorkflowClient
from interactly.configs import WorkflowRunInput

async with AsyncWorkflowClient() as client:
    # Create a typed run input
    run_input = WorkflowRunInput(
        command="start",
        dynamic_variables={"name": "Alice"},
        thread_to_node_inputs={
            "thread_0": {
                "llm_node_1": {"messages": [{"role": "user", "content": "Hello"}]}
            }
        }
    )

    response = await client.runs.execute_with_input(
        workflow_id="wf_123",
        run_input=run_input
    )
```

This is the transport layer used internally by `WorkflowHandle` and is exposed for advanced use cases.

---

## Workflow Handles

A `WorkflowHandle` is a lightweight wrapper that:
1. Pre-loads the workflow's hydrated config
2. Persists the `run_id` across turns
3. Merges dynamic variables (defaults + per-turn overrides)

Ideal for multi-turn interactive workflows where you want the SDK to manage session state.

### Create a handle

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    # Fetch the workflow and pre-load its config
    handle = await client.workflows.handle(
        workflow_id="wf_123",
        dynamic_variables={"default_name": "Alice"}  # optional defaults
    )

    print(handle.workflow_id)
    print(handle.config)  # WorkflowConfigFullyHydrated
    print(handle.run_id)  # None until first turn
```

### Run the handle

```python
from interactly import AsyncWorkflowClient
from interactly.configs import WorkflowRunInput

async with AsyncWorkflowClient() as client:
    handle = await client.workflows.handle(workflow_id="wf_123")
    
    run_input = WorkflowRunInput(
        command="start",
        dynamic_variables={"user_message": "Hello"}
    )

    # Iterate over typed events
    async for event in handle.arun(run_input):
        print(f"Event: {event.type}")

    # The handle now stores the run_id internally
    print(f"Run ID: {handle.run_id}")

    # Next turn: dynamic_variables are merged with defaults
    next_input = WorkflowRunInput(
        command="continue",
        dynamic_variables={"user_message": "How are you?"}
    )

    async for event in handle.arun(next_input):
        print(f"Event: {event.type}")
```

### Reset the session

Forget the current `run_id` to start a fresh session on the next `.arun()` call.

```python
handle.reset()
print(handle.run_id)  # None again
```

### Handle factory functions

Create a workflow from a config and get a handle in one call:

```python
from interactly import AsyncWorkflowClient
from interactly.runtime.handle import aupload_and_get_handle
from interactly.configs import WorkflowConfigFullyHydrated

config = WorkflowConfigFullyHydrated(...)

async with AsyncWorkflowClient() as client:
    handle = await aupload_and_get_handle(
        client,
        config,
        name="My Workflow",
        description="Test workflow",
        dynamic_variables={"key": "value"}
    )

    # Handle is ready to use
    run_input = WorkflowRunInput(command="start")
    async for event in handle.arun(run_input):
        print(event)
```

---

## Checkpointing & Branching

Resume execution from a specific turn in a past run, creating a new branched run.

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    # Create a new run branching from turn 2 of an existing run
    new_run = await client.runs.checkpoint(
        workflow_id="wf_123",
        run_id="old_run_id",
        resume_turn_index=2  # 0-based; inherits turns 0, 1, 2
    )

    print(new_run.id)  # New run ID
    print(new_run.status)  # "started"

    # Optionally start from a specific node
    new_run = await client.runs.checkpoint(
        workflow_id="wf_123",
        run_id="old_run_id",
        resume_turn_index=2,
        start_node_logical_id="some_node"
    )
```

---

## Run Metadata

### Get schema for run structures

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    schema = await client.runs.schema()
    # Returns: {
    #     "run_schema": {...},
    #     "run_input_schema": {...},
    #     "run_output_schema": {...},
    #     "run_input_output_pair_schema": {...}
    # }
```

---

## Advanced: WorkflowCommand Enum

Valid commands (use the enum or string equivalents):

```python
from interactly import WorkflowCommand

# Equivalent forms:
command = WorkflowCommand.START      # enum
command = "start"                     # string

# Other commands:
# WorkflowCommand.STOP
# WorkflowCommand.PAUSE
# ... (check the enum for all available)
```

---

## Common Patterns

### Pattern 1: Wait for completion (streaming)

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    async with client.runs.stream(workflow_id="wf_123") as stream:
        async for event in stream:
            print(event.type)
            if event.is_terminal():
                print("Workflow completed")
                break
```

### Pattern 2: Turn-by-turn with early exit

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    response = await client.runs.execute(workflow_id="wf_123", command="start")

    for turn in range(10):
        if response.is_completed:
            break
        
        response = await client.runs.execute(
            workflow_id=response.workflow_id,
            run_id=response.run_id,
            command="start"
        )
```

### Pattern 3: Multi-turn conversation with a handle

```python
from interactly import AsyncWorkflowClient
from interactly.configs import WorkflowRunInput

async with AsyncWorkflowClient() as client:
    handle = await client.workflows.handle(workflow_id="wf_123")

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "What can you do?"},
    ]

    for msg in messages:
        run_input = WorkflowRunInput(
            command="continue",
            dynamic_variables={"message": msg["content"]}
        )
        
        events = []
        async for event in handle.arun(run_input):
            events.append(event)
            print(event)
```

---

## Key Parameters & Options

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `workflow_id` | str | required | Target workflow |
| `command` | str / WorkflowCommand | "start" | Workflow command |
| `run_by` | str | "api" | Caller identifier |
| `version_number` | int | None | Use this version (default: active) |
| `dynamic_variables` | dict | {} | Template placeholders |
| `runtime_variables` | dict | {} | Runtime overrides |
| `miscellaneous` | dict | {} | Arbitrary metadata |
| `run_id` | str | None | Resume session (omit on first turn) |
| `resume_turn_index` | int | — | Checkpoint: resume from this turn |
| `start_node_logical_id` | str | None | Checkpoint: start from this node |

---

## Gotchas

- **Streaming requires WebSocket**: Install with `pip install 'interactly[stream]'` to use `.stream()`.
- **Handles are single-flight**: Do not interleave `.arun()` calls on the same handle from different tasks. Create a new handle per concurrent session.
- **Variable merging**: When using handles, per-turn `dynamic_variables` override the handle's defaults at the leaf level (deep merge).
- **Turn index is 0-based**: In `.checkpoint()`, `resume_turn_index=0` includes only the first turn's pair.
- **Async lock on handles**: `AsyncWorkflowHandle.arun()` uses an internal lock to serialize turns, preventing orphaned sessions if concurrent `.arun()` calls happen by accident.

---

## See also

- [Workflows and Versions](workflows_and_versions.md) — manage workflows and versions
- [Monitoring Runs](monitoring_runs.md) — query past runs and results
- [Streaming](../streaming.md) — detailed WebSocket protocol docs
- [Runtime Events](../runtime.md) — event types and parsing
- [API Reference](../api_async.md) — full endpoint reference
- [Configs](../configs.md) — WorkflowRunInput and event models

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and `async with`:

```python
from interactly import WorkflowClient

client = WorkflowClient()

# Streaming
with client.runs.stream(workflow_id="wf_123") as stream:
    for event in stream:
        print(event.type)
        if event.is_terminal():
            break

# Execution
response = client.runs.execute(workflow_id="wf_123", command="start")
print(response.status)

# Handle
handle = client.workflows.handle(workflow_id="wf_123")
for event in handle.run(run_input):
    print(event)
```

Note: Use `handle.run()` instead of `handle.arun()` and `page.list_all()` (not `await page.list_all()`).
