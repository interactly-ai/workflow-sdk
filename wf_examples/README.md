# Interactly Workflow SDK — Examples & Learning Curriculum

A hands-on, progressive curriculum for the Interactly Workflow SDK. Each example builds on the previous one and introduces a small number of new concepts, so working through them in order is the fastest way to become fluent with the SDK.

Every example ships in three forms:

- **A builder script** — `wf_example_progression_N.py` exposes `build_assistant_workflow()`, which returns a fully-typed workflow config.
- **A runnable notebook** — [`notebooks/wf_example_notebooks/wf_example_progression_N.ipynb`](../notebooks/wf_example_notebooks/) imports that builder, creates the workflow on the server, drives a **capped** conversation, and cleans up.
- **A doc (this curriculum)** — `wf_example_progression_N.md` explains the purpose, shows a workflow diagram, and details the nodes, routing, and dynamic variables.

## How to run any example

```bash
# one-time setup (from the workflow_sdk/ root)
pipenv install --dev

# run a single example's notebook end to end against the dev server
pipenv run python notebooks/_run_e2e.py wf_example_progression_1

# run the whole suite (all core notebooks + every example)
pipenv run python notebooks/_run_e2e.py
```

> Credentials are read from the SDK's `.env` file. See the [top-level README](../README.md) for setup and SDK concepts.

## The curriculum

### Foundations

_Build, route, and parameterise a conversational workflow._

| Step | Example | Teaches | New concepts |
|---|---|---|---|
| 1 | [Your first workflow](./wf_example_progression_1.md) | Build and run a minimal three-node conversational workflow end to end. | SayLLMNodeConfig, SayStaticMessageNodeConfig, DirectEdgeConfig… |
| 2 | [Intent routing](./wf_example_progression_2.md) | Route the caller to one of several scoped specialist agents, then end on goodbye. | Router node pattern, multiple ConditionalEdgeConfig branches, global end node (is_global) |
| 3 | [Global router + dynamic variables](./wf_example_progression_3.md) | Make the router global (re-routable mid-conversation) and parameterise prompts with dynamic variables. | GlobalNodeConfig, default_dynamic_variables, default_prompt_prefix / default_prompt_suffix… |

### Structured data & routing

_Capture typed data with Worker LLMs and route on it._

| Step | Example | Teaches | New concepts |
|---|---|---|---|
| 4 | [Structured data capture](./wf_example_progression_4.md) | Silently extract a typed intake form with a Worker LLM and route once required fields are present. | WorkerLLMNodeConfig, structured output schema, freeform condition over extracted fields |
| 5 | [Expression-based routing](./wf_example_progression_5.md) | Same intake flow, but route with the typed expression language instead of a freeform condition. | condition_expression, isPresent([[var]]), [[runtime_variable]] references |
| 6 | [Companion agents + multi-path routing](./wf_example_progression_6.md) | Pair a conversational agent with a silent companion extractor and branch to three risk paths. | CompanionEdgeConfig, parallel Say + Worker agents, multi-branch expression routing |
| 7 | [Putting it together](./wf_example_progression_7.md) | A comprehensive front-desk agent: routing, intake, scheduling, confirmation, plus a global emergency and end node. | composing many nodes/edges, multiple global nodes, larger real-world graph |

### Tools & external integrations

_Call Python tools, REST APIs, knowledge bases, and MCP servers; pick model providers._

