# Runtime: Server-Side Workflow Runtime

The SDK's `runtime` package gives you a `WorkflowRuntime.from_config(...)`
object with a `run(...)` / `arun(...)` event stream. Execution happens
remotely: all state (turn counter, message history, node state) lives on the
Interactly server, and `from_config(...)` takes a `client=` argument since the
workflow runs on the server.

```python
from interactly import AsyncWorkflowClient, AsyncWorkflowRuntime
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent

client = AsyncWorkflowClient()
runtime = await AsyncWorkflowRuntime.from_config(
    workflow_config_full,                    # WorkflowConfigFullyHydrated
    client=client,
    dynamic_variables={"company": "Acme"},
)

async for event in runtime.arun(WorkflowRunInput(thread_to_node_inputs={}, dynamic_variables={})):
    if isinstance(event, AssistantResponseEvent):
        print(f"agent> {event.response}")
```

You can also build a runtime straight off the client:

```python
runtime = await client.runtime.from_config(workflow_config_full)   # async
runtime = client.runtime.from_config(workflow_config_full)         # sync client
```

## Object model

| Type | Purpose |
|------|---------|
| `WorkflowRuntime` / `AsyncWorkflowRuntime` | Server-backed runtime. `from_config(config, *, client, ...)` uploads the config and returns a ready-to-run object; drive it with `run(...)` / `arun(...)`. |
| `client.runtime.from_config(config)` / `client.runtime(config)` | The same thing, off the client. |
| `WorkflowHandle` / `AsyncWorkflowHandle` | Lower-level base classes holding `(workflow_id, config, dynamic_variables, run_id)` and dispatching turns via `POST /v1/workflows/{id}/execute`. |
| `upload_and_get_handle(...)` / `aupload_and_get_handle(...)` | Back-compatible factory alias for `WorkflowRuntime.from_config`. |
| `client.workflows.create_from_config(config)` | Lower-level upload-only call. |
| `client.workflows.get_fully_hydrated(workflow_id)` | Fetch an existing workflow as a typed `WorkflowConfigFullyHydrated`. |
| `client.workflows.handle(workflow_id, dynamic_variables=...)` | Build a runtime/handle for an existing workflow without re-uploading. |

## Multi-turn semantics

The very first `runtime.run(...)` call omits `run_id`; the server creates a new
session and returns its identifier on the response.  The runtime stores that
`run_id` and replays it on every subsequent call — there is no client-side
state to keep track of beyond the runtime object itself.

```python
turn1 = list(runtime.run(input1))     # creates the session
print(runtime.run_id)                  # e.g. "run-abc123"
turn2 = list(runtime.run(input2))     # resumes the same session
```

Call `runtime.reset()` to forget the current `run_id` and start a fresh
session on the next turn.

## Dynamic variable merging

Variables you pass to the **runtime** are defaults; variables you pass to a
specific `WorkflowRunInput` override them.  Missing keys are filled in from
the runtime defaults:

```python
runtime = await AsyncWorkflowRuntime.from_config(config, client=client, dynamic_variables={
    "company": "Acme",
    "region": "us",
})

# This turn sees: company="Acme-EU" (overridden), region="us" (inherited).
await runtime.arun(WorkflowRunInput(
    thread_to_node_inputs={},
    dynamic_variables={"company": "Acme-EU"},
))
```

## Typed events

`handle.run()` / `handle.arun()` yield typed event objects from
`interactly.runtime.events` — `AssistantResponseEvent`,
`WorkerLLMNodeEvent`, `EndRunNodeEvent`, etc.  Unknown event types
(useful when the server is ahead of the SDK) fall back to a generic
`BaseEvent` rather than raising.

```python
from interactly.runtime.events import (
    AssistantResponseEvent,
    WorkerLLMNodeEvent,
    EndRunNodeEvent,
)

async for event in handle.arun(workflow_input):
    if isinstance(event, AssistantResponseEvent):
        print(event.response)
    elif isinstance(event, WorkerLLMNodeEvent):
        print(event.node_run_output)
    elif isinstance(event, EndRunNodeEvent):
        print("done")
```

