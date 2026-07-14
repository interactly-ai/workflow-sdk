# Type-Safe Configs (`interactly-configs`)

The `interactly-configs` package is an optional companion to the Interactly Python SDK.
It provides fully-typed Pydantic models for every workflow configuration object.

## Installation

```bash
pip install interactly[configs]
# or install both packages separately:
pip install interactly interactly-configs
```

## Why use typed configs?

| Without `interactly-configs` | With `interactly-configs` |
|---|---|
| Config fields are plain `dict` | Config fields are Pydantic models |
| No IDE auto-complete for nested fields | Full auto-complete and inline docs |
| Typos in field names silently pass | Validation errors caught at assignment |
| API responses return raw dicts | Responses deserialise to typed objects |

## Importing config classes

All public config symbols are available from `interactly.configs`:

```python
from interactly.configs import (
    # Workflow-level
    WorkflowConfig,
    WorkflowConfigFullyHydrated,

    # Node configs
    BaseNodeConfig,
    GlobalNodeConfig,
    NodeType,
    NodeCategory,

    # Edge configs
    EdgeConfig,
    EdgeType,
    DirectEdgeConfig,
    ConditionalEdgeConfig,
    CompanionEdgeConfig,
    ConditionConfig,

    # Tool configs
    ToolConfig,
    ToolType,

    # LLM configs
    LLMGroupConfig,
    LLMOrGroupConfig,
    PromptConfig,
    StaticMessagesConfig,
    DynamicMessagesConfig,

    # Run I/O
    BaseRunInput,
    BaseRunOutput,

    # MCP
    MCPServerConfig,
)
```

## Passing typed objects to SDK methods

**Prefer constructing typed config objects** and passing them directly — you get autocomplete and
validation at the point of assignment. The SDK serialises them automatically (no `.model_dump()`
call needed):

```python
from interactly import AsyncWorkflowClient
from interactly.configs import SayLLMNodeConfig, PromptConfig, OpenAILLMConfig

async with AsyncWorkflowClient() as client:
    # Build a typed node config — fields are checked as you assign them
    node_cfg = SayLLMNodeConfig(
        name="Greet User",
        main_response_config=PromptConfig(prompt="You are a friendly support agent."),
        llms_config=OpenAILLMConfig(model="gpt-4o-mini"),
    )
    node = await client.nodes.create(workflow_id="<workflow-id>", node_config=node_cfg)
```

**Dict form (also supported).** The same methods accept a plain `dict` when the `[configs]` extra
isn't installed — no code change needed, you just lose autocomplete and assignment-time validation:

```python
node = await client.nodes.create(
    workflow_id="<workflow-id>",
    node_config={"node_type": "say_llm", "name": "Greet User",
                 "config": {"main_response_config": {"prompt": "You are a friendly support agent."}}},
)
```

Typed objects are accepted anywhere a `*_config` is expected:

| Method | Typed parameter |
|---|---|
| `client.nodes.create(node_config=...)` | `BaseNodeConfig` |
| `client.nodes.update(id, node_config=...)` | `BaseNodeConfig` |
| `client.edges.create(edge_config=...)` | `EdgeConfig` (or `DirectEdgeConfig` etc.) |
| `client.edges.update(id, edge_config=...)` | `EdgeConfig` |
| `client.tools.create(tool_config=...)` | `ToolConfig` |
| `client.tools.update(id, tool_config=...)` | `ToolConfig` |
| `client.node_libraries.create(node_library_config=...)` | `NodeLibraryConfig` |
| `client.workflows.create(config=...)` | `WorkflowConfig` |
| `client.workflows.versions.update_config(wf_id, ver, config=...)` | `WorkflowConfig` |
| `client.schedules.create(..., run_input=...)` | `BaseRunInput` |

## Typed API responses

When `interactly-configs` is installed, the `*_config` fields on response objects are
automatically deserialised to their typed Pydantic counterparts.  If the library is **not**
installed the fields remain as plain `dict` (fully backward-compatible).

```python
node = await client.nodes.get("<node-id>")

# With interactly-configs installed:
from interactly.configs import BaseNodeConfig
if isinstance(node.node_config, BaseNodeConfig):
    print(node.node_config.node_type)   # type-checked, IDE-autocompleted
else:
    print(node.node_config)             # fallback dict
```

Fields that are upgraded automatically:

| Response model | Field | Typed as |
|---|---|---|
| `Node` | `node_config` | `BaseNodeConfig` |
| `Edge` | `edge_config` | `EdgeConfig` |
| `Tool` | `tool_config` | `ToolConfig` |
| `NodeLibrary` | `node_library_config` | `BaseNodeConfig` |
| `WorkflowVersion` | `config` | `WorkflowConfig` |
| `SuperNodeDetail` | `encapsulated_workflow_config` | `WorkflowConfigFullyHydrated` |
| `Run` | `input_output_pairs` | `List[WorkflowRunInputOutputPair]` |

## Discriminated union types

`EdgeConfig` and `ToolConfig` are Pydantic discriminated unions — the concrete subclass
is selected based on the `edge_type` / `tool_type` field.  Use `pydantic.TypeAdapter` to
validate them directly:

```python
from pydantic import TypeAdapter
from interactly.configs import EdgeConfig, DirectEdgeConfig

edge_cfg = TypeAdapter(EdgeConfig).validate_python({
    "edge_type": "direct",
    "source_node_logical_id": "node-a",
    "destination_node_logical_id": "node-b",
})
assert isinstance(edge_cfg, DirectEdgeConfig)
```

## Backward compatibility

The `[configs]` extra is **fully optional**.  All SDK methods continue to accept plain
`dict` arguments, and response fields remain as `dict` when the package is not installed.
Existing code requires no changes.

## See also

- [Notebook: 17_interactly_configs.ipynb](../notebooks/17_interactly_configs.ipynb)
- [Build your first workflow (typed)](04_first_workflow.md) and [wf_examples/wf_example_progression_1.py](../wf_examples/wf_example_progression_1.py)
- `interactly-configs` package on PyPI
