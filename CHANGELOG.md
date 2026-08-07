# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Workflow-service sync (2026-08)

Brings the SDK back in line with the workflow service, which had drifted since 2026-07-20. The SDK
remains self-contained: no imports from `interactly-ai`, `common`, `beanie`, `bson` or `pymongo`.

#### Added
- **Re-runs** — `client.reruns`: `rerunnable_turns`, `preflight`, `create_token`, `preview_token`,
  `amend_token`, `execute`. Replay a finished run from any turn, optionally against a different
  workflow or version. Two preconditions worth knowing: only **WebSocket-driven** runs can be re-run
  (the config snapshot is written by `stream()`, not `execute()`), and a token is redeemed by passing
  `rerun_token=` to `stream()`. See [`docs/guides/reruns.md`](docs/guides/reruns.md).
- **Run feedback** — ratings and comments at turn and event level:
  `set_turn_rating`, `set_event_rating`, `delete_turn_rating`, `delete_event_rating`,
  `add_turn_comment`, `delete_turn_comment`. Every write returns the full list plus a
  `feedback_users` map. Refused with `409` while the run is still in progress.
  See [`docs/guides/run_feedback.md`](docs/guides/run_feedback.md).
- **Background work** — `client.runs.pump_companions()` and the bounded
  `client.runs.drive_background_work()`, plus `has_background_work` on `InteractiveRunResponse`.
  REST-driven runs do not advance companion threads on their own.
- **Companion threads** (`CompanionThreadConfig` on direct edges), **evaluate-while-waiting**
  (`EvaluateWhileWaitingConfig` on conditional edges) and **bounded self-loops** (`SelfLoopConfig` on
  nodes), with the `edge_is_companion` / `edge_companion_thread_id` /
  `edge_evaluates_while_waiting` / `edge_waiting_evaluation_config` accessors.
- **`NoOpNodeConfig`** — a node that runs and succeeds without doing anything: a fan-in junction, a
  placeholder, or a branch-testing stand-in. Not the same as `disabled=True`, which emits nothing.
- **Run lineage filters** — `client.runs.list(source_workflow_run_id=..., source_turn_index=...)`.
- **Tool portability** — `client.tools.export()` / `client.tools.import_bundle()`. Secrets are
  redacted on export; an `inline_python` bundle requires `confirm_executable=True`.
- **Streaming exceptions** — `InvalidStreamInputError` (close 4006) and `RerunTokenError`
  (close 4007), both subclasses of `StreamError`; and `BadRequestError` for graph-validation 400s,
  whose message joins the server's category and the specific rule that failed.
- Seven new event types re-exported from `interactly.runtime.events`:
  `CompanionStepBoundaryEvent`, `WaitingEvaluationBoundaryEvent`, `WaitingConditionMatchedEvent`,
  `WorkflowReadyForInputEvent`, `SelfLoopDelayEvent`, `SelfLoopExhaustedEvent`, `NodeExpiredEvent` —
  along with `GuardrailEscalationEdgeEvent`, `WorkflowIterationMetrics` and
  `should_persist_background_event`.
- **`is_system` on global variables** — `interactly_api_base_url` and `interactly_api_token` are
  provided automatically for every team and are read-only.
- **Drift harnesses** and their make targets: `make parity-check` (SDK configs vs. upstream source),
  `make schema-check` (vs. a live server's JSON schemas), `make refs-check` (symbols referenced in
  docs/notebooks/examples), `make api-docs-check` (generated API reference is current).

#### Changed
- **`client.runs.checkpoint()` removed.** The endpoint no longer exists server-side; `client.reruns`
  replaces it and does more.
- `client.runs.stream()` takes `rerun_token=`; a frame carrying `initial_state` is now rejected by
  the server with close code 4006.
- `WorkflowConfigFullyHydrated` upgrades each node through the discriminated union on validation.
  Previously, validating a plain `dict` against `SerializeAsAny[BaseNodeConfig]` coerced it to the
  base class and **silently discarded every subclass field**, so a fetch → modify → upload round trip
  lost most of the workflow. An unknown node type now falls back to an `extra="allow"` model rather
  than failing the whole workflow.
