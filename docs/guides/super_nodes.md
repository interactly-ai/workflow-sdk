# Super Nodes

A super node is a published workflow that can be embedded inside another workflow as a reusable node. This guide shows how to publish a workflow as a super node, reference it in other workflows, and manage the published versions.

## What is a super node?

A super node wraps a complete workflow with a defined interface (input fields) so it can be used as a single node inside parent workflows. This enables:
- **Reusable sub-workflows** across teams and projects
- **Encapsulation** of complex logic into a single node
- **Interface contracts** that decouple sub-workflow internals from parent workflows

## Publish a workflow as a super node

All examples below use the asynchronous `AsyncWorkflowClient`. Open it with `async with` so the underlying HTTP session is cleaned up on exit, then `await` each call. The `client` established here is reused throughout this guide.

To publish a workflow as a super node, define its input interface and call `publish()`:

```python
from interactly import AsyncWorkflowClient

# Define the input interface: map workflow input fields to sub-workflow variables
interface = {
    "field_values": [
        {
            "name": "member_id",
            "type": "string",
            "description": "Member's unique identifier",
            "map_to": "dynamic_variable:member_id",
        },
        {
            "name": "reason_for_contact",
            "type": "string",
            "description": "Why the member is contacting",
            "map_to": "dynamic_variable:reason",
        },
    ]
}

async with AsyncWorkflowClient() as client:
    result = await client.super_nodes.publish(
        workflow_id="<workflow_id>",
        interface=interface,
    )
    print(f"Published version {result['workflow_version_number']}")
```

The return dict contains:
- `workflow_id` — the published workflow's ID
- `workflow_version_number` — the version snapshot created
- `num_input_fields` — count of interface fields
- `message` — human-readable confirmation

## Get super node details

Retrieve the full published definition, including the hydrated workflow config:

```python
super_node = await client.super_nodes.get(workflow_id="<workflow_id>")

print(f"Name: {super_node.name}")
print(f"Version: {super_node.workflow_version_number}")
print(f"Interface: {super_node.super_node_interface}")
# Access the encapsulated workflow config (if interactly[configs] is installed)
if super_node.encapsulated_workflow_config:
    print(f"Config nodes: {len(super_node.encapsulated_workflow_config.nodes)}")
```

To fetch a specific version:

```python
super_node = await client.super_nodes.get(
    workflow_id="<workflow_id>",
    version_number=2,
)
```

## Get the schema for embedding

Retrieve the JSON Schema describing a super node's input fields for rendering in editors:

```python
schema = await client.super_nodes.schema(workflow_id="<workflow_id>")
print(schema)  # {"type": "object", "properties": {...}}
```

## List all published super nodes

Get all super nodes published by your team:

```python
super_nodes = await client.super_nodes.list()

for sn in super_nodes:
    print(f"{sn.name} (v{sn.workflow_version_number}): {sn.num_input_fields} inputs")
```

This returns a full list (not paginated).

## Preview expanded config

Preview a workflow with all embedded super nodes flattened into nodes and edges (useful for validation):

```python
preview = await client.super_nodes.expand_preview(workflow_id="<workflow_id>")

print(f"Expanded nodes: {len(preview.expanded_config.nodes)}")
print(f"Super node origins: {preview.super_node_origins}")
print(f"Report: {preview.expansion_report}")
```

The report contains diagnostics like duplicate node IDs and expansion warnings.

## Check snapshot freshness

Determine if a workflow's super-node snapshot is current (matches the workflow's latest state):

```python
status = await client.super_nodes.snapshot_status(workflow_id="<workflow_id>")
print(status)  # e.g., {"is_current": True, "last_updated_at": "2025-07-03T..."}
```

## Find dependents

List workflows that embed a given super node (before unpublishing). This endpoint is paginated: `await` the call to get an `AsyncPage`, then `async for` over it:

```python
page = await client.super_nodes.dependents(
    workflow_id="<workflow_id>",
    page=1,
    size=20,
)

async for dependent in page:
    print(f"Used by: {dependent.name} ({dependent.workflow_id})")

# Fetch the next page (raises NoMorePagesError past the last page)
if page.has_next_page:
    next_page = await page.next_page()
```

To collect dependents across every page in one call, use `await page.list_all()`.

## Unpublish a super node

Stop a workflow from being publishable as a super node:

```python
result = await client.super_nodes.unpublish(workflow_id="<workflow_id>")

print(f"Unpublished version {result['workflow_version_number']}")
print(f"Workflows still using it: {result.get('workflows_referencing', [])}")
```

To unpublish a specific version (defaults to active):

```python
result = await client.super_nodes.unpublish(
    workflow_id="<workflow_id>",
    version_number=1,
)
```

## Embedding a super node in a workflow

To use a published super node as a node in another workflow, reference it via a `SuperNodeConfig` node (see [configs.md](../configs.md)):

```python
from interactly.configs import SuperNodeConfig

super_node_ref = SuperNodeConfig(
    name="Insurance Intake",
    description="Reusable intake flow",
    super_workflow_id="<published_super_node_workflow_id>",
    field_values={
        "member_id": "dynamic_variable:caller_id",
        "reason_for_contact": "dynamic_variable:contact_reason",
    },
)
```

### Dict form (also supported)

If you have not installed the `interactly[configs]` extra, build the same node as a plain `dict` with a `"type": "super_node"` discriminator:

```python
super_node_ref = {
    "type": "super_node",
    "name": "Insurance Intake",
    "description": "Reusable intake flow",
    "super_workflow_id": "<published_super_node_workflow_id>",
    "field_values": {
        "member_id": "dynamic_variable:caller_id",
        "reason_for_contact": "dynamic_variable:contact_reason",
    },
}
```

Prefer the typed `SuperNodeConfig` when the extra is available — it validates field names and types at construction time.

## Key options

| Option | Default | Notes |
|---|---|---|
| `version_number` | active version | Retrieve or unpublish a specific version |
| `page` | 1 | For dependents pagination |
| `size` | 20 | Items per page (dependents) |

## Gotchas

1. **Interface mapping is critical** — the interface must correctly map input fields to the sub-workflow's dynamic variables or the super node will fail at runtime.
2. **Snapshot stalenesss** — after modifying a sub-workflow's config, call `publish()` again to update the snapshot; use `snapshot_status()` to check freshness.
3. **Dependent workflows fail** — unpublishing a super node breaks any workflow that references it; always check `dependents()` first.
4. **Active version matters** — if you don't specify `version_number`, the workflow's currently-active version is used.

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient

client = WorkflowClient()

# List published super nodes (returns a plain list, not paginated)
for sn in client.super_nodes.list():
    print(f"{sn.name}: {sn.num_input_fields} inputs")

# Fetch one super node's definition
super_node = client.super_nodes.get(workflow_id="<workflow_id>")

# Page through dependents with a SyncPage
page = client.super_nodes.dependents(workflow_id="<workflow_id>", size=20)
for dependent in page:
    print(f"Used by: {dependent.name} ({dependent.workflow_id})")

client.close()
```

## See also

- [Embedding a super node](../../wf_examples/wf_example_progression_17.py) — progression example that builds and embeds a sub-workflow
- [Configs guide](../configs.md) — super node config types and parameters
- [API reference](../api_async.md#super-nodes--clientsuper_nodes)
```