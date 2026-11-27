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

    # Filter by type, category, logical id, creator or favourites (every filter given must match)
    page = await client.workflows.list(workflow_type="evaluation")
    page = await client.workflows.list(categories=["Sales"], favorites=True)
    page = await client.workflows.list(logical_id="workflow_abc123")
```

**Pagination**: `page` is an `AsyncPage[Workflow]` object. Iterate with `async for item in page:` or collect all pages via `await page.list_all()` (returns a list).

**Workflow type**: `workflow_type` is `standard` (the workflows that run calls) or `evaluation` (post-call analysis, see [Evaluation workflows](#evaluation-workflows)). The server lists `standard` workflows unless `evaluation` is asked for.

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

### Secrets in a bundle

By default `export()` clears the workflow's secrets: a secret field becomes `None`, and a sensitive header or body entry (an `Authorization` header, say) becomes `""`. Each cleared value is listed in `bundle["redactions"]` as `{"path", "reason", "node_name", "segments"}`, and `bundle["secrets_included"]` is `False`.

```python
async with AsyncWorkflowClient() as client:
    bundle = await client.workflows.export(
        workflow_id="wf_123",
        version_numbers=[0],
        active_version_number=0,
    )
    for redaction in bundle["redactions"]:
        print(redaction["path"], redaction["reason"])

    # Supply each cleared value again on import, keyed by its path
    # (supplied: your own dict of values, keyed by redaction path)
    imported = await client.workflows.import_bundle(
        bundle,
        secret_overrides={r["path"]: supplied[r["path"]] for r in bundle["redactions"]},
    )
    for warning in imported.warnings:
        print(warning)   # a secret not supplied stays empty, and is named here
```

- `include_secrets=True` keeps the secrets in the bundle, in plain text. Anything that stores the bundle then holds the workflow's credentials. A viewer asking for them gets `PermissionDeniedError`.
- In a `secret_overrides` path, the number after `versions.` is the version's position in `bundle["versions"]`, not its version number.
- A blank value counts as not supplied. A secret not supplied stays empty and adds a line to the imported workflow's `warnings`.
- A path the bundle does not list raises `UnprocessableEntityError`; `err.body["field_errors"]` names the paths.

## Usage

`usage()` lists the team's workflows that use this one, in any version: as a super node's workflow, an evaluator, or a warm-transfer target.

```python
async with AsyncWorkflowClient() as client:
    report = await client.workflows.usage("wf_123")
    for entry in report.used_by:
        print(entry.workflow_id, entry.name, entry.version_numbers)
```

A delete does not consult this: deleting the workflow still succeeds and leaves these workflows with a reference that no longer resolves. An id that names no workflow returns an empty report.

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

    # The variables of one version; without version_number the server reads the workflow's own record
    result = await client.workflows.dynamic_variables(workflow_id="wf_123", version_number=2)
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

    # Hydrate one version rather than the workflow's own record
    config = await client.workflows.get_fully_hydrated("wf_123", version_number=2)
```

## Favorites

Mark workflows as favorites for the requesting user.

```python
async with AsyncWorkflowClient() as client:
    # Add to favorites (idempotent)
    await client.workflows.favorite(workflow_id="wf_123")

    # Remove from favorites
    await client.workflows.unfavorite(workflow_id="wf_123")

    # List the workflows the calling user favourited
    page = await client.workflows.list(favorites=True)
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
    # Create a new version, cloned from the current active version. version_name is required.
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
        version_name="Release 1.1",
        mark_as_active=True
    )
```

### Get one version

`get()` returns one version's name and its settings snapshot (`config`, a `WorkflowConfig`). It raises `NotFoundError`
if the workflow or the version does not exist.

```python
async with AsyncWorkflowClient() as client:
    v = await client.workflows.versions.get("wf_123", 1)
    print(v.version_name, v.config)
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

### Update a version's settings

`update_config` changes a version's workflow-level settings (name, description, category, the global LLM config,
`tools_config`, ...). Only the settings given change: a typed `WorkflowConfig` sends the fields set on it, and a dict
sends its keys. A new `category` reaches every version of the workflow.

Nodes and edges are not settings. A `config` holding them raises `ValueError`; change them through `client.nodes` and
`client.edges`. If the update removed global tools, the returned version's `pruned_global_tool_exclusions` lists the
nodes whose exclusions of those tools were dropped.

```python
async with AsyncWorkflowClient() as client:
    v = await client.workflows.versions.update_config(
        workflow_id="wf_123",
        version_number=1,
        config={"description": "Books and reschedules appointments"},  # or a typed WorkflowConfig
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

    # Filter to workflows created by given users (user ids; with an API key, yours is its creator's id)
    page = await client.workflows.versions.list_active(created_by=["<user_id>"])

    # Search names, descriptions and categories
    page = await client.workflows.versions.list_active(search="intake")

    # Filter to favorites
    page = await client.workflows.versions.list_active(favorites=True)

    # Filter by multiple categories
    page = await client.workflows.versions.list_active(categories=["Sales", "Support"])

    # Filter by workflow logical ID
    page = await client.workflows.versions.list_active(logical_id="workflow_abc123")

    # Evaluation workflows instead of standard ones
    page = await client.workflows.versions.list_active(workflow_type="evaluation")
```

---

## Evaluation workflows

An evaluation workflow analyses a finished conversation (a summary, a success verdict, structured data) and stores
what it finds. It never runs on a live call. Once created, it is an ordinary workflow to `client.workflows`.

```python
async with AsyncWorkflowClient() as client:
    templates = await client.evaluation_workflows.templates()
    presets = await client.evaluation_workflows.node_presets()   # the ready-made analysis nodes

    wf = await client.evaluation_workflows.create_from_template(
        template_id=templates[0].template_id,
        name="Call summary",
    )                                                            # version 0 is active

    evaluators = await client.evaluation_workflows.list()        # the team's evaluation workflows, not paged

    # The same workflows through the standard list
    page = await client.workflows.list(workflow_type="evaluation")
```

- `templates()`: the templates a new evaluation workflow can start from. Each has a `template_id`.
- `node_presets()`: the ready-made analysis nodes, in the order a workflow usually uses them.
- `create_from_template(template_id=, name=)`: `NotFoundError` for an unknown template; `BadRequestError` when the
  template uses a node type this server has not enabled.
- `list()`: each evaluation workflow with its versions and whether it masks PHI.

`WorkflowType` has two values: `standard` (the default, the workflows that run calls) and `evaluation`.

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
| `version_name` | str | required on create | Version label; the server refuses a version without one |
| `source_version_number` | int | None | Clone from this version |
| `mark_as_active` | bool | False | Immediately activate on create |
| `dynamic_variables` | dict | None | Default vars for handle |
| `workflow_type` | str | `standard` | List filter: `standard` or `evaluation` |
| `include_secrets` | bool | False | Export: keep secrets in the bundle, in plain text (viewers refused) |
| `secret_overrides` | dict | None | Import: cleared secret values, keyed by their `redactions` path |

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

---

## See also

- [Nodes & Edges & Tools](nodes_edges_tools.md) — structure your graph
- [Running Workflows](running_workflows.md) — execute workflows (streaming, interactive, handles)
- [Monitoring Runs](monitoring_runs.md) — query run history and results
- [API Reference](../api_async.md) — full endpoint docs
- [Configs](../configs.md) — typed workflow models

---

## Gotchas

- **Cascading delete**: Deleting a workflow deletes all its versions and associated runs.
- **Active version required**: A workflow must always have an active version. You cannot delete the only remaining version.
- **Export format**: The bundle (`export_format` `"v2"`) is a dict with `versions`, `active_version_number`, `source_workflow_id`, `source_workflow_name`, `exported_at`, `redactions`, `secrets_included` and `warnings`. Each entry in `versions` holds a `version_number`, a `version_name` and a fully-hydrated `workflow_config` (with its own `node_configs` and `edge_configs`). Treat it as opaque and do not modify it by hand; read `warnings` for anything the export stripped or could not resolve.
- **Handles are single-flight**: Do not interleave `.arun()` calls on the same handle from different async contexts. Create a new handle for each concurrent session.
- **NOT_GIVEN sentinel**: When updating, omit a field to leave it unchanged; pass `None` to explicitly set it to null.
- **`dynamic_variables()` returns an envelope**: read `["dynamic_variables"]`; names a team global already fills are under `["global_variables_resolved"]` instead.
- **Writes can carry `warnings`**: a created or imported workflow's `warnings` lists advisory lints that did not block the save. `lints()` runs the same checks on demand.
- **Writes can carry `pruned_global_tool_exclusions`**: a write that removed global tools lists the nodes whose exclusions of them it dropped.
- **Secrets are cleared by default**: an export without `include_secrets=True` carries no secret values. Supply them again with `secret_overrides` on import, or the imported workflow has them empty.
