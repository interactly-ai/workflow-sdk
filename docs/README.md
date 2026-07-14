# Interactly Workflow SDK — Documentation

Welcome. This is a guided tour of the SDK: read it top-to-bottom to go from "what is this?" to
building, running, and operating real workflows — or jump straight to a capability guide.

> **New here? Follow the tour in order (1 → 6).** Each step builds on the previous one.

## The tour

| # | Page | What you'll learn |
|---|---|---|
| 1 | [Overview](01_overview.md) | What the SDK is, what it's for, and the big picture |
| 2 | [Installation & setup](02_installation.md) | Running in-repo, credentials, the `[configs]` extra |
| 3 | [Core concepts](03_concepts.md) | Workflows, nodes, edges, tools, super-nodes, configs, runtime |
| 4 | [Your first workflow](04_first_workflow.md) | Build, upload, and run a workflow end-to-end |
| 5 | [Running workflows](guides/running_workflows.md) | Streaming, `execute`, and runtime handles |
| 6 | [Monitoring runs](guides/monitoring_runs.md) | Inspect runs, evaluations, and comments |

## Capability guides

Focused how-tos for each part of the API. Reach for these once you know the basics.

- [Workflows & versions](guides/workflows_and_versions.md) — CRUD, clone, export/import, favorites, versioning
- [Nodes, edges & tools](guides/nodes_edges_tools.md) — the building blocks and how to author them
- [Running workflows](guides/running_workflows.md) — stream vs. execute vs. handle
- [Monitoring runs](guides/monitoring_runs.md) — runs, evaluations, comments
- [Scheduling](guides/scheduling.md) — schedule workflow runs
- [Webhooks](guides/webhooks.md) — subscriptions, delivery, and signature verification
- [Simulations](guides/simulations.md) — batch-test workflows against samples
- [Global variables](guides/global_variables.md) — team-scoped variables
- [Super nodes](guides/super_nodes.md) — publish and reuse workflows as nodes
- [Reusable assets](guides/reusable_assets.md) — node libraries, templates, categories
- [LLM configs](guides/llm_configs.md) — named/team LLM configurations

## Reference & topics

- [API reference (async)](api_async.md) — every resource method, `await`-style (generated from source)
- [API reference (sync)](api_sync.md) — the same methods on the synchronous client
- [Typed configs](configs.md) — authoring workflows with the `[configs]` extra
- [Runtime handles](runtime.md) — server-backed execution handles and the event catalog
- [Streaming](streaming.md) — WebSocket event streaming
- [Pagination](pagination.md) — working with `SyncPage` / `AsyncPage`
- [Authentication](authentication.md) — credentials and headers
- [Error handling](error_handling.md) — the exception hierarchy
- [Retries](retries.md) — automatic retries and timeouts
- [Versioning](versioning.md) — workflow versioning + SDK semver policy

## Other surfaces

- [`../notebooks/`](../notebooks/) — runnable, interactive lessons (start at `00_index.ipynb`)
- [`../wf_examples/`](../wf_examples/) — complete workflow-authoring examples, simple → complex
- [`../README.md`](../README.md) — the SDK's front door

---

**Conventions in these docs** (full detail in [Core concepts → house style](03_concepts.md#house-style-async-first-typed-first)):

- **Async-first.** The `AsyncWorkflowClient` (with `async with` + `await`) is the preferred way to use
  the SDK, and every page leads with it. The synchronous `WorkflowClient` mirrors it method-for-method;
  each page ends with a short **Synchronous alternative** note.
- **Typed-first.** Examples author workflows with the typed `interactly.configs` classes; plain `dict`
  configs are also supported and shown as a fallback.
- **Library-style imports.** All code uses `from interactly import …` / `import interactly_configs`,
  like any installed package (editable-install for local dev, or use the in-repo bootstrap). Clients
  are built from `INTERACTLY_*` environment variables.
