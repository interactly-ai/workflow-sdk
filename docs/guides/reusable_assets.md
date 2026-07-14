# Reusable Assets

This guide covers node libraries, templates, and categories — the three mechanisms for sharing and reusing workflow components across your team.

The examples below use the asynchronous `AsyncWorkflowClient`. Every call is awaited, and the client is driven inside an `async with` block so it is closed cleanly on exit. All snippets assume you are inside:

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    ...  # snippets below
```

A synchronous `WorkflowClient` mirrors the same API — see [Synchronous alternative](#synchronous-alternative) at the end.

---

## Node Libraries

A node library bundles sets of pre-configured nodes and edges that can be imported into any workflow. Use libraries to package domain-specific nodes or application-wide standards.

### Get the node library schema

Retrieve the JSON Schema to understand the expected config structure:

```python
schema = await client.node_libraries.schema()
print(schema)  # {"type": "object", "properties": {...}}
```

### Create a node library

Define a library and save it. Lead with the typed `NodeLibraryConfig` from `interactly.configs` (requires `pip install interactly[configs]`):

```python
from interactly.configs import NodeLibraryConfig

config = NodeLibraryConfig(
    name="Healthcare Commons",
    description="Reusable healthcare intake and scheduling nodes",
    access_level="public",
    nodes=["node_verify_insurance", "node_schedule_appointment"],
)

library = await client.node_libraries.create(node_library_config=config)
print(f"Created library {library.id}: {library.name}")
```

**Dict form (also supported).** If you haven't installed the `[configs]` extra, pass a plain dict instead — the SDK serializes it the same way:

```python
node_library_config = {
    "name": "Healthcare Commons",
    "description": "Reusable healthcare intake and scheduling nodes",
    "access_level": "public",
    "nodes": [
        {
            "name": "Verify Insurance",
            "type": "llm",
            "config": {
                "llms_config": {"provider": "openai", "model": "gpt-4"},
                "main_response_config": {"prompt": "Verify patient insurance..."},
            },
        },
        {
            "name": "Schedule Appointment",
            "type": "rest_api",
            "config": {
                "method": "POST",
                "url": "https://api.clinic.com/appointments",
            },
        },
    ],
    "edges": [
        {
            "source_node_logical_id": "...",
            "destination_node_logical_id": "...",
            "edge_type": "direct",
        },
    ],
}

library = await client.node_libraries.create(node_library_config=node_library_config)
print(f"Created library {library.id}: {library.name}")
```

### List node libraries

Paginate through libraries with optional search and filtering:

```python
page = await client.node_libraries.list(
    page=1,
    size=20,
    search="healthcare",
    access_level="public",
)

async for lib in page:
    print(f"{lib.name} — {lib.access_level}")

# Move to next page
if page.has_next_page:
    next_page = await page.next_page()
```

### Get a single library

Retrieve a library by ID:

```python
library = await client.node_libraries.get(library_id="<library_id>")
print(f"Name: {library.name}")
print(f"Created by: {library.created_by}")
print(f"Nodes: {len(library.nodes)}")
```

### Update a library

Modify a library's config (only supplied fields are sent):

```python
library = await client.node_libraries.update(
    library_id="<library_id>",
    node_library_config={
        "description": "Updated description",
    },
)
```

### Delete a library

Remove a library entirely:

```python
await client.node_libraries.delete(library_id="<library_id>")
```

---

## Workflow Templates

A template is a parameterized workflow blueprint. Create a template once, then instantiate it with different values to generate new workflows rapidly.

### Get the template schema

Understand the expected config structure:

```python
schema = await client.templates.schema()
print(schema)
```

### Create a template

Define a template with nodes, edges, and input parameters. `templates.create` accepts a full `WorkflowTemplateConfig`-compatible dict:

```python
template_config = {
    "name": "Customer Support Flow",
    "description": "Standard customer support intake and routing",
    "category": "Support",
    "access_level": "public",
    "parameters": {
        "escalation_threshold": {"type": "integer", "default": 3},
        "support_email": {"type": "string", "description": "Support team email"},
    },
    "nodes": [
        {
            "name": "Collect Issue",
            "type": "llm",
            "config": {...},
        },
    ],
    "edges": [...],
}

template = await client.templates.create(config=template_config)
print(f"Created template {template.id}: {template.name}")
```

### List templates

Paginate templates with search and access level filtering:

```python
page = await client.templates.list(
    page=1,
    size=20,
    search="support",
    access_level="public",
)

async for tmpl in page:
    print(f"{tmpl.name} — {tmpl.category}")

if page.has_next_page:
    next_page = await page.next_page()
```

### Get a single template

Retrieve a template by ID:

```python
template = await client.templates.get(template_id="<template_id>")
print(f"Name: {template.name}")
print(f"Parameters: {template.parameters}")
print(f"Node count: {len(template.nodes)}")
```

### Update a template

Modify a template's config:

```python
template = await client.templates.update(
    template_id="<template_id>",
    config={
        "description": "Updated description",
    },
)
```

### Delete a template

Remove a template:

```python
await client.templates.delete(template_id="<template_id>")
```

---

## Workflow Categories

Categories are labels for organizing and filtering workflows. Each team has access to global default categories plus custom team-specific categories.

### List categories

Retrieve all available category names:

```python
categories = await client.categories.list()

for cat in categories:
    print(f"- {cat}")
```

Returns a list like:
```
['System Examples', 'Support', 'Sales', 'HR', 'Custom Intake']
```

This is a simple read-only operation; categories are managed outside the SDK.

---

## Key options

### Node Libraries
| Option | Default | Notes |
|---|---|---|
| `search` | None | Fuzzy filter by name |
| `access_level` | None | Filter by "public", "private", etc. |
| `page` | 1 | Page number (1-indexed) |
| `size` | 20 | Items per page |

### Templates
| Option | Default | Notes |
|---|---|---|
| `search` | None | Fuzzy filter by name |
| `access_level` | None | Filter by "public", "private", etc. |
| `page` | 1 | Page number (1-indexed) |
| `size` | 20 | Items per page |

---

## Gotchas

1. **Library nodes must have unique IDs** — within a library, all nodes must have distinct `logical_id` values or imports will fail.
2. **Template parameters are optional** — if a parameter has no `default`, downstream workflows must supply it during instantiation.
3. **Access levels are enforced** — a `private` library can only be used by the owning team; `public` libraries are visible team-wide.
4. **Categories are read-only** — you cannot create or delete categories via the SDK; contact your admin to add custom categories.

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient
from interactly.configs import NodeLibraryConfig

client = WorkflowClient()

library = client.node_libraries.create(
    node_library_config=NodeLibraryConfig(
        name="Healthcare Commons",
        description="Reusable healthcare intake and scheduling nodes",
        access_level="public",
        nodes=["node_verify_insurance", "node_schedule_appointment"],
    ),
)

page = client.node_libraries.list(search="healthcare")
for lib in page:
    print(f"{lib.name} — {lib.access_level}")

categories = client.categories.list()
```

---

## See also

- [API reference](../api_async.md#node-libraries--clientnode_libraries) — full method signatures
- [Configs guide](../configs.md) — typed config objects for libraries and templates
- [Super nodes](super_nodes.md) — another mechanism for workflow reuse (published workflows as embedded nodes)
</content>
</invoke>