- `client.workflows.get_fully_hydrated()` unwraps the server's nested response shape, which had
  never returned a usable config.

#### Fixed
- `make install` had been broken since 2026-07-14: `pyproject.toml` still declared
  `license = { file = "LICENSE" }` after the root `LICENSE` was deleted, so metadata generation
  failed.
- `make typecheck` was checking nothing — two stray empty `__init__.py` files made mypy bail with
  "Source file found twice". Removing them surfaced 79 real type errors, all now fixed.
- `is_given()` returned `bool` rather than `TypeGuard[T]`, so narrowing never happened at any call
  site.

#### Docs
- New guides: [re-runs](docs/guides/reruns.md), [companion threads](docs/guides/companion_threads.md),
  [evaluate while waiting](docs/guides/waiting_evaluation.md),
  [self-loops](docs/guides/self_loops.md), [run feedback](docs/guides/run_feedback.md).
- `docs/streaming.md` rewritten. It had documented four `RunEvent` fields that do not exist, the
  wrong types for `is_terminal()`, a `run.output` attribute that does not exist, and the removed
  `checkpoint` endpoint.
- `wf_examples/internal/gen_api_reference.py` restored (it was referenced by both API-reference
  pages but absent from the repo, so the "generated" tables had been drifting by hand). `make
  api-docs` regenerates; `make api-docs-check` gates.

### Added
- **Direct tool execution**: `client.tools.execute(tool_id, args=...)` runs a saved tool with the given argument values and returns a typed `ToolExecuteResult` (`success`, `result`, `error`, `latency_ms`) — no workflow required. `client.tools.execute_inline(tool_config=..., args=...)` does the same for an unsaved config. Backed by new `POST /v1/tools/{id}/execute` and `POST /v1/tools/execute` endpoints on the Interactly Workflow API (with a wall-clock timeout; tool failures return `success=False` rather than an HTTP error). Note: inline-Python tools execute via unsandboxed `exec` server-side — intended for authoring/debugging within a team's own workspace.
- **Runtime surface**: `WorkflowRuntime` / `AsyncWorkflowRuntime` with `from_config(config, *, client, dynamic_variables=None, ...)` — a `from_config(...)` runtime that reads like an in-process runtime, the only difference being the `client=` argument (execution is remote). Exported from `interactly` and `interactly.runtime`.
- **`client.runtime`** accessor: `client.runtime.from_config(config)` / `client.runtime(config)` (async on `AsyncWorkflowClient`) to build a runtime straight off the client.
- `client.runs.execute(...)` now accepts the typed `WorkflowCommand` enum (in addition to a string) for `command`, plus an optional typed `run_input: WorkflowRunInput` (mutually exclusive with the loose kwargs).
- `client.runs.stream(...)` now accepts optional `dynamic_variables` / `runtime_variables` or a full typed `run_input: WorkflowRunInput`, forwarded on the WebSocket handshake (the server validates a full `WorkflowRunInput`).
- Typed-first resource params: `client.templates.create/update` accept a typed `WorkflowTemplateConfig`; `client.super_nodes.publish` accepts a typed `SuperNodeInterface`; `client.simulations.create/update` accept typed Pydantic models — all still accept plain `dict`s.
- New typed exports from `interactly.configs`: `WorkflowTemplateConfig`, `SuperNodeInterface`, `SuperNodeInputField`, `SuperNodeFieldMapping`, `SuperNodeFieldMappingTargetType`, `SuperNodeInputFieldValueType`.
- `NodeLibraryConfig` is now exported from `interactly_configs` and the `interactly.configs` facade, so `client.node_libraries.create(node_library_config=NodeLibraryConfig(...))` matches the typed-first pattern documented in the reusable-assets guide.
- `tests/integration/test_runtime_e2e.py` — opt-in (`-m integration`) live dev-environment E2E test with tagged assets and self-cleanup.
- `configs/README.md` — enables editable installs of the `interactly-configs` package.

