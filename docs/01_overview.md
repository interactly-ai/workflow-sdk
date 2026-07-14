# 1. Overview

The Interactly Workflow SDK is a Python client for building **AI conversational workflows as code**.
Anything you can build in the Interactly dashboard — a routing agent, a tool-calling assistant, a
multi-step intake flow — you can express as typed Python objects, deploy to the server, run, and
operate, all from a script or notebook.

## What is a workflow?

A **workflow** is a directed graph:

- **Nodes** do the work — an LLM turn that talks to the user (`say_llm`), a background worker that
  extracts data (`worker_llm`), a tool call, an HTTP request, an SMS, a conversation start/end, and more.
- **Edges** connect nodes and decide what happens next — always (`direct`), based on a condition
  (`conditional`), or in parallel (`companion`).

At runtime the workflow drives a conversation: it speaks, waits for the user, branches on what they
say, calls tools, and eventually ends. The server holds all the state; your code steers it.

## What the SDK gives you

| You want to… | The SDK offers |
|---|---|
| **Author** a workflow as code | Typed config classes (`SayLLMNodeConfig`, `DirectEdgeConfig`, …) via the `[configs]` extra |
| **Deploy** it | `client.workflows.create` / `create_from_config`, versions, publish, clone, export/import |
| **Run** it | `client.runs.stream` (WebSocket), `client.runs.execute` (turn-by-turn), or a runtime `handle` |
| **Operate** it | Runs, evaluations, comments, schedules, webhooks, simulations, global variables |

## Two layers: authoring vs. execution

The SDK cleanly separates the two things you do with a workflow:

1. **Authoring** — you construct a `WorkflowConfigFullyHydrated` from config classes. This is pure data;
   it describes *what the workflow is*. See [Typed configs](configs.md).
2. **Execution** — you upload that config and the **server** runs it. A `WorkflowHandle` is a thin
   client-side reference; every turn's state (session, history, node state) lives server-side. See
   [Runtime handles](runtime.md).

This split is why the same workflow can be created once and then run, scheduled, simulated, or
monitored independently.

## Async and sync

Every capability comes in two forms with identical surfaces. **The async client is the preferred
way to use the SDK** — workflows are I/O-bound (network round-trips, streamed events), so `await`
lets your program stay responsive:

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:   # preferred
    workflow = await client.workflows.get("wf-123")
```

A synchronous `WorkflowClient` mirrors it method-for-method (same names, no `await`) for scripts,
notebooks-without-async, and quick experiments:

```python
from interactly import WorkflowClient

with WorkflowClient() as client:               # convenience fallback
    workflow = client.workflows.get("wf-123")
```

These docs lead with the **async** client throughout; each page ends with a short **Synchronous
alternative** note. See [Core concepts → house style](03_concepts.md#house-style-async-first-typed-first).

## When to use the SDK (vs. the dashboard)

Use the SDK when you want workflows under version control, generated programmatically, tested in CI,
batch-simulated, or embedded in a larger Python service. Use the dashboard for visual editing and
one-off changes. They operate on the same workflows — the SDK is just the code path.

---

**Next:** [2. Installation & setup →](02_installation.md)
