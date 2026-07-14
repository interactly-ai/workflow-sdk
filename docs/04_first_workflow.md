# 4. Your first workflow

Let's build a small workflow **as code**, upload it, and hold a conversation with it. This is the
canonical example reused across the docs, [`notebooks/02`](../notebooks/02_interactive_workflow.ipynb), and
[`wf_examples/wf_example_progression_1.py`](../wf_examples/wf_example_progression_1.py).

The workflow: greet the user → an assistant that answers questions and loops until they say goodbye →
a static sign-off.

```
 start ▶ Greeting (say_llm) ─direct▶ Assistant (say_llm, self-loop) ─conditional("goodbye")▶ End (static)
```

This needs the [`[configs]` extra](02_installation.md#the-configs-extra-typed-authoring) and
`langchain-core` for the interactive turns.

## 1. Author the config

```python
from interactly.configs import (
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
    SayLLMNodeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    DirectEdgeConfig,
    ConditionalEdgeConfig,
    ConditionConfig,
    PromptConfig,
    OpenAILLMConfig,
    OPENAIModel,
)

# LLM settings the nodes will use
fast_llm = OpenAILLMConfig(model=OPENAIModel.GPT_5_4_NANO, max_tokens=40, temperature=0.5)
main_llm = OpenAILLMConfig(model=OPENAIModel.GPT_5_4, max_tokens=300, temperature=0.2)

# --- Nodes ---
greeting = SayLLMNodeConfig(
    name="Greeting",
    description="Greets the user.",
    is_start=True,                 # entry node
    self_loop=False,
    wait_for_user_message=False,   # speak immediately, don't wait first
    main_response_config=PromptConfig(prompt="Greet the user warmly in under 15 words and ask how you can help."),
    llms_config=fast_llm,
)

assistant = SayLLMNodeConfig(
    name="Assistant",
    description="Answers the user's questions.",
    self_loop=True,                # keep handling turns...
    wait_for_user_message=True,    # ...waiting for each user message
    main_response_config=PromptConfig(prompt="You are a concise, helpful assistant. Answer in <= 3 sentences."),
    llms_config=main_llm,
)

end = SayStaticMessageNodeConfig(
    name="End",
    description="Signs off.",
    static_messages_config=StaticMessagesConfig(static_messages=["Thanks for chatting. Goodbye!"]),
)

# --- Edges ---
greeting_to_assistant = DirectEdgeConfig(
    source_node_logical_id=greeting.logical_id,
    destination_node_logical_id=assistant.logical_id,
    name="Start assisting",
)

assistant_to_end = ConditionalEdgeConfig(
    source_node_logical_id=assistant.logical_id,
    destination_node_logical_id=end.logical_id,
    name="End on goodbye",
    condition=ConditionConfig(
        condition_freeform="The user says goodbye or indicates they're done (e.g. 'that's all', 'bye')."
    ),
)

# --- Assemble the graph ---
config = WorkflowConfigFullyHydrated(
    workflow_config=WorkflowConfig(name="My First Workflow", description="A greet → assist → end demo."),
    node_configs=[greeting, assistant, end],
    edge_configs=[greeting_to_assistant, assistant_to_end],
)
```

Notes:
- Each node auto-generates a `logical_id`; edges reference those IDs to wire the graph.
- `self_loop=True` + `wait_for_user_message=True` is the pattern for a node that keeps talking with the
  user until an edge condition sends it elsewhere.

## 2. Upload and get a handle

The **server** runs the workflow. `aupload_and_get_handle` creates the workflow from your config and
returns a thin [handle](runtime.md) you drive turn-by-turn. We use the **async** client throughout
(the preferred way to use the SDK — see [house style](03_concepts.md#house-style-async-first-typed-first)):

```python
from interactly import AsyncWorkflowClient, aupload_and_get_handle

client = AsyncWorkflowClient()   # reads INTERACTLY_* env vars
handle = await aupload_and_get_handle(client, config, dynamic_variables={})
print("Uploaded workflow id =", handle.workflow_id)
```

## 3. Run a turn and read events

Each turn you send a `WorkflowRunInput` and iterate the typed events it emits with `async for`.

```python
from langchain_core.messages import HumanMessage
from interactly.configs import WorkflowRunInput, NodesRunInputs, LLMNodeRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent

async def send(text: str):
    run_input = WorkflowRunInput(
        thread_to_node_inputs={"0": NodesRunInputs(node_run_inputs=[LLMNodeRunInput(messages=[HumanMessage(content=text)])])},
        dynamic_variables={},
    )
    async for event in handle.arun(run_input):
        if isinstance(event, AssistantResponseEvent):
            print(f"ASSISTANT ({event.origin_node_name}): {event.content}")
        elif isinstance(event, BusyWaitForUserMessageEvent):
            print(f"[{event.origin_node_name} is waiting for your reply]")

await send("Hi there!")
await send("What can you help me with?")
await send("That's all, thanks. Goodbye!")   # triggers the conditional edge → End
```

The first turn creates a server-side session; subsequent turns resume it automatically (the handle
remembers the `run_id`). See [Runtime handles](runtime.md) for the full event catalog and multi-turn
semantics.

For a complete runnable version with an interactive stdin loop, see
[`wf_examples/wf_example_progression_1.py`](../wf_examples/wf_example_progression_1.py)
(`python wf_examples/wf_example_progression_1.py`).

## 4. Clean up

```python
await client.workflows.delete(handle.workflow_id)
await client.close()
```

## Where to go next

- Prefer creating the workflow without a handle? Use `client.workflows.create_from_config(config, name=...)`
  — see [Workflows & versions](guides/workflows_and_versions.md).
- Stream events over a WebSocket instead: [Running workflows](guides/running_workflows.md) and [Streaming](streaming.md).
- Layer in tools, routing, and more: walk the [`wf_examples/` ladder](../wf_examples/README.md).

## Synchronous alternative

Prefer a plain script without `async`/`await`? The synchronous `WorkflowClient` mirrors every call —
use `upload_and_get_handle` (no `a` prefix), `handle.run(...)` with a normal `for`, and `client.close()`:

```python
from interactly import WorkflowClient, upload_and_get_handle

client = WorkflowClient()
handle = upload_and_get_handle(client, config, dynamic_variables={})

def send(text: str):
    run_input = WorkflowRunInput(
        thread_to_node_inputs={"0": NodesRunInputs(node_run_inputs=[LLMNodeRunInput(messages=[HumanMessage(content=text)])])},
        dynamic_variables={},
    )
    for event in handle.run(run_input):        # plain for, no await
        if isinstance(event, AssistantResponseEvent):
            print(f"ASSISTANT ({event.origin_node_name}): {event.content}")

send("Hi there!")
client.workflows.delete(handle.workflow_id)
client.close()
```

---

**Next:** [5. Running workflows →](guides/running_workflows.md) · or browse the [capability guides](README.md#capability-guides)