### Docs
- Corrected stale references in the guides and generated API reference: `client.workflows.retrieve(...)` → `client.workflows.get(...)` (the real method name), and the API-reference generator (`wf_examples/internal/gen_api_reference.py`) now emits library-style `from interactly import ...` imports.
- Fixed the exception hierarchy in `docs/error_handling.md`: `APITimeoutError` is shown nested under `APIConnectionError`, `NoMorePagesError` and `StreamError` are listed, and `WebhookVerificationError` is called out as a standalone `Exception` (not an `InteractlyError`).
- Regenerated `docs/api_async.md` / `docs/api_sync.md` from the current resource classes (method descriptions and updated signatures now match the code).


### E2E validation tooling & fixes (dev server)
- **`notebooks/_run_e2e.py`** — headless runner that executes every docs notebook against a live Interactly server and reports per-notebook PASS/FAIL. All 17 notebooks now pass end-to-end against dev.
- **`wf_examples/_run_e2e.py`** — non-interactive driver that uploads each `wf_example_progression_*` config and drives canned turns (or `--upload-only`). All 23 example configs upload; 20/23 run full turns with real LLM output (the other 3 require external setup: multi-provider credentials, a published super-node sub-workflow, and workflow-run-fetch team context).
- `tests/integration/test_runtime_e2e.py` now also covers **turn execution** (static + opt-in real-LLM), not just CRUD; its stale "execute returns 500" note was removed.

Real SDK bugs the E2E runs surfaced and fixed (all confirmed against dev):
- **Interactive `execute`/`stream` never seeded a thread** — a bare `command` (e.g. `START`) sent an input with no `thread_to_node_inputs`, so the runtime rejected every run with "Found 0 threads". Both the loose `execute` body and the WS stream payload now seed the default thread `"0"`.
- **WebSocket streaming auth** — the gateway authenticates WS upgrades with a single-use `?token=` session (minted from `GET {gateway_root}/v1/session`), not the bearer JWT; `client.runs.stream` now mints and appends that token (falling back to header auth when no gateway session endpoint exists).
- **`Run` never matched the server shape** — the workflow-runs endpoints return a nested `{"workflow_run": {..., "workflow_run": {...state...}}}` document; the `Run` model now flattens both layers so `runs.get`/`runs.list` validate.
- **`RunEvent` rejected the stream handshake frame** — the initial ack frame carries a `message` but no `type`; the model now synthesises a `run_ack` type and surfaces `origin_node_logical_id`→`node_id` / `content`→`output`.
- **`add_comment` cast the whole run to `RunComment`** — the endpoint echoes the updated run; `RunComment` now extracts the newest comment from that envelope.
- **Resource `.id` was `None`** — `Node`, `Edge`, `Tool`, `NodeLibrary`, `Template`, `Schedule`, `GlobalVariable`, `Simulation`/`SimulationGroup`/`SimulationRun` now map the server `_id` onto `id`; **`LLMConfig.id`** maps from the logical `llm_config_id` the endpoints actually address by.
- **`Node`/`NodeLibrary` config lost its subclass** — `node_config` now validates through the discriminated `NodeConfig` union, so `fetched.node_config` is the concrete subclass (e.g. `SayLLMNodeConfig`) with its `type`.
- **Paginated lists returned 0 items for many resources** — `_extract_items` recognised only a few envelope keys; it now falls back to the first non-metadata list, fixing global-variables/webhooks/runs/etc. `SyncPage`/`AsyncPage` also expose `total`/`page_number`/`size`/`pages`.
- **`workflows.versions.activate` cast a workflow to a version** — it returns the updated `Workflow`; the return type is corrected.
- **`workflows.clone` always 500'd** — the server requires at least one version selected; `clone` now defaults to `clone_all_versions=True` and accepts `version_numbers`/`description`/`fallback_active_version`.
- **`Workflow.name` is now optional** — listing no longer crashes on incomplete workflows (null `workflow_config`).
- `Tool` and `Simulation` expose convenience `name` / `description` read from their config.


