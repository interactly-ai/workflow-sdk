# Simulations

Run workflow simulations to evaluate and compare workflow variants. A simulation runs multiple samples of a workflow and its counter-workflow under controlled conditions, then scores the results.

## Setup

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # await client.simulations.<...>
```

The `async with` block opens the client and cleanly closes it on exit. Every example
below assumes an open `client` from this block. (Prefer synchronous code? See
[Synchronous alternative](#synchronous-alternative) at the end.)

## Get the simulation schema

Retrieve the JSON Schema for a simulation configuration before creating one.

```python
schema = await client.simulations.schema()

print(schema)  # Contains 'config_schema' key
```

**Returns:**
A dict with `config_schema` key containing a JSON Schema that describes the shape of a simulation configuration.

## Create a simulation

Create a new simulation configuration that specifies the workflow to test, counter-workflow for comparison, and run parameters.

Build the config with the typed `SimulationConfig` model — field names and types are validated as you assign them:

```python
from interactly_configs.simulation import (
    SimulationConfig,
    SimulationWorkflowDetails,
)

config = SimulationConfig(
    name="Customer Support Quality",
    description="A/B testing our response strategy",
    selected_workflow=SimulationWorkflowDetails(workflow_id="workflow_abc"),
    counter_workflow=SimulationWorkflowDetails(workflow_id="workflow_xyz"),
    number_of_simulations=10,  # number of runs per workflow
)

simulation = await client.simulations.create(config=config.model_dump(exclude_none=True))

print(f"Created simulation: {simulation.id}")
```

**Dict form (also supported).** When the `[configs]` extra isn't installed, pass a plain
`SimulationConfig`-compatible `dict` instead — you just lose autocomplete and assignment-time
validation:

```python
config = {
    "name": "Customer Support Quality",
    "description": "A/B testing our response strategy",
    "selected_workflow": {"workflow_id": "workflow_abc"},
    "counter_workflow": {"workflow_id": "workflow_xyz"},
    "number_of_simulations": 10,
}

simulation = await client.simulations.create(config=config)
```

**Parameters:**
- `config`: A `SimulationConfig`-compatible dict describing the simulation (selected workflow, counter-workflow, number of simulations, timeouts, etc.). Serialise a typed `SimulationConfig` with `.model_dump(exclude_none=True)`, or pass a raw dict.

**Returns:**
A `Simulation` object with `id`, `name`, `config`, and other metadata.

## List simulations

```python
page = await client.simulations.list(
    page=1,
    size=20,
    search="Customer",  # optional: fuzzy text filter
)

async for sim in page:
    print(f"{sim.id}: {sim.name}")

# Iterate through all pages
for sim in await page.list_all():
    print(sim.id)
```

**Parameters:**
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).
- `search`: Text matched, ignoring case, against the description and the names of both workflows.
- `logical_id`: The simulation's logical id.
- `selected_workflow_id`: Only simulations of this workflow under test.
- `counter_workflow_id`: Only simulations whose simulated user is played by this workflow.
- `selected_version_number`: Only simulations naming this version of the workflow under test.
- `counter_version_number`: Only simulations naming this version of the counter workflow.
- `status`: The status the configuration records for its latest group (`Simulation.status`). A stopped or paused group is not recorded there; filter groups with `list_runs()` and their `status` instead.
- `start`, `end`: Only simulations created between these times. Give both or neither; the range may span 31 days at most.

Every filter given must match. Results are newest first. Passing only one of `start` and `end` raises `ValueError`; a range over 31 days, or an `end` before `start`, raises `BadRequestError`.

**Returns:**
An `AsyncPage` of `Simulation` objects (a `SyncPage` with the synchronous client).

## Get a single simulation

```python
simulation = await client.simulations.get("simulation_id_123")

print(f"Config: {simulation.config}")
```

**Parameters:**
- `simulation_id`: ObjectId of the simulation.

**Returns:**
A `Simulation` object.

## Update a simulation

Partially update a simulation configuration. Only `description` and `status` are updatable via the backend.

```python
updated = await client.simulations.update(
    "simulation_id_123",
    updates={"description": "Updated test description"},
)

print(f"Updated: {updated.description}")
```

**Parameters:**
- `simulation_id`: ObjectId of the simulation.
- `updates`: Dict of fields to update (typically `description` and `status`).

**Returns:**
The updated `Simulation` object.

## Delete a simulation

```python
result = await client.simulations.delete("simulation_id_123")

print(f"Deleted: {result.get('message')}")
```

**Parameters:**
- `simulation_id`: ObjectId of the simulation.

**Returns:**
A dict with a `message` field.

## Run a simulation

Trigger a new simulation batch run. This spawns multiple individual workflow runs (one per sample) for both the selected workflow and counter-workflow.

```python
run_group = await client.simulations.run(
    "simulation_id_123",
    runner_name="test-runner-001",  # optional: label for the runner
)

