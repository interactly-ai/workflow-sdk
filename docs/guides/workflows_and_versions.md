# Workflows and Versions

Workflows are executable directed graphs that define business logic. The SDK provides methods to create, list, update, delete, and clone workflows, plus manage multiple versioned snapshots of each workflow independently.

## Quick Start

```python
import asyncio
from interactly import AsyncWorkflowClient

async def main():
    async with AsyncWorkflowClient() as client:
        # Create a new workflow
        wf = await client.workflows.create(name="My Workflow", description="A test workflow")
        print(wf.id)

        # Fetch it back
        wf = await client.workflows.get(wf.id)

        # Update metadata
        wf = await client.workflows.update(wf.id, name="Updated Name")

        # Delete it
        await client.workflows.delete(wf.id)

asyncio.run(main())
```

## CRUD Operations

### Create a workflow

```python
async with AsyncWorkflowClient() as client:
    # Minimal
    wf = await client.workflows.create(name="My Workflow")

    # With description
    wf = await client.workflows.create(
        name="My Workflow",
        description="Handles customer inquiries"
    )

    # With a config dict (nodes, edges, etc.)
    config = {
        "workflow_config": {
            "name": "My Workflow",
            "description": "..."
        },
        "node_configs": [...],
        "edge_configs": [...]
    }
    wf = await client.workflows.create(config=config)
```

### Get a workflow

```python
async with AsyncWorkflowClient() as client:
    wf = await client.workflows.get("workflow_id_here")
    print(wf.name, wf.status, wf.created_at)
```

### Update a workflow

Update metadata (name, description). To modify the graph structure (nodes/edges), use versions.

```python
async with AsyncWorkflowClient() as client:
    wf = await client.workflows.update(
        wf.id,
        name="New Name",
        description="New description"
    )

    # Explicitly set description to null
    wf = await client.workflows.update(wf.id, description=None)

    # Leave fields unchanged by omitting them
    wf = await client.workflows.update(wf.id, name="Updated")
```

### Delete a workflow

Permanently deletes the workflow and all its versions.

```python
async with AsyncWorkflowClient() as client:
    await client.workflows.delete(wf.id)
```

### List workflows (paginated)

```python
async with AsyncWorkflowClient() as client:
    # First page
    page = await client.workflows.list(page=1, size=20)
    async for wf in page:
        print(wf.id, wf.name)

    # Fetch all pages
    all_workflows = await page.list_all()

    # Filter by name/description
    page = await client.workflows.list(search="customer")
```

**Pagination**: `page` is an `AsyncPage[Workflow]` object. Iterate with `async for item in page:` or collect all pages via `await page.list_all()` (returns a list).

## Cloning Workflows

Deep-copy a workflow, including all its nodes, edges, and versions.

```python
async with AsyncWorkflowClient() as client:
    # Clone with auto-generated name ("My Workflow (copy)")
    cloned = await client.workflows.clone("original_workflow_id")

    # Clone with custom name
    cloned = await client.workflows.clone("original_workflow_id", name="My New Workflow")
```

## Concurrency Control

Set the maximum number of simultaneous runs allowed for a workflow.

```python
async with AsyncWorkflowClient() as client:
    result = await client.workflows.update_concurrency(
        workflow_id="wf_123",
        max_concurrent_runs=5
    )
    # Returns: {"workflow_id": "...", "max_concurrent_runs": 5, "message": "..."}
```

## Export & Import

Export a workflow and its versions as a portable bundle, then import it elsewhere.

```python
async with AsyncWorkflowClient() as client:
    # Export versions 0, 1, 2 with version 1 as active
    bundle = await client.workflows.export(
        workflow_id="wf_123",
        version_numbers=[0, 1, 2],
        active_version_number=1
    )

    # Import the bundle into a new workflow
    imported = await client.workflows.import_bundle(
        bundle,
        versions_to_import=[0, 1, 2],
        active_version_number=1,
        workflow_name="Imported Workflow"  # optional name override
    )
```

## Schema & Dynamic Variables

### Get the workflow schema

Returns the JSON Schema for valid workflow config structures.

```python
async with AsyncWorkflowClient() as client:
    schema = await client.workflows.schema()
    # Use for form generation, validation, docs
```

### Get dynamic variables for a workflow

Returns the `{{variables}}` a caller must supply to run the workflow:

```python
async with AsyncWorkflowClient() as client:
    result = await client.workflows.dynamic_variables(workflow_id="wf_123")
    result["dynamic_variables"]          # what a run must supply, e.g. {"member_id": "", "patient": {"id": ""}}
    result["global_variables_resolved"]  # names your team's global variables already fill in
```

Variables a team global already provides are listed under `global_variables_resolved` and **removed**
from `dynamic_variables`, because the caller does not need to supply them. Only flat globals count: a
global holds a string, so it cannot satisfy a nested reference like `{{patient.id}}`. Variables used by a
tool attached by reference (its endpoint, headers or body live on the saved tool) are included.