### Changed
- **Library-style imports**: the SDK and its docs/notebooks/examples now import as an installed package — `import interactly` / `import interactly_configs` — with no `sys.path` hacks. All internal imports migrated from `workflow_sdk.src.interactly` to `interactly` (and `workflow_sdk.configs.src.interactly_configs` to `interactly_configs`). Editable-install locally with `pip install -e workflow_sdk -e workflow_sdk/configs`; the notebook/example bootstraps still work without installing.
- Notebooks 09 & 16 and `docs/runtime.md` now lead with `WorkflowRuntime` / `AsyncWorkflowRuntime` (`aupload_and_get_handle` / `WorkflowHandle` remain available as back-compatible aliases).

### Fixed
- **Hydrated workflow authoring now round-trips through the server.** Two config-fork
  serialization bugs made every SDK-authored workflow un-runnable (interactive execution
  returned `500 "No start node found"`):
  - `WorkflowConfigFullyHydrated.node_configs` was typed `List[BaseNodeConfig]`, so
    serialization dropped each node's `type` discriminator (and subclass payload). The
    server's discriminated `NodeConfig` union then couldn't retag the nodes, the
    `Union[WorkflowConfigFullyHydrated, WorkflowConfig]` create body fell back to the bare
    `WorkflowConfig` branch, and the workflow was created **with no nodes/edges**. Fixed by
    typing `node_configs` as `List[SerializeAsAny[BaseNodeConfig]]`.
  - `interactly.configs.WorkflowRunInput` exported a stripped variant that **omitted
    `thread_to_node_inputs`** (plus `start_node_logical_id` / `initial_state`), so no
    interactive turn ever carried its per-thread node inputs (the runtime rejected it with
    "Found 0 threads in workflow input"). The facade now exports the complete
    `WorkflowRunInput`. Verified end-to-end against dev (`create_from_config` →
    `AsyncWorkflowRuntime.arun` → terminal `EndWorkflowEvent`).
- `client.workflows.create_from_config(...)` now persists the workflow **name** (and description): the hydrated-create endpoint reads `name` from the top level of the request body, not from the nested `workflow_config`. Previously the created workflow's name came back `null`. Verified against the dev environment.

### Added (previously)
- `client.runs.add_event_comment(run_id, event_logical_id, *, content)` — add a comment on a specific run event (`POST /workflow-runs/{id}/events/{event_id}/comments`).
- `client.runs.delete_event_comment(run_id, event_logical_id, comment_logical_id)` — remove an event-level comment.
- `client.runs.schema()` — fetch the JSON schema for workflow run objects (`GET /workflow-runs/schema`).
- `docs/streaming.md` — WebSocket streaming guide.
- `docs/retries.md` — retry and timeout configuration guide.
- `docs/versioning.md` — SDK versioning policy and workflow versioning guide.
- `examples/error_handling.py` — comprehensive error-handling example.
- `examples/pagination.py` — all pagination patterns (single page, `list_all()`, manual, async).
- `examples/webhook_receiver.py` — FastAPI webhook receiver with signature verification.
- `scripts/detect-breaking-changes.py` — AST-based public API surface comparator.
- `api_surface_baseline.json` — saved API surface snapshot (83 exports, 216 methods across 32 classes).
- `bitbucket-pipelines.yml` — CI/CD pipeline with Python 3.10 / 3.11 / 3.12 test matrix and publish-on-tag step.
- `notebooks/01_quickstart.ipynb` — end-to-end quickstart: install, authenticate, create workflow, stream a run.
- `notebooks/02_build_a_workflow.ipynb` — nodes, edges, versioning, clone, diff walkthrough.
- `notebooks/03_streaming_events.ipynb` — sync/async streaming, event-type reference, checkpoint, execute.
- `notebooks/04_pagination_and_filtering.ipynb` — `list_all()`, manual `next_page()`, async pagination, count-without-fetching pattern.
- `notebooks/05_error_handling.ipynb` — full exception hierarchy, retry config, structured logging, raw response headers.
- `SECURITY.md` — vulnerability disclosure policy (responsible disclosure, CVSS-based SLAs, security best practices).
- **`interactly-configs` package** (`interactly-configs/`) — pure-Pydantic ≥2.0 config types for authoring workflows, with zero server-side dependencies. Installable via `pip install "interactly[configs]"`. Includes 51 tests.

