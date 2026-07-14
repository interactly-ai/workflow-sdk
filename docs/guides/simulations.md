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
- `search`: Fuzzy text filter (optional).

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
    updates={
        "description": "Updated test description",
        "status": "inactive",
    }
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

Cancel a simulation run group. The orchestrator stops spawning new individual runs. Already-running runs complete naturally.

```python
stopped = await client.simulations.stop_run("group_id_123")

print(f"Status: {stopped.status}")  # Should be "cancelled"
```

**Parameters:**
- `run_id`: ObjectId of the simulation group to stop.

**Returns:**
The updated `SimulationGroup` with status `cancelled`.

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
- Stopping a run group only prevents new executions from starting; already-running executions complete naturally.
</content>
</invoke>