## Execution model

| Aspect | Runtime / handle (SDK) |
|--------|------------------------|
| Where execution runs | On the Interactly server |
| Latency | One HTTPS round-trip per turn |
| State storage | Persisted server-side |
| Transport | REST (`POST /v1/workflows/{id}/execute`) |
| Multi-turn resumption | `run_id` echo |
| Typing | `WorkflowConfigFullyHydrated` |

## Event catalog

`handle.run()` / `handle.arun()` yield typed events from
`interactly.runtime.events`. Match on them with `isinstance`. Unknown types fall back
to a generic `BaseEvent` (so a newer server never breaks an older SDK). The main ones:

| Category | Events |
|---|---|
| Workflow lifecycle | `StartWorkflowEvent`, `EndWorkflowEvent`, `EndWorkflowIterationEvent`, `WorkflowErrorEvent`, `WorkflowWarningEvent`, `WorkflowDebugLogEvent`, `WorkflowNavigationEvent`, `WorkflowShowStateEvent` |
| Turn / thread | `AssistantResponseEvent`, `UserMessagesEvent`, `BusyWaitEvent`, `BusyWaitForUserMessageEvent`, `PauseEvent`, `StartThreadEvent`, `EndThreadEvent`, `PauseThreadEvent` |
| Node run | `StartRunNodeEvent`, `EndRunNodeEvent`, `SayLLMNodeEvent`, `WorkerLLMNodeEvent`, `SayStaticMessageNodeEvent`, `HttpRequestNodeEvent`, `SendSMSNodeEvent`, `StartConversationNodeEvent`, `EndConversationNodeEvent`, `AthenaNodeEvent`, `GoogleDocs*NodeEvent`, `ForceTransferToNodeEvent` |
| LLM detail | `BaseLLMNodeEvent`, `ConditionEvaluatorLLMNodeEvent`, `DiscardedMainLLMNodeEvent` |
| Edge | `DirectEdgeEvent`, `ConditionalEdgeEvent`, `CompanionEdgeEvent`, `ReverseConditionalEdgeEvent`, `SelfLoopEdgeEvent`, `GuardrailEscalationEdgeEvent` |
| Background execution | `CompanionStepBoundaryEvent`, `WaitingEvaluationBoundaryEvent`, `WaitingConditionMatchedEvent`, `WorkflowReadyForInputEvent` |
| Bounded self-loops | `SelfLoopDelayEvent`, `SelfLoopExhaustedEvent` (carries `SelfLoopOutcome`), `NodeExpiredEvent` |

The two you'll handle most often: **`AssistantResponseEvent`** (the assistant said something —
`event.content`) and **`BusyWaitForUserMessageEvent`** (the workflow is waiting for the user's next
message). Use `parse_event(raw_dict)` to deserialize a raw event dict into its typed instance.

### Background work

Once a workflow has [companion threads](guides/companion_threads.md) or
[evaluate-while-waiting edges](guides/waiting_evaluation.md), `EndWorkflowIterationEvent` stops
meaning "your turn" — companions may still be running. Wait for `WorkflowReadyForInputEvent`, which
also carries `active_companion_thread_ids`.

Every event exposes `thread_reference_id` as a **computed field**: `"0"` for the main thread, or the
companion's configured `thread_id`. It is derived from the internal thread id rather than stored, so
it is present on events written before the feature existed.

`should_persist_background_event(event)` mirrors the server's own rule: non-transitioning
`WaitingEvaluationBoundaryEvent`s recur on every background pass and are not written to the run
record, though they do arrive on the wire.

`EndWorkflowIterationEvent` carries `WorkflowIterationMetrics` — including
`IterationCallLatencyStats` and `StructuredOutputRetryMetadata` when an LLM call had to retry to
produce valid structured output.

See [`wf_examples/wf_example_progression_1.py`](../wf_examples/wf_example_progression_1.py) for an
end-to-end runnable example and [`wf_examples/README.md`](../wf_examples/README.md) for the full
curriculum of 25 progression examples
plus a 125-node telephone-triage workflow.