## Checking a workflow

Two read-only questions you can ask about a stored workflow without running it. Both analyse the graph
**after super-node expansion**, and fall back to the outer graph (saying so) if expansion fails.

### Lints

The advisory checks a fully-hydrated create runs, but graph-wide. That matters for a workflow built a
node at a time: two of the checks can only be answered against the whole graph. Those two are a
cross-thread reference to a companion that does not exist, and a waiting condition that could never fire.

```python
report = await client.workflows.lints("wf_123")              # the active version
report = await client.workflows.lints("wf_123", version_number=2)
for warning in report.warnings:
    print(warning)
```

### Realtime compatibility

Whether the workflow can run its voice calls on a realtime (speech-to-speech) model:

```python
report = await client.workflows.realtime_compatibility("wf_123", model="gpt-realtime")
print(report.supported, report.summary)        # True  "Realtime-ready with 2 warning(s)."
for finding in report.blockers + report.warnings + report.indeterminate:
    print(finding.severity, finding.code, finding.description)
```

Pass the realtime `model` the call would use: the realtime protocols differ enough that a workflow can be
ready on one model and not another. Without it, the findings describe what holds on either. A super node
that could not be expanded is reported as `indeterminate` rather than assumed fine.

### Voice persona

For GPT-Live calls, `WorkflowConfig.voice_persona` says who is speaking, in two to four sentences
written as "You are …" (at most 600 characters). The voice answers most turns without consulting any
node's prompt, so this is how it knows who it is. Left empty, the server may generate one from the
workflow's prompts when a version is saved; `WorkflowConfigFullyHydrated.resolved_voice_persona()` tells
you which applies.

## Typed Config API

Create and retrieve workflows using fully-typed Pydantic models from the `[configs]` extra.

```python
from interactly.configs import WorkflowConfigFullyHydrated

async with AsyncWorkflowClient() as client:
    # Create from a typed config
    config = WorkflowConfigFullyHydrated(...)  # fully-hydrated config with nodes/edges
    wf = await client.workflows.create_from_config(
        config,
        name="Optional override"
    )

    # Fetch as a typed config
    config = await client.workflows.get_fully_hydrated("wf_123")
    # Returns: WorkflowConfigFullyHydrated instance
```

## Favorites

Mark workflows as favorites for the requesting user.

```python
async with AsyncWorkflowClient() as client:
    # Add to favorites (idempotent)
    await client.workflows.favorite(workflow_id="wf_123")

    # Remove from favorites
    await client.workflows.unfavorite(workflow_id="wf_123")

    # List favorites via search + filter
    page = await client.workflows.list(search="...")  # then filter in code
```

## Workflow Handles

A `WorkflowHandle` is a lightweight client-side object that pre-loads a workflow's config and manages the multi-turn session `run_id` for you. Useful for interactive runs (conversation-style, multiple turns).

```python
async with AsyncWorkflowClient() as client:
    # Fetch a handle pre-loaded with the hydrated config
    handle = await client.workflows.handle(
        workflow_id="wf_123",
        dynamic_variables={"name": "Alice"}
    )

    # The handle remembers the run_id between turns
    print(handle.workflow_id)
    print(handle.config)
    print(handle.run_id)  # None until first turn

    # Reset the session to start fresh
    handle.reset()

    # Use the handle with .arun() for interactive execution
    from interactly.configs import WorkflowRunInput
    run_input = WorkflowRunInput(...)
    async for event in handle.arun(run_input):
        print(event)
```

## Factory Functions

Create a workflow from a config and get a handle in one call.

```python
import asyncio
from interactly import AsyncWorkflowClient
from interactly.runtime.handle import aupload_and_get_handle
from interactly.configs import WorkflowConfigFullyHydrated

async def main():
    async with AsyncWorkflowClient() as client:
        config = WorkflowConfigFullyHydrated(...)
        handle = await aupload_and_get_handle(
            client,
            config,
            name="My Workflow",
            description="...",
            dynamic_variables={"key": "value"}
        )
        # Returns: AsyncWorkflowHandle with pre-loaded config and dynamic variables

asyncio.run(main())
```

---

## Versions

Each workflow has multiple versions. The active version is used by default when running the workflow. You manage versions via `client.workflows.versions.*`.

### Create a version

```python
async with AsyncWorkflowClient() as client:
    # Create a new version (cloned from the current active version)
    v = await client.workflows.versions.create(
        workflow_id="wf_123"
    )

    # Create with a human-readable name
    v = await client.workflows.versions.create(
        workflow_id="wf_123",
        version_name="Release 1.0"
    )

    # Clone from a specific version
    v = await client.workflows.versions.create(
        workflow_id="wf_123",
        source_version_number=0,
        version_name="Branch from v0"
    )

    # Create and immediately activate
    v = await client.workflows.versions.create(
        workflow_id="wf_123",
        mark_as_active=True
    )
```