---

## [0.1.0] — 2026-04-30

### Added
- `WorkflowClient` and `AsyncWorkflowClient` — sync and async top-level clients with env-var credential resolution (`INTERACTLY_API_KEY`, `INTERACTLY_TEAM_ID`, `INTERACTLY_USER_ID`, `INTERACTLY_BASE_URL`).

**`client.workflows`**
- `create`, `get`, `update`, `delete`, `list` (paginated), `clone`, `export`, `import_bundle`, `schema`, `dynamic_variables`, `update_concurrency`.

**`client.workflows.versions`**
- `create`, `list`, `activate`, `update`, `update_config`, `delete`, `diff`.

**`client.runs`**
- `stream` (WebSocket, sync and async context manager), `list` (paginated), `get`, `delete`, `evaluation_result`, `add_comment`, `delete_comment`, `execute`, `checkpoint`.

**`client.webhooks`**
- `create`, `list`, `get`, `update`, `delete`, `list_events`, `list_delivery_attempts`, `retry_event`.

**`client.schedules`**
- `create`, `list` (per-workflow), `list_all` (cross-team), `get`, `update`, `cancel`.

**`client.templates`**
- `schema`, `create`, `list`, `get`, `update`, `delete`.

**`client.categories`**
- `list`.

**`client.nodes`**
- `types`, `schema`, `create`, `list`, `get`, `update`, `delete`.

**`client.edges`**
- `types`, `schema`, `create`, `list`, `get`, `update`, `delete`.

**`client.super_nodes`**
- `list`, `get`, `schema`, `publish`, `unpublish`.

**`client.tools`**
- `types`, `schema`, `inbuilt`, `create`, `list`, `get`, `update`, `delete`.

**`client.global_variables`**
- `create`, `bulk_create`, `list`, `get`, `update`, `delete`, `resolve`.

**`client.node_libraries`**
- `schema`, `create`, `list`, `get`, `update`, `delete`.

**`client.simulations`**
- `schema`, `create`, `list`, `get`, `update`, `delete`, `run`, `list_runs`, `get_run`, `stop_run`, `list_executions`, `evaluation_summary`, `list_detailed_executions`.

**`client.copilot.workflows`**
- `schema`, `ws_url`.

**`client.copilot.medical`**
- `schema`, `ws_url`.

**Infrastructure**
- Real-time WebSocket streaming via `Stream[T]` (sync) and `AsyncStream[T]` (async).
- Paginated responses: `SyncPage[T]` and `AsyncPage[T]` with `list_all()` and `next_page()`.
- Full exception hierarchy: `InteractlyError`, `APIError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `ConflictError`, `UnprocessableEntityError`, `RateLimitError`, `InternalServerError`, `APIConnectionError`, `APITimeoutError`.
- `NOT_GIVEN` sentinel for distinguishing omitted PATCH fields from `None`.
- `verify_signature()` webhook helper with optional replay-protection via `X-Interactly-Timestamp`.
- Automatic retry with exponential back-off and jitter (default 2 retries; 429 + 5xx + network errors).
- `py.typed` PEP 561 marker — SDK ships its own type stubs.
- `noxfile.py` — multi-Python test matrix (3.10, 3.11, 3.12).
- `Makefile` — `lint`, `test`, `format`, `build` targets.
- `api.md` — flat method reference for all 17 resources.
- `docs/authentication.md`, `docs/error_handling.md`, `docs/pagination.md` — reference guides.
- `examples/quickstart.py`, `examples/async_demo.py` — runnable quickstart scripts.
- 215 unit tests covering all resources, retry logic, pagination, webhooks, and `NOT_GIVEN` semantics.