print(f"Started run group: {run_group.id}")
print(f"Status: {run_group.status}")
```

**Parameters:**
- `simulation_id`: ObjectId of the simulation configuration.
- `runner_name`: Optional label for the runner instance (useful for tracking which runner triggered the batch).

**Returns:**
A `SimulationGroup` object with `id`, `status`, `simulation_id`, and metadata.

## Generate a counter workflow

A simulation pits your workflow against a **counter workflow**: a set of simulated callers. The server
can write one for you from your workflow's own configuration:

```python
state = await client.workflows.generate_counter_workflow(
    workflow_id,
    num_cases=20,                 # 1-200 simulated callers
    instructions="Include callers who refuse to give a date of birth.",
    provider="gemini",            # or "claude"
)
print(state.status)               # "pending" — generation runs on the server
```

`generate_counter_workflow` **returns at once**. Generation runs in the background and makes several LLM
calls, so poll for progress:

```python
import asyncio

while True:
    status = await client.workflows.counter_workflow(workflow_id)
    generation = status.generation
    print(generation.status, generation.num_cases_generated, "/", generation.num_cases_requested)
    if generation.status in ("completed", "failed"):
        break
    await asyncio.sleep(5)

if generation.status == "completed":
    counter = status.counter_workflow
    print(counter.workflow_id, counter.case_count)   # use as the simulation's counter workflow
else:
    print("failed:", generation.error)
```

`counter_workflow()` answers both questions in one call: is a generation running, and is there already
a counter workflow to use rather than generating another. By default a regeneration is added to the
existing counter workflow as a new version; pass `new_workflow=True` for a separate one.

Two refusals to expect: a generation already running for the workflow is a `ConflictError`, and
generating from a workflow that is itself a counter workflow is a `BadRequestError`.

## List simulation runs

List all run groups (batches) for a specific simulation.

```python
runs_page = await client.simulations.list_runs(
    "simulation_id_123",
    page=1,
    size=20,
)

async for run_group in runs_page:
    print(f"{run_group.id}: {run_group.status}")

# Iterate through all pages
for run_group in await runs_page.list_all():
    print(run_group.id)
```

**Parameters:**
- `simulation_id`: ObjectId of the simulation.
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).

**Returns:**
An `AsyncPage` of `SimulationGroup` objects (a `SyncPage` with the synchronous client).

## Get evaluation summary

Get aggregated evaluation results for a simulation. Results include scores from both the selected workflow and counter-workflow.

```python
summary = await client.simulations.evaluation_summary(
    "simulation_id_123",
    group_id="group_xyz",  # optional: scope to a specific run group
)

print(f"Selected workflow summary: {summary['selected_workflow_summary']}")
print(f"Counter workflow summary: {summary['counter_workflow_summary']}")
```

**Parameters:**
- `simulation_id`: ObjectId of the simulation.
- `group_id`: Optional run group ID to scope the summary. Defaults to the latest group.

**Returns:**
A dict with:
- `simulation_id`
- `group_id`
- `selected_workflow_summary` (scores and metrics)
- `counter_workflow_summary` (scores and metrics)

## Get a single run group

Retrieve details of a specific simulation run group.

```python
run_group = await client.simulations.get_run("group_id_123")

print(f"Status: {run_group.status}")
```

**Parameters:**
- `run_id`: ObjectId of the simulation group.

**Returns:**
A `SimulationGroup` object.

## Stop a simulation run

Stop a run group for good. The group moves to `cancelled`: no simulation of it starts, and each one running ends `cancelled` before its next turn. Stopping a group that has already ended returns it unchanged. To hold a group and resume it later, use `pause_run()`.

```python
stopped = await client.simulations.stop_run("group_id_123")

print(f"Status: {stopped.status}")  # "cancelled", or the status the group had already ended with
```

**Parameters:**
- `run_id`: ObjectId of the simulation group to stop.

**Returns:**
A `SimulationGroup`: `cancelled`, or the status it ended with if it had already ended.

## Pause and resume a run

`pause_run()` holds a run group until `resume_run()`. A pending or running group moves to `paused`; pausing a paused group changes nothing. While the group is paused, no simulation of it starts or takes a turn, and the workflow runs of each simulation in flight are paused too.

```python
result = await client.simulations.pause_run("group_id_123", reason="Test window closed")
print(result.simulation_group.status)  # "paused"

for run in result.runs:
    print(run.role, run.outcome, run.status)