### List versions for a workflow

```python
async with AsyncWorkflowClient() as client:
    # Returns a full list (not paginated)
    versions = await client.workflows.versions.list(workflow_id="wf_123")
    for v in versions:
        print(v.version_number, v.version_name, v.is_active)
```

### Activate a version

```python
async with AsyncWorkflowClient() as client:
    # Make version 1 the active version
    v = await client.workflows.versions.activate(
        workflow_id="wf_123",
        version_number=1
    )
```

### Update a version's name

```python
async with AsyncWorkflowClient() as client:
    v = await client.workflows.versions.update(
        workflow_id="wf_123",
        version_number=1,
        version_name="New Name"
    )
```

### Replace a version's config

```python
async with AsyncWorkflowClient() as client:
    new_config = {...}  # dict or typed NodeConfig/EdgeConfig objects
    v = await client.workflows.versions.update_config(
        workflow_id="wf_123",
        version_number=1,
        config=new_config
    )
```

### Delete a version

```python
async with AsyncWorkflowClient() as client:
    await client.workflows.versions.delete(
        workflow_id="wf_123",
        version_number=1
    )
```

### Compare two versions

```python
async with AsyncWorkflowClient() as client:
    diff = await client.workflows.versions.diff(
        workflow_id="wf_123",
        version1=0,
        version2=1
    )
    # Returns: {"version1_number": 0, "version2_number": 1, "nodes": {...}, "edges": {...}, "summary": "..."}
```

### List all active versions (team-wide)

Returns one active version per workflow across the team (paginated).

```python
async with AsyncWorkflowClient() as client:
    # Get all active versions
    page = await client.workflows.versions.list_active(page=1, size=20)

    # Filter to your workflows only
    page = await client.workflows.versions.list_active(created_by_me=True)

    # Filter to favorites
    page = await client.workflows.versions.list_active(favorites=True)

    # Filter by category
    page = await client.workflows.versions.list_active(category="Customer Service")

    # Filter by multiple categories
    page = await client.workflows.versions.list_active(categories=["Sales", "Support"])

    # Filter by workflow logical ID
    page = await client.workflows.versions.list_active(logical_id="workflow_abc123")
```

---

## Key Parameters & Options

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `name` | str | required | Workflow name |
| `description` | str | None | Human-readable summary |
| `config` | dict / WorkflowConfigOrDict | None | Full workflow + nodes + edges |
| `page` | int | 1 | Pagination index (1-indexed) |
| `size` | int | 20 | Items per page |
| `search` | str | None | Fuzzy filter on name/description |
| `max_concurrent_runs` | int | — | Max simultaneous runs |
| `version_number` | int | — | Version number (0-indexed) |
| `version_name` | str | None | Human label for version |
| `source_version_number` | int | None | Clone from this version |
| `mark_as_active` | bool | False | Immediately activate on create |
| `dynamic_variables` | dict | None | Default vars for handle |

---

## Gotchas

- **Cascading delete**: Deleting a workflow deletes all its versions and associated runs.
- **Active version required**: A workflow must always have an active version. You cannot delete the only remaining version.
- **Export format**: The bundle is a dict with keys `workflow_config`, `node_configs`, `edge_configs`, `versions`; do not modify it manually.
- **Handles are single-flight**: Do not interleave `.arun()` calls on the same handle from different async contexts. Create a new handle for each concurrent session.
- **NOT_GIVEN sentinel**: When updating, omit a field to leave it unchanged; pass `None` to explicitly set it to null.
- **`dynamic_variables()` returns an envelope**: read `["dynamic_variables"]`; names a team global already fills are under `["global_variables_resolved"]` instead.
- **Writes can carry `warnings`**: a created or imported workflow's `warnings` lists advisory lints that did not block the save. `lints()` runs the same checks on demand.

---

## See also

- [Nodes & Edges & Tools](nodes_edges_tools.md) — structure your graph
- [Running Workflows](running_workflows.md) — execute workflows (streaming, interactive, handles)
- [Monitoring Runs](monitoring_runs.md) — query run history and results
- [API Reference](../api_async.md) — full endpoint docs
- [Configs](../configs.md) — typed workflow models

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors all methods (drop the `await`, use `with` instead of `async with`):

```python
from interactly import WorkflowClient

client = WorkflowClient()

# Create a new workflow
wf = client.workflows.create(name="My Workflow", description="A test workflow")
print(wf.id)

# List workflows
page = client.workflows.list(page=1, size=20)
for wf in page:
    print(wf.id, wf.name)

# Fetch all pages
all_workflows = page.list_all()
```

For version operations, use `client.workflows.versions.*` (without `await`). See [api_sync.md](../api_sync.md) for the complete synchronous reference.
