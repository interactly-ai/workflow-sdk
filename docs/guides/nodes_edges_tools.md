# Nodes, Edges, and Tools

Workflows are directed graphs composed of **nodes** (operations) connected by **edges** (transitions). Tools are reusable functions that nodes (especially LLM nodes) can invoke. You can manage these as standalone resources or as part of a complete workflow graph.

All examples below use the asynchronous `AsyncWorkflowClient`. The first example opens a client with `async with`; the remaining snippets assume a `client` obtained the same way (`async with AsyncWorkflowClient() as client:`). For the synchronous client, see [Synchronous alternative](#synchronous-alternative) at the end.

## Nodes

A node is an atomic unit of work: prompt an LLM, send an SMS, make an HTTP request, etc.

### Node types

List all available node types by category.

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    # Get all node types
    types_list = await client.nodes.types()
    # Returns: [
    #     {"type": "say_llm", "primary_category": "System", "secondary_category": "LLM"},
    #     {"type": "http_request", "primary_category": "REST API", ...},
    #     ...
    # ]
```

### The no-op node

`no_op` runs and succeeds without doing anything else. Three uses:

```python
import interactly_configs as ic

junction = ic.NoOpNodeConfig(name="junction")                      # fan-in point
placeholder = ic.NoOpNodeConfig(name="eligibility", note="TODO: real check")
slow = ic.NoOpNodeConfig(name="slow", delay_seconds=2.0)           # testing only
failing = ic.NoOpNodeConfig(name="boom", simulate_failure=True)    # testing only
```

**It is not `disabled=True`.** A disabled node is skipped entirely and emits nothing, so downstream
conditional edges have nothing to branch on. A no-op node *runs*: it emits the usual node
start/end events and writes `no_op_result` and `no_op_result_success` to thread state — which is
exactly what makes it usable as a fan-in junction or a branch-testing stand-in.

`simulate_failure=True` reports `success=False` without aborting the run, so you can exercise a
failure branch with no failing integration behind it.

### Node schema

Retrieve the JSON Schema for a specific node type (config, run inputs, run outputs).

```python
schema = await client.nodes.schema("say_llm")
# Returns: {
#     "config_schema": {...},
#     "run_input_schema": {...},
#     "run_output_schema": {...}
# }
```

### Create a standalone node

Build the node config with a typed class from `interactly.configs`:

```python
from interactly.configs import SayLLMNodeConfig, PromptConfig

node_config = SayLLMNodeConfig(
    logical_id="llm_1",
    name="Ask User",
    main_response_config=PromptConfig(prompt="What is your name?"),
    attachable_llm_config_id="llm_cfg_123",
)

node = await client.nodes.create(node_config=node_config)
print(node.id)  # ObjectId
```

**Dict form (also supported).** If you have not installed the `[configs]` extra, pass a plain dict with the same field names — it is serialized and sent as-is:

```python
node_config = {
    "type": "say_llm",
    "logical_id": "llm_1",
    "name": "Ask User",
    "main_response_config": {"prompt": "What is your name?"},
    "attachable_llm_config_id": "llm_cfg_123",
}

node = await client.nodes.create(node_config=node_config)
```

### List nodes

```python
# All nodes
page = await client.nodes.list(page=1, size=20)

# Filter by type
page = await client.nodes.list(node_type="say_llm")

# Filter by workflow
page = await client.nodes.list(workflow_id="wf_123")

# Search by name
page = await client.nodes.list(search="ask")

async for node in page:
    print(node.id, node.node_config.name)
```

### Get a node

```python
node = await client.nodes.get("node_id_here")
print(node.node_config)
```

### Update a node

```python
from interactly.configs import SayLLMNodeConfig, PromptConfig

updated_node = await client.nodes.update(
    node_id="node_123",
    node_config=SayLLMNodeConfig(
        main_response_config=PromptConfig(prompt="What is your email?"),
    ),
)
```

**Dict form (also supported):**

```python
updated_node = await client.nodes.update(
    node_id="node_123",
    node_config={"type": "say_llm", "main_response_config": {"prompt": "What is your email?"}},
)
```

### Delete a node

```python
await client.nodes.delete("node_id_here")
```

---

## Edges

An edge defines how execution flows from one node to another, with optional conditions.

### Edge types

List available edge types.

```python
edge_types = await client.edges.types()
# Returns: ["direct", "conditional", "companion"]
```

### Edge schema

Get the JSON Schema for an edge type.

```python
schema = await client.edges.schema("conditional")
# Returns: {
#     "config_schema": {...},
#     "run_input_schema": {...}
# }
```

### Extra edge behaviour

Three optional configs change *when* an edge is considered, not where it goes. Each has its own
guide:

| Config | On | Effect |
|---|---|---|
| `companion_thread_config` | direct edges | Forks a background thread — [Companion threads](companion_threads.md) |
| `evaluate_while_waiting_config` | conditional edges | Fires while the source node is parked — [Evaluate while waiting](waiting_evaluation.md) |
| `self_loop_config` | **nodes**, not edges | Bounded re-execution — [Self-loops](self_loops.md) |

```python
ic.DirectEdgeConfig(
    source_node_logical_id=entry.logical_id,
    destination_node_logical_id=poller.logical_id,
    companion_thread_config=ic.CompanionThreadConfig(is_companion_thread=True, thread_id="labpoll"),
)
```

Read them back with the defensive helpers, which are safe on any edge:

```python
ic.edge_is_companion(edge)
ic.edge_companion_thread_id(edge)
ic.edge_evaluates_while_waiting(edge)
ic.edge_waiting_evaluation_config(edge)
```

### Create a standalone edge

Build edge configs with the typed classes from `interactly.configs`. Note the target field is `destination_node_logical_id`.

```python
from interactly.configs import (
    DirectEdgeConfig,
    ConditionalEdgeConfig,
    CompanionEdgeConfig,
    ConditionConfig,
)

# Direct edge: source → target
edge_config = DirectEdgeConfig(
    source_node_logical_id="llm_1",
    destination_node_logical_id="http_1",
)
edge = await client.edges.create(edge_config=edge_config)
print(edge.id)

# Conditional edge: source → target when the condition is met
edge_config = ConditionalEdgeConfig(
    source_node_logical_id="llm_1",
    destination_node_logical_id="sms_1",
    condition=ConditionConfig(condition_freeform="The user's request is urgent."),
)
edge = await client.edges.create(edge_config=edge_config)

# Companion edge: runs alongside the source node
edge_config = CompanionEdgeConfig(
    source_node_logical_id="llm_1",
    destination_node_logical_id="logger_1",
)
edge = await client.edges.create(edge_config=edge_config)
```

**Dict form (also supported).** Without the `[configs]` extra, pass equivalent dicts:

```python
# Direct
edge_config = {
    "type": "direct",
    "source_node_logical_id": "llm_1",
    "destination_node_logical_id": "http_1",
}
edge = await client.edges.create(edge_config=edge_config)

# Conditional
edge_config = {
    "type": "conditional",
    "source_node_logical_id": "llm_1",
    "destination_node_logical_id": "sms_1",
    "condition": {"condition_freeform": "The user's request is urgent."},
}
edge = await client.edges.create(edge_config=edge_config)
```

### List edges

```python
# All edges
page = await client.edges.list(page=1, size=20)

# Filter by type
page = await client.edges.list(edge_type="conditional")

# Filter by workflow
page = await client.edges.list(workflow_id="wf_123")

# Search by name
page = await client.edges.list(search="escalate")

async for edge in page:
    print(edge.id, edge.edge_config.type)
```

### Get an edge

```python
edge = await client.edges.get("edge_id_here")
print(edge.edge_config.source_node_logical_id, edge.edge_config.destination_node_logical_id)
```

### Update an edge

```python
from interactly.configs import ConditionalEdgeConfig, ConditionConfig

updated_edge = await client.edges.update(
    edge_id="edge_123",
    edge_config=ConditionalEdgeConfig(
        source_node_logical_id="llm_1",
        destination_node_logical_id="sms_1",
        condition=ConditionConfig(condition_freeform="The user's request is urgent."),
    ),
)
```

**Dict form (also supported):**

```python
updated_edge = await client.edges.update(
    edge_id="edge_123",
    edge_config={
        "type": "conditional",
        "condition": {"condition_freeform": "The user's request is urgent."},
    },
)
```

### Delete an edge

```python
await client.edges.delete("edge_id_here")
```

---

## Tools

Tools are reusable functions that LLM nodes can invoke. The SDK distinguishes three categories:

1. **Inbuilt tools** — pre-packaged (e.g., math, string utilities); use as-is.
2. **Configurable inbuilt tools** — pre-packaged with user-supplied config.
3. **Custom tools** — user-defined functions.

### Tool types

List all custom tool type identifiers.

```python
tool_types = await client.tools.types()
# Returns: ["inbuilt_function", "inline_python", "external_api", "knowledge_base"]
# Interactly staff also see "codebase_function" — see "Codebase functions" below.
```

### Tool schema

Get the JSON Schema for a custom tool type.

```python
schema = await client.tools.schema("inline_python")
# Returns: {"config_schema": {...}}
```

### List inbuilt tools

Pre-packaged tools (no configuration required).

```python
inbuilt = await client.tools.inbuilt()
# Returns: [
#     {
#         "tool_id": "math_add",
#         "name": "Add",
#         "signature": "add(a: float, b: float) -> float",
#         "args_schema": {...},
#         "category": "Math"
#     },
#     ...
# ]
```

### List configurable inbuilt tools

Pre-packaged tools that accept configuration.

```python
configurable = await client.tools.configurable_inbuilt()
# Returns: [
#     {
#         "key": "web_search",
#         "title": "Web Search",
#         "registry_tool_id": "...",
#         "config_schema": {...}
#     },
#     ...
# ]
```

### Get schema for a configurable inbuilt tool

```python
schema = await client.tools.configurable_inbuilt_schema("web_search")
# Returns: {"key": "web_search", "title": "Web Search", "config_schema": {...}}
```

### Create a custom tool

Build the tool config with a typed class from the `ToolConfig` family in `interactly.configs`:

```python
from interactly.configs import InlinePythonToolConfig

tool_config = InlinePythonToolConfig(
    name="My Custom Tool",
    description="A user-defined Python function",
    code="def my_func(x: float) -> float:\n    return x * 2",
)

tool = await client.tools.create(tool_config=tool_config)
print(tool.id)
```

Other members of the family include `InbuiltFunctionToolConfig`, `ExternalAPIToolConfig`,
`KnowledgeBaseToolConfig` and the staff-only `CodebaseFunctionToolConfig`.

A write can come back with **advisory warnings**: things worth fixing that did not stop the save, such as
a variable the tool needs that your team has not defined. They are on the returned object, and are empty
on a plain read:

```python
tool = await client.tools.create(tool_config=tool_config)
for warning in tool.warnings:
    print("warning:", warning)
```

`Node`, `Workflow` and `WorkflowVersion` carry `warnings` the same way.

**Dict form (also supported).** Without the `[configs]` extra, pass an equivalent dict:

```python
tool_config = {
    "type": "inline_python",
    "name": "My Custom Tool",
    "description": "A user-defined Python function",
    "code": "def my_func(x): return x * 2",
}

tool = await client.tools.create(tool_config=tool_config)
```

### List custom tools

```python
# All tools
page = await client.tools.list(page=1, size=20)

# Filter by type
page = await client.tools.list(tool_type="inline_python")

# Filter by workflow
page = await client.tools.list(workflow_id="wf_123")

# Search by name
page = await client.tools.list(search="custom")

async for tool in page:
    print(tool.id, tool.tool_config.name, tool.tool_config.type)
```

### Get a tool

```python
tool = await client.tools.get("tool_id_here")
print(tool.tool_config)
```

### Update a tool

```python
from interactly.configs import InlinePythonToolConfig

updated_tool = await client.tools.update(
    tool_id="tool_123",
    tool_config=InlinePythonToolConfig(code="def my_func(x: float) -> float:\n    return x * 3"),
)
```

**Dict form (also supported):**

```python
updated_tool = await client.tools.update(
    tool_id="tool_123",
    tool_config={"type": "inline_python", "code": "def my_func(x): return x * 3"},
)
```

### Return a response as media

An external-API tool can hand back the response body as media — a call recording, an image — instead of
parsing it:

```python
from interactly.configs import ExternalAPIToolConfig

recording = ExternalAPIToolConfig(
    name="Fetch recording",
    api_endpoint="https://example.com/recordings/{{call_id}}",
    result_as_media=True,
)
```

On a tool node, the bytes are held for the run and the result variable gets a `media://` handle. An LLM
node whose prompt names that variable (for example `[[tool_result]]`) is sent the media with its request,
so a model that takes audio or images can listen to or look at it. Because the result is a handle, there
is nothing for `result_variable_mappings` or `expand_result_into_runtime_variables` to read, and setting
either alongside `result_as_media` is rejected.

### Clone a tool

Duplicate a saved tool within your team:

```python
copy = await client.tools.clone(tool.id)                         # named "<source> (Clone)"
renamed = await client.tools.clone(tool.id, name="Lookup v2")
```

Unlike export and import, a clone is verbatim, **secrets included**, because both copies live in the same
team. A plain inbuilt tool cannot be cloned (`PermissionDeniedError`).

### Test a tool

Run a saved tool, or an unsaved config, with argument values:

```python
result = await client.tools.execute(tool.id, args={"member_id": "M123"})
print(result.success, result.result, result.error)
```

**Inline Python is not executed by default.** Test execution of an `inline_python` config runs
caller-authored code on the server, so environments refuse it unless they opt in. The call does not
raise; it returns `success=False` with an explanatory `error`:

```
Inline Python tool execution is disabled in this environment. Use dry run to validate inputs, or enable
ALLOW_INLINE_PYTHON_TOOL_TEST in a trusted environment.
```

### Export & import a tool

Move a tool between teams or environments:

```python
bundle = await client.tools.export(tool_id)

imported = await client.tools.import_bundle(
    bundle,
    name_override="Eligibility check (staging)",
    secret_overrides={"api_headers.Authorization": "Bearer ..."},
)
```

Two things the server insists on, both worth knowing before the call fails:

- **Secrets are redacted on export**, never included. The bundle records which fields were dropped;
  re-supply them by dotted path via `secret_overrides`.
- **`inline_python` bundles require `confirm_executable=True`.** Such a bundle carries code that will
  run in your team's context, so it is refused unless you say so explicitly.

`clear_unresolved_refs` (default `True`) strips team-scoped references — knowledge-base ids and the
like — that cannot resolve in the importing team, rather than importing a tool that silently points
at another team's resources.

Variable **values** never travel with a bundle, but their names do: `bundle["required_dynamic_variables"]`
lists what the tool needs. An import into a team that has not defined one still succeeds, and says so in
`warnings`:

```python
imported.warnings
# ["This tool uses dynamic variable(s) this team has not defined: member_id. Add them as global
#   variables (or supply them per run) or the tool will fail at call time with an unresolved-variable
#   error."]
```

### Codebase functions (Interactly staff only)

A `CodebaseFunctionToolConfig` calls a function that already exists in the platform's codebase, named by
its `function_id`. Creating, updating, executing or listing one requires an Interactly super-admin; every
other role gets `PermissionDeniedError`, and does not see the type in `tools.types()`. A customer can
still **read** a workflow that uses one, so the config class is part of `interactly.configs`.

```python
catalogue = await client.tools.codebase_functions()
for function in catalogue.codebase_functions:
    print(function.id, function.side_effect, function.summary)

detail = await client.tools.get_codebase_function("benefits.estimate_member_cost_share")
detail.args_schema   # derived from the function's signature

from interactly.configs import CodebaseFunctionToolConfig

CodebaseFunctionToolConfig(name="Estimate cost", function_id="benefits.estimate_member_cost_share")
```

Note that `tool_id` means a **saved tool document** here, the opposite of `InbuiltFunctionToolConfig`,
where `tool_id` names the function itself. An unknown id raises `NotFoundError`; its `body["reason"]`
separates "no such function" from "its module could not be imported here".

### Delete a tool

```python
await client.tools.delete("tool_id_here")
```

---

## Authoring Full Graph Configs

Standalone node/edge/tool operations are useful for building a library. To execute a workflow, assemble them into a complete graph using the typed config classes:

```python
from interactly.configs import (
    WorkflowConfigFullyHydrated,
    WorkflowConfig,
    SayLLMNodeConfig,
    PromptConfig,
)

# Create a simple workflow programmatically
config = WorkflowConfigFullyHydrated(
    workflow_config=WorkflowConfig(
        name="Simple Flow",
        description="Greet the user",
    ),
    node_configs=[
        SayLLMNodeConfig(
            logical_id="ask_name",
            name="Ask Name",
            is_start=True,
            main_response_config=PromptConfig(prompt="What is your name?"),
        )
    ],
    edge_configs=[],
)

# Upload and execute
wf = await client.workflows.create_from_config(config)
```

Tools are attached to LLM nodes via the node's `tools_config`; there is no separate `tool_configs` list on `WorkflowConfigFullyHydrated`. For complex graphs with many interdependencies, prefer using the dashboard's visual editor or the SDK's typed config classes with validation.

---

## Key Parameters & Options

| Parameter | Type | Notes |
|-----------|------|-------|
| `node_config` | BaseNodeConfig / dict | Required for node create/update |
| `edge_config` | EdgeConfig / dict | Required for edge create/update |
| `tool_config` | ToolConfig / dict | Required for tool create/update |
| `type` | str | Node/edge/tool type identifier |
| `logical_id` | str | Unique within workflow (UUID prefix) |
| `name` | str | Human-readable name |
| `source_node_logical_id` | str | Edge source node |
| `destination_node_logical_id` | str | Edge target node |
| `condition` | ConditionConfig / dict | Conditional edge only |
| `page` | int | 1-indexed, default 1 |
| `size` | int | Items per page, default 20 |
| `search` | str | Fuzzy name filter |
| `workflow_id` | str | Filter to nodes/edges/tools in a workflow |

---

## Gotchas

- **Logical IDs are unique per workflow**: Two nodes in the same workflow cannot share a `logical_id`.
- **Edges reference logical IDs, not ObjectIds**: Use `source_node_logical_id` and `destination_node_logical_id`, not ObjectIds.
- **Inbuilt tools don't need creation**: They are pre-registered globally and referenced by `tool_id` (e.g., `"math_add"`).
- **Standalone node/edge/tool IDs vs. workflow nodes**: A standalone node created via `nodes.create()` gets a `id`. When that node is added to a workflow, it is part of the graph's JSON config and referenced by its `logical_id`.
- **Tool attachment**: Tools are attached to LLM nodes via the node's `tools_config`; the SDK does not enforce this at the node/tool API level.
- **`no_op` is not `disabled`**: a disabled node emits nothing; a no-op node runs and emits events.
- **The condition language is smaller than it looks**: `==`, `!=`, `<`, `<=`, `>`, `>=`,
  `AND`/`OR`/`NOT`, and `isPresent` / `isAbsent` / `isEmpty` / `isNonEmpty`. No `contains()`, and an
  unsupported call fails the **run**, not the save.
- **Dotted access into a dict-valued runtime variable is not interpolated**: a prompt containing
  `[[result.value]]` where `result` holds a dict comes through as that literal text. Have tools
  return the field you need directly.
- **Import refuses `inline_python` by default**: pass `confirm_executable=True` deliberately.
- **Test execution of `inline_python` is off by default**: `execute_inline` returns `success=False` with
  an explanatory error rather than raising.
- **Read `warnings` after a write**: the server reports things like undefined variables there instead of
  failing the save.
- **`result_as_media` excludes result mappings**: the result is a `media://` handle with no fields to map.
- **Typed configs need the extra**: The typed classes require `pip install interactly[configs]`. Without it, use the dict form shown in each section.

---

## Synchronous alternative

The synchronous `WorkflowClient` mirrors the async API exactly — drop the `await` and use
`with` instead of `async with`:

```python
from interactly import WorkflowClient
from interactly.configs import SayLLMNodeConfig, PromptConfig

client = WorkflowClient()

node = client.nodes.create(
    node_config=SayLLMNodeConfig(
        logical_id="llm_1",
        name="Ask User",
        main_response_config=PromptConfig(prompt="What is your name?"),
    )
)

page = client.nodes.list(node_type="say_llm")
for node in page:
    print(node.id, node.node_config.name)
```

---

## See also

- [Companion threads](companion_threads.md) — `companion_thread_config` on direct edges
- [Evaluate while waiting](waiting_evaluation.md) — `evaluate_while_waiting_config`
- [Self-loops](self_loops.md) — `self_loop_config` on nodes
- [Workflows and Versions](workflows_and_versions.md) — manage workflow lifecycle and versioning
- [Running Workflows](running_workflows.md) — execute a workflow with its nodes and edges
- [Monitoring Runs](monitoring_runs.md) — inspect node outputs and events
- [API Reference](../api_async.md) — full endpoint docs
- [Configs](../configs.md) — typed node/edge/tool models