result = await client.simulations.resume_run("group_id_123")
print(result.simulation_group.status)  # "running"
```

**Parameters:**
- `run_id`: ObjectId of the simulation group.
- `reason` (`pause_run` only): Why the group is paused, up to 1,000 characters. It is recorded on each workflow run paused.

**Returns:**
A `SimulationRunControlResult` with:
- `simulation_group`: the group after the call.
- `runs`: one `SimulationRunControlOutcome` per workflow run in flight, with `individual_run_id`, `workflow_run_id`, `role` (`selected` for the workflow under test, `counter` for the workflow playing its user), `outcome` and `status`. It is empty when no simulation was running, such as a group paused before its first one started.

`outcome` is one of: `applied`; `already_requested` or `not_paused` (nothing to change); `not_durable` (the server's simulation runs are not durable, so the group alone holds that run); `run_ended`, `not_found` or `conflict`.

`resume_run()` moves the group back to `running`: its simulations carry on and the rest start. It lifts the pause on each workflow run in flight, however it was paused. On a group that is not paused, it only lifts those runs' pauses.

**Raises:**
- `ConflictError`: the group has ended.
- `NotFoundError`: no such group in the team.
- `PermissionDeniedError`: the caller's role is below Developer.
- `UnprocessableEntityError` (`pause_run` only): a reason over 1,000 characters.

## List individual executions

List individual workflow runs within a simulation run group.

```python
executions_page = await client.simulations.list_executions(
    "group_id_123",
    page=1,
    size=20,
)

async for execution in executions_page:
    print(f"{execution.id}")

# Iterate through all pages
for execution in await executions_page.list_all():
    print(execution.id)
```

**Parameters:**
- `run_id`: ObjectId of the simulation group.
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).

**Returns:**
An `AsyncPage` of `SimulationRun` objects (a `SyncPage` with the synchronous client).

## List detailed executions

List individual executions with hydrated workflow run details. Each execution includes the workflow name, status, evaluation run ID, and scores.

```python
detailed = await client.simulations.list_detailed_executions(
    "group_id_123",
    page=1,
    size=20,
)

for run_data in detailed:
    print(f"Run: {run_data.get('workflow_name')} → {run_data.get('status')}")
    print(f"  Score: {run_data.get('score')}")
```

**Parameters:**
- `run_id`: ObjectId of the simulation group.
- `page`: Page number (1-indexed, default 1).
- `size`: Items per page (default 20).

**Returns:**
A `list` of dicts (not paginated), each with:
- `workflow_name`
- `workflow_id`
- `status`
- `evaluation_run_id`
- `score`
- And other execution metadata.

Results are sorted ascending by run index.

## Key concepts

### Simulation hierarchy

1. **Simulation**: Configuration defining what to test (workflow IDs, run parameters, etc.).
2. **SimulationGroup**: A batch run of the simulation (multiple samples).
3. **SimulationRun**: Individual workflow execution within a group.

### Evaluation flow

When you run a simulation:
1. The system spawns N samples (runs) of the selected workflow.
2. Optionally, it also runs N samples of a counter-workflow for comparison.
3. Each run is evaluated.
4. Aggregated results are available via `evaluation_summary()`.

### Run status values

- `pending`: Waiting to start.
- `running`: Currently executing.
- `completed`: All samples finished.
- `failed`: Execution error.
- `cancelled`: Manually stopped via `stop_run()`.
- `paused`: Held by `pause_run()` until `resume_run()`. Only a run group takes this status.

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient

client = WorkflowClient()

simulation = client.simulations.create(config=config.model_dump(exclude_none=True))

run_group = client.simulations.run("simulation_id_123")

for sim in client.simulations.list(search="Customer"):
    print(sim.id)

summary = client.simulations.evaluation_summary("simulation_id_123")
```

## See also

- [Simulations API reference](../api_async.md) — endpoint documentation
- [Evaluation guide](monitoring_runs.md) — reviewing run results
- [Workflows guide](workflows_and_versions.md) — creating workflows to simulate

## Gotchas

- Only `description` and `status` can be updated on a simulation. Other fields (workflow IDs, run parameters) are immutable after creation.
- Deleting a simulation also deletes its run history. Use caution.
- `list_detailed_executions()` returns a plain list (not paginated), sorted by run index.
- Stopping a run group ends each running simulation as `cancelled` before its next turn. A group that has already ended is returned unchanged.
- `pause_run()` and `resume_run()` need the Developer role. Either one raises `ConflictError` on a group that has ended.
- `Simulation.status` records only the configuration's latest group. A stopped group leaves it `running` and a paused group is not recorded there, so `list(status="cancelled")` does not find a stopped simulation. Read the group with `get_run()` instead.
- `generate_counter_workflow()` returns before any case exists and spends LLM calls on the server; poll `counter_workflow()` rather than waiting on the call.
- One generation per workflow at a time: a second start while one is running raises `ConflictError`.
</content>
</invoke>
