# 3. Core concepts

This page explains the mental model behind the SDK. Once these pieces click, the rest of the API is
just detail.

## House style: async-first, typed-first

Two conventions run through every page, notebook, and example. They're stated once here; the rest of
the docs just follow them.

**1. Async-first.** The **async client is the preferred way to use the SDK.** Workflows are
I/O-bound — network calls and streamed events — so `await` keeps your program responsive. The
canonical shape is `async with`, which opens and cleanly closes the client for you:

```python
import asyncio
from interactly import AsyncWorkflowClient

async def main():
    async with AsyncWorkflowClient() as client:      # reads INTERACTLY_* env vars
        workflow = await client.workflows.get("wf-123")
        print(workflow.name)

asyncio.run(main())
```

In **notebooks**, skip the `asyncio.run` wrapper — Jupyter supports top-level `await` directly:

```python
async with AsyncWorkflowClient() as client:
    workflow = await client.workflows.get("wf-123")
```

The synchronous `WorkflowClient` mirrors it method-for-method (same names, drop the `await`) and is a
fine choice for simple scripts. Each doc page ends with a short **Synchronous alternative** section
rather than repeating both forms throughout.

**2. Typed-first.** Author workflows with the **typed config classes** from
`interactly.configs` (the [`[configs]` extra](02_installation.md#the-configs-extra-typed-authoring)).
You get autocomplete, validation at assignment, and typed responses:

```python
from interactly.configs import SayLLMNodeConfig, PromptConfig, OpenAILLMConfig

greet = SayLLMNodeConfig(
    name="Greeting",
    main_response_config=PromptConfig(prompt="Greet the user warmly and ask how you can help."),
    llms_config=OpenAILLMConfig(model="gpt-4o-mini"),
)
```

Every method that takes a `*_config` **also** accepts a plain `dict` (the escape hatch when the
`[configs]` extra isn't installed) — shown as a "Dict form (also supported)" note where relevant.
Prefer the typed classes. See [Typed configs](configs.md).

## The graph

A workflow is a **directed graph** of nodes connected by edges:

```
                ┌─────────────┐   direct    ┌──────────────┐
   start ─────▶ │  greeting   │ ──────────▶ │  assistant   │ ◀─┐ self-loop
                │ (static msg)│             │  (say_llm)   │ ──┘ (waits for user)
                └─────────────┘             └──────┬───────┘
                                                   │ conditional: "user says goodbye"
                                                   ▼
                                             ┌──────────────┐
                                             │     end      │
                                             └──────────────┘
```

The workflow starts at an entry node, and each turn it runs a node, emits events, and follows an edge
to the next node — speaking to the user, waiting for input, branching, or ending.

## Nodes — the units of work

Each node type does one job. The common ones:

| Node type | Config class | Does |
|---|---|---|
| Speaking LLM | `SayLLMNodeConfig` | An LLM turn that talks to the user (and can self-loop, waiting for replies) |
| Worker LLM | `WorkerLLMNodeConfig` | A background LLM that extracts/decides without speaking |
| Static message | `SayStaticMessageNodeConfig` | Sends a fixed (or templated) message |
| Tool | `ToolNodeConfig` | Deterministically runs a tool and stores the result |
| HTTP request | `HttpRequestNodeConfig` | Calls an external REST API |
| SMS | `SendSMSNodeConfig` | Sends an SMS |
| Conversation | `StartConversationNodeConfig` / `EndConversationNodeConfig` | Marks conversation boundaries |
| Super node | `SuperNodeConfig` | Embeds another published workflow as a single node |
| Data / eval | `FieldExtractorNodeConfig`, `DeduplicateNodeConfig`, `WorkflowRunFetchNodeConfig`, `WorkflowRunEvalLLMNodeConfig` | Transform data or evaluate prior runs |

A **global node** (`GlobalNodeConfig`) is reachable from anywhere — used for routers and catch-all
exits.

## Edges — the flow

- **Direct** (`DirectEdgeConfig`) — always go to the target.
- **Conditional** (`ConditionalEdgeConfig` + `ConditionConfig`) — go only if a condition matches. A
  condition can be a natural-language intent or a structured `condition_expression` like
  `[[extracted_intent]] == 'billing'`.
- **Companion** (`CompanionEdgeConfig`) — run a side-task alongside the main flow.

## Tools

Tools give LLM nodes capabilities. Types (`ToolConfig` family):

- `InlinePythonToolConfig` — a Python function you define inline.
- `InbuiltFunctionToolConfig` — a pre-packaged registry tool.
- `ExternalAPIToolConfig` — call an external API as a tool.
- `KnowledgeBaseToolConfig` — retrieve from a knowledge base (RAG).
- `MCPServerConfig` — tools served by an MCP server.

Tools can declare an `args_schema` so the LLM extracts structured arguments before the tool runs.

## LLM configs

Every LLM node needs an LLM configuration — a provider + model + parameters
(`OpenAILLMConfig`, `AnthropicLLMConfig`, `BedrockLLMConfig`, …), or a **group**
(`LLMGroupConfig`, `LLMGroupWithBackchannelConfig`) that combines models (e.g. a fast "backchannel"
model that says "let me check…" while the main model thinks).

You can also save **named/team LLM configs** on the server and reference them from a node by
`named_llm_config_id` — see the [LLM configs guide](guides/llm_configs.md).

## Variables — three tiers of scope

Values flow through a run at three scopes:

1. **Dynamic variables** — supplied at run start (e.g. caller name, account id). Interpolated into
   prompts as `{{variable}}`.
2. **Workflow-global variables** — team/workflow-scoped values managed via
   [`client.global_variables`](guides/global_variables.md).
3. **Thread-local / runtime variables** — produced during a run (e.g. a tool's output), referenced
   downstream as `[[runtime_variable]]`.

## Authoring vs. execution

This is the key split:

- **Authoring** produces a `WorkflowConfigFullyHydrated` = a `WorkflowConfig` (graph metadata) +
  `node_configs` + `edge_configs`. It's pure data. See [Typed configs](configs.md).
- **Execution** happens on the **server**. You upload the config, then drive it. A `WorkflowHandle`
  (from `upload_and_get_handle`) is a thin client-side reference; the server owns the session, message
  history, and node state. See [Runtime handles](runtime.md).

## Events

A run emits a stream of **typed events** — `StartWorkflowEvent`, `AssistantResponseEvent`,
`BusyWaitForUserMessageEvent`, per-node events (`SayLLMNodeEvent`, `HttpRequestNodeEvent`, …), edge
events, and `EndWorkflowEvent`. You consume these when [streaming](streaming.md) or driving a
[handle](runtime.md). The full catalog is in the [runtime guide](runtime.md).

## Versions, super-nodes, and reuse

- A workflow has **versions**; one is **active**. Versions let you iterate safely and A/B test — see
  [Workflows & versions](guides/workflows_and_versions.md).
- Publish a workflow as a **super-node** to reuse it inside others — see [Super nodes](guides/super_nodes.md).
- **Templates**, **node libraries**, and **categories** help you reuse and organize — see
  [Reusable assets](guides/reusable_assets.md).

---

**Next:** [4. Your first workflow →](04_first_workflow.md)