| Step | Example | Teaches | New concepts |
|---|---|---|---|
| 8 | [Inline Python tools](./wf_example_progression_8.md) | Give an LLM callable Python tools to compute insurance quotes on demand. | InlinePythonToolConfig, LLM-invoked tools, tool args_schema |
| 9 | [Tools + runtime variables + branching](./wf_example_progression_9.md) | Run an assessment tool, store its result in a runtime variable, and branch on it. | result_runtime_variable_name, runtime variables [[...]], branching on tool output… |
| 10 | [Communication & transcript summary](./wf_example_progression_10.md) | End the call, summarise the transcript, and hand off to a (disabled) SMS node. | EndConversationNodeConfig, SendSMSNodeConfig, dynamic-variable templating in nodes… |
| 11 | [Dedicated tool node](./wf_example_progression_11.md) | Execute exactly one tool unconditionally with a ToolNodeConfig and read its result downstream. | ToolNodeConfig, EndRunNodeEvent, deterministic tool execution |
| 12 | [Calling a REST API](./wf_example_progression_12.md) | Call an external HTTP endpoint from the graph and let the LLM explain the response. | HttpRequestNodeConfig, HttpRequestNodeEvent, query parameters & timeouts |
| 13 | [Choosing LLM providers](./wf_example_progression_13.md) | Configure nodes to use alternative model providers (Azure / Google / Anthropic) and a platform default. | provider LLM configs, GlobalDefaultLLMConfig, per-node model selection |
| 14 | [Racing providers in parallel](./wf_example_progression_14.md) | Run several providers concurrently in an LLM group with patience windows and pick a winner. | LLMGroupConfig, OperationMode, max_patience_time_ms |
| 15 | [External API & knowledge-base tools](./wf_example_progression_15.md) | Let the LLM call a hosted REST tool and search a knowledge base, injecting secrets via dynamic variables. | ExternalAPIToolConfig, KnowledgeBaseToolConfig, secret injection via dynamic variables |
| 16 | [MCP server integration](./wf_example_progression_16.md) | Register Model Context Protocol servers at the workflow level and expose their tools to a node. | MCPServerConfig, use_mcp_tools |

### Composition, lifecycle & advanced control

_Compose sub-workflows, evaluate past runs, and control the run lifecycle._

| Step | Example | Teaches | New concepts |
|---|---|---|---|
| 17 | [Composing workflows (super nodes)](./wf_example_progression_17.md) | Embed a reusable sub-workflow inside a parent workflow as a single super node. | SuperNodeConfig, encapsulated_workflow_config, workflow composition |
| 18 | [Evaluation workflows](./wf_example_progression_18.md) | Fetch a completed run and score it with an evaluator LLM — a non-conversational, one-shot workflow. | WorkflowRunFetchNodeConfig, WorkflowRunEvalLLMNodeConfig, one-shot (non-conversational) runs |
| 19 | [Run lifecycle & commands](./wf_example_progression_19.md) | Drive the run lifecycle explicitly with WorkflowCommand and observe lifecycle events. | WorkflowCommand (START / DATA / …), lifecycle events, per-turn run control |
| 20 | [The full event catalog](./wf_example_progression_20.md) | A reference that handles every event type the runtime can emit. | complete event taxonomy, exhaustive event handling |
| 21 | [Advanced conditions & global escalation](./wf_example_progression_21.md) | Use structured condition arguments and a global escalation node with a reverse edge. | ConditionConfig args_schema, global_condition_evaluation_method, reverse_conditional_edge |
| 22 | [Backchannels](./wf_example_progression_22.md) | Emit natural filler while the main model is still thinking, using a backchannel group. | LLMGroupWithBackchannelConfig, SEQUENTIAL_WITH_PROACTIVE |

### Capstone

_Everything, together, in one production-shaped agent._

| Step | Example | Teaches | New concepts |
|---|---|---|---|
| 23 | [Capstone: full member-services agent](./wf_example_progression_23.md) | Synthesise the whole curriculum into one production-shaped agent. | WorkerLLM + backchannel group, external API + KB tools, global escalation + reverse edge… |

---

### A note on the dev environment

A few examples exercise capabilities that depend on the specific dev deployment or on external endpoints (e.g. LLM-invoked Python tools, alternative model providers, external REST/knowledge-base tools, MCP servers, super-node execution). Their placeholder endpoints/credentials are **not** live, so the corresponding notebooks are written to **degrade gracefully**: they build and create the workflow, attempt the run, and if the server returns an execution error they print a clear diagnostic and still clean up. The SDK usage they demonstrate is correct regardless.
