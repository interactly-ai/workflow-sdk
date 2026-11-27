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
    NoOpNodeConfig,
    NodeType,
    NodeCategory,

    # Edge configs
    EdgeConfig,
    EdgeType,
    DirectEdgeConfig,
    ConditionalEdgeConfig,
    CompanionEdgeConfig,
    ConditionConfig,

    # Background execution
    CompanionThreadConfig,
    EvaluateWhileWaitingConfig,
    WaitingEvaluationTriggerMode,
    SelfLoopConfig,

    # Feedback
    RatingValue,

    # Tool configs
    ToolConfig,
    ToolType,

    # LLM configs (see the LLM configs guide for every provider)
    OpenAILLMConfig,
    AnthropicLLMConfig,
    AnthropicBackend,
    GoogleLLMConfig,
    GoogleBackend,
    GeminiThinkingLevel,
    XAILLMConfig,
    GemmaLLMConfig,
    GLMLLMConfig,
    DeepSeekLLMConfig,
    NodeRealtimeOverrides,
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

    # Fallbacks for a type a newer server sends (see "Unknown LLM and tool types")
    UnknownLLMConfig,
    UnknownToolConfig,
    UnknownNodeConfig,
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
    node = await client.nodes.create(node_config=node_cfg)
```

**Dict form (also supported).** The same methods accept a plain `dict` when the `[configs]` extra
isn't installed — no code change needed, you just lose autocomplete and assignment-time validation:

```python
node = await client.nodes.create(
    node_config={
        "type": "say_llm",
        "name": "Greet User",
        "main_response_config": {"prompt": "You are a friendly support agent."},
    },
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

`EdgeConfig`, `ToolConfig`, `LLMConfig` and `NodeConfig` are Pydantic discriminated unions: the concrete
subclass is selected by the **`type`** field (`"direct"`, `"external_api"`, `"xai_llm"`, `"say_llm"`, …).
Use `pydantic.TypeAdapter` to validate them directly:

```python
from pydantic import TypeAdapter
from interactly.configs import DirectEdgeConfig, EdgeConfig, LLMConfig, XAILLMConfig

edge_cfg = TypeAdapter(EdgeConfig).validate_python({
    "type": "direct",
    "source_node_logical_id": "node-a",
    "destination_node_logical_id": "node-b",
})
assert isinstance(edge_cfg, DirectEdgeConfig)

llm_cfg = TypeAdapter(LLMConfig).validate_python({"type": "xai_llm", "model": "grok-4.6"})
assert isinstance(llm_cfg, XAILLMConfig)
```

A provider or tool `type` this version of the package does not know is kept rather than failing the node
that holds it: an LLM provider becomes an `UnknownLLMConfig`, and a tool type an `UnknownToolConfig` (see
[Unknown LLM and tool types](#unknown-llm-and-tool-types)). Inside a hydrated workflow, a node type it does
not know is kept as `UnknownNodeConfig` with its fields intact. Upgrade `interactly[configs]` to get the
typed class back.

## Round-tripping a hydrated config

`WorkflowConfigFullyHydrated.node_configs` is annotated `SerializeAsAny[BaseNodeConfig]`, so an
unknown node type cannot fail the whole workflow. A `mode="before"` validator upgrades each entry
through the discriminated union first, which is what keeps *known* types at full fidelity:

```python
hydrated = await client.workflows.get_fully_hydrated(workflow_id)
node = hydrated.node_configs[0]
type(node).__name__     # 'SayLLMNodeConfig' — not 'BaseNodeConfig'
node.prompt_config      # preserved
```

Without that validator, validating a plain dict against `SerializeAsAny[BaseNodeConfig]` coerces it
to the base class and **silently discards every subclass field** — `SerializeAsAny` governs
serialization, not validation.

A node type this package does not know yet lands in an internal `UnknownNodeConfig` with
`extra="allow"`, so its fields survive validation and a later `model_dump()`. Branch on `node.type`
rather than `isinstance` when you need to handle that case:

```python
known = {t.value for t in ic.NodeType}
for node in hydrated.node_configs:
    if node.type not in known:
        print("newer server node type:", node.type)   # fields still intact
```

That is what makes a fetch → modify → upload round trip safe against a server ahead of your SDK.

## Unknown LLM and tool types

A server can be ahead of the installed package. When a workflow or a saved LLM config names an LLM provider or a
tool type this package does not know, the config is kept as an unknown type rather than failing the node that holds
it. The node keeps its own class: a `say_llm` node stays a `SayLLMNodeConfig`, with an `UnknownLLMConfig` inside it.

- `UnknownLLMConfig` stands in for an LLM config wherever one is held: a node's `llms_config`, a workflow's default
  `llms_config`, or a member of an `LLMGroupConfig`. `llm_configs.get()` returns one as `config` for an unknown provider.
- `UnknownToolConfig` stands in for a tool config: a tool node's `tool_config`, or an entry of an LLM node's
  `tools_config.tools`.

```python
from interactly.configs import UnknownLLMConfig

node = hydrated.node_configs[0]
if isinstance(node.llms_config, UnknownLLMConfig):
    print(node.llms_config.type, node.llms_config.model)   # fields the server sent are readable
```

**What round-trips.** An unknown config keeps every field the server sent, including fields this package has no
field for. Writing it back sends exactly those fields: no defaults are added and no `logical_id` is minted, so a
fetch, edit and upload keeps the config intact. The fields the base class declares are typed; one the server
omitted reads as the base default, and that default is not written back. For a tool, the shared fields include
`result_variable_mappings`.

**What still raises.** A config with no `type`, and a known type with an invalid field, still raise. Those are
mistakes in the config, not a newer type.

**What you cannot do with them.**

- Get the provider- or tool-specific checks. Only the shared fields are typed; the server judges the rest when you
  upload.
- Use `isinstance` against a known class. `isinstance(config, OpenAILLMConfig)` is false for an unknown config, so
  branch on `type` or on `UnknownLLMConfig` / `UnknownToolConfig`.
- Find the type in a published JSON Schema. The schemas do not describe the fallbacks.
- Edit a field with typed assignment. Send the changed config as a dict with the same `type`, or upgrade
  `interactly[configs]` to get the typed class.

## Backward compatibility

The `[configs]` extra is **fully optional**.  All SDK methods continue to accept plain
`dict` arguments, and response fields remain as `dict` when the package is not installed.
Existing code requires no changes.

## Synchronous alternative

The typed classes work the same with the synchronous `WorkflowClient`: pass them to the same methods without `await`,
and open the client with `with` instead of `async with`:

```python
from interactly import WorkflowClient
from interactly.configs import PromptConfig, SayLLMNodeConfig

with WorkflowClient() as client:
    node = client.nodes.create(
        node_config=SayLLMNodeConfig(
            name="Greet User",
            main_response_config=PromptConfig(prompt="You are a friendly support agent."),
        ),
    )
```

## See also

- [Nodes, edges & tools](guides/nodes_edges_tools.md) — the no-op node and edge-level configs
- [Companion threads](guides/companion_threads.md) / [Evaluate while waiting](guides/waiting_evaluation.md) / [Self-loops](guides/self_loops.md) — what the background-execution configs do

- [Notebook: 17_interactly_configs.ipynb](../notebooks/17_interactly_configs.ipynb)
- [Build your first workflow (typed)](04_first_workflow.md) and [wf_examples/wf_example_progression_1.py](../wf_examples/wf_example_progression_1.py)
- `interactly-configs` package on PyPI

## Gotchas

- **Unknown types skip the typed checks.** An `UnknownLLMConfig` or `UnknownToolConfig` runs only the checks every config of its kind shares (for a tool, its variable bindings and result mappings), none specific to its type. The server judges the rest on upload.
- **`isinstance` is false for an unknown type.** Check `type`, or the `UnknownLLMConfig` / `UnknownToolConfig` class.
- **Upgrading restores the typed class.** The data is unchanged; the same config is validated by the new class.
