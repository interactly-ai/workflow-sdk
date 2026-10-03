# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Docs
- **Three examples in the running-workflows guide never delivered the user's message.**
  - "Typed Execution" used thread key `"thread_0"` and a plain dict for the node input. That constructs
    without error but is dropped, so the run started with no message. The key is `"0"`, and the entry a
    `NodesRunInputs` of `LLMNodeRunInput`s.
  - "Run the handle" and "Pattern 3" used `command="continue"`, which is not a `WorkflowCommand` and
    fails validation. They also passed the caller's text as a dynamic variable rather than as a message.
  - All three now send `{"type": "human", "content": ...}` messages on thread `"0"`, with `START` then
    `DATA`. Shown working live, with no `langchain_core` needed.
- **The export-bundle gotcha** listed keys the bundle does not have. It now describes the real `v2`
  bundle: `versions` entries each holding a fully-hydrated `workflow_config`, plus `warnings`.
- **Checked, and correct as written:** rerun `message_appends` take role `"user"` / `"assistant"`.

### Notebooks
- **`10_llm_configs` no longer leaves the team without a default LLM config.** It creates its demo config
  with `override_default=True`, which takes the default flag from the config that held it, and then
  deletes the demo config. It now records the team's default first and restores it in Cleanup.

---

## [0.3.0] — 2026-10-03

Brings the SDK in line with the workflow service as of `interactly-ai@07a14e7da` (2026-10-02). The
vendored configs have no structural difference from upstream source and none from the live dev server's
published schemas. Install both packages at 0.3.0: `pip install "interactly[configs]>=0.3.0"`.

### Upgrading from 0.2.0

The changes that can alter what existing code does:

- **`tools.update(tool_config=<typed config>)` now sends only the fields you set.** Before, it sent every
  field, so an update wiped the tool's other fields and changed its `logical_id`. Code that relied on
  replacing the whole config must now set every field it wants changed. A dict is still sent as given.
- **`llm_configs.update(config=...)` keeps the stored API key** when `config` has none
  (`preserve_api_key=True`). With an admin token, pass `preserve_api_key=False` to remove a key.
- **Companion threads stop when the conversation does**, on a server that includes
  `interactly-ai@310a9a8ec`. Set `CompanionThreadConfig(stop_with_main_thread=False)` for work that must
  outlive it.
- **Retired models are gone from the enums:** `gpt-5.2-chat-latest`, `gpt-5.3-chat-latest`,
  `claude-opus-4-1-20250805`. A config naming one fails validation.
- **`CustomLLMConfig.okta_auth` is now `integration_auth`** (the old keyword is still accepted on
  construction; reading `.okta_auth` raises `AttributeError`).
- **`runs.list()` refuses a `start`–`end` window over 31 days** (`BadRequestError`).
- **The `configs` extra requires `interactly-configs>=0.3.0`.** `interactly.configs` re-exports names that
  only exist from 0.3.0, so with an older configs package `import interactly.configs` fails.

### Added
- **`secret_variables` on `BaseRunInput` and `WorkflowConfigFullyHydrated`.** Mirrors the server field
  that carries credential-valued variables apart from `dynamic_variables`, with `exclude=True`,
  `repr=False` and `SecretStr` values, so a run input can be serialised, logged and cached without
  emitting them. The server populates it from team globals; because `exclude=True` also keeps it out of
  a serialised request body, a value set client-side is dropped before the request is sent. It is
  mirrored so this package's models are shaped like the server's, not because there is a reason to fill
  it in. Adding it to the two base classes closed **22** parity differences — the field was being
  reported once per `*RunInput` subclass.
- **`IntegrationAuthConfig`**, and **`integration_auth` on `ExternalAPIToolConfig`** — the second of the
  two fields the rename below introduced upstream.
- **Four LLM providers served through Google Vertex AI:** `XAILLMConfig` (Grok), `GemmaLLMConfig`,
  `GLMLLMConfig` and `DeepSeekLLMConfig`, with `XAIModel`, `GemmaModel`, `GLMModel`, `DeepSeekModel`, the
  matching `LLMProvider` members, and membership in `LLMConfigUnion`. None takes an API key: the server
  authenticates with its Google Cloud credentials. All four are served only on Vertex's global endpoint
  (`*_VERTEX_GLOBAL_ONLY`), so leave `vertex_location` blank or `"global"`. Gemma, GLM and DeepSeek have
  `enable_thinking`, off by default. Note `DeepSeekLLMConfig`'s documented weakness on conditional edges.
- **Backend selection.** `AnthropicLLMConfig.backend` (`AnthropicBackend`: `direct` by default, or
  `vertex`) with `vertex_project` / `vertex_location`; `GoogleLLMConfig.backend` (`GoogleBackend`:
  `ai_studio` / `vertex`, unset by default, which keeps the server's own choice).
  `vertex_selectable_anthropic_models()` returns what the Vertex backend accepts:
  `VERTEX_SUPPORTED_ANTHROPIC_MODELS` minus `VERTEX_DISABLED_ANTHROPIC_MODELS` (Opus 5, withheld on cost).
- **`GoogleLLMConfig.thinking_level`** (`GeminiThinkingLevel`, in the new `interactly_configs.gemini_models`)
  for the Gemini 3 models that take a level instead of a token budget. Accepts any casing.
- **Models:** `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-audio-1.5`, `gpt-audio-mini`,
  `gemini-3.8-flash`, `gemini-3.7-flash`.
- **Capability data:** `AUDIO_INPUT_OPENAI_MODELS`, `REJECTS_TRAILING_MODEL_TURN_GOOGLE_MODELS`,
  `VISION_BEDROCK_MODELS`. Upstream keeps these inside the enums as `enum.nonmember`; that is 3.11+, so
  the mirror hoists them, qualifying a name with its provider where it would otherwise be ambiguous.
- **`CustomLLMConfig.supports_audio_input`**, off by default.
- **`CodebaseFunctionToolConfig`** and `ToolType.CODEBASE_FUNCTION`: a tool that calls a function
  registered in the platform's codebase, named by `function_id`. **Staff-only**: the server refuses to
  create, update, execute or list one for any role below super-admin. It is mirrored so that a customer
  reading a workflow staff configured with one can parse it. Note `tool_id` means a saved tool document
  here, the opposite of `InbuiltFunctionToolConfig`. Its binding check mirrors the inbuilt one: a no-op
  unless signatures are registered with `register_codebase_function_arguments`.
- **`ExternalAPIToolConfig.result_as_media`**: return the response body as media (a recording or an
  image) rather than parsing it. The result variable holds a `media://` handle, so combining it with
  `result_variable_mappings` or `expand_result_into_runtime_variables` is rejected.
- **`CompanionThreadConfig.stop_with_main_thread`** and `edge_companion_stops_with_main_thread()`. See
  *Changed* for what the default means.
- **`WorkflowConfig.voice_persona`** (at most `VOICE_PERSONA_MAX_LENGTH` = 600 characters): who the voice
  of a GPT-Live call through this workflow is. **`WorkflowConfigFullyHydrated.generated_voice_persona`** and
  `resolved_voice_persona()`, which prefers the hand-written one.
- **`WorkflowCopilotCommand.FINISH`**: ends a copilot conversation for good, where `STOP` only hangs up.
- **`interactly_configs.utils.extract_dynamic_variables(*configs)`**: the `{{variables}}` any set of
  configs references, for callers holding something other than a whole workflow.
- **`NodeRealtimeOverrides`** and `realtime_overrides` on every LLM node: per-node realtime voice
  settings (reasoning effort, voice, preamble mode, turn detection, and transcription keywords that bias
  speech recognition for that node only). Everything defaults to "inherit from the workflow", and the
  whole object is ignored unless the workflow runs on a realtime model.
- **Copilot proposals.** `ProposalOutput` (with `ProposedChangeItem` and `ProposalGraph`) joins
  `WorkflowCopilotOutput`: a change the copilot has worked out but not made, for a person to accept or
  decline. Also `WorkflowCopilotTurnDoneEvent`, the top-level signal that a turn has finished;
  `WorkflowCopilotCommand.NEW_CHAT`; and `session_id` / `page_context` on `WorkflowCopilotInput`. These
  live in `interactly_configs.workflow_copilot` and, like the rest of that module, are not re-exported at
  the package top level.
- **`tools.clone(tool_id, *, name=...)`**: duplicate a saved tool in your team, secrets included,
  named `"<source> (Clone)"` unless a name is given. A plain inbuilt tool cannot be cloned
  (`PermissionDeniedError`).
- **`tools.codebase_functions()` and `tools.get_codebase_function(function_id)`**: the catalogue a
  `CodebaseFunctionToolConfig` can name, as `CodebaseFunctionCatalogue` / `CodebaseFunction`.
  **Interactly-staff only**: for any role below super-admin the server refuses, and these raise
  `PermissionDeniedError`.
- **`workflows.lints(workflow_id, *, version_number=None)`** → `WorkflowLintReport`: every advisory lint
  for a stored workflow, graph-wide and after super-node expansion. The only way to catch a cross-thread
  reference to a missing thread, or a waiting condition that could never fire, for a workflow built a
  node at a time.
- **`workflows.realtime_compatibility(workflow_id, *, version_number=None, model=None)`** →
  `RealtimeCompatibilityReport`: whether the workflow can run on a realtime (speech-to-speech) model,
  with typed `blockers`, `warnings` and `indeterminate` findings. Pass `model` to judge against the
  realtime model the call would actually use.
- **`workflows.counter_workflow(workflow_id)`** and **`workflows.generate_counter_workflow(...)`**: the
  simulated-caller workflow generated from a workflow, and the state of its generation run. Generation
  returns at once and runs on the server, making several LLM calls; poll `counter_workflow` for progress.
- **`warnings` on `Tool`, `Node`, `Workflow` and `WorkflowVersion`**: the advisory lints the server
  returns with a write, which the SDK used to discard while unwrapping the response. A tool imported with
  a variable your team has not defined now says so, for example.

### Changed
- **`OktaAuthConfig` → `IntegrationAuthConfig`, following a server-side rename** made
  provider-agnostic (any integration exposing an OAuth2 client-credentials endpoint, not only Okta).
  Both of upstream's back-compat affordances are mirrored exactly:
  - `OktaAuthConfig` remains importable as an alias of the same class, so existing imports keep working.
  - `CustomLLMConfig.okta_auth` became `integration_auth` **with**
    `validation_alias=AliasChoices("integration_auth", "okta_auth")`, so the old keyword is still
    accepted on construction and previously saved configs keep deserializing.

  **One thing does change for readers, and it changes on the server too:** the attribute is now
  `integration_auth`, so code doing `llm.okta_auth` raises `AttributeError`. Constructing with
  `okta_auth=` is unaffected. Migration is a rename at the read site.
- **`ALWAYS_THINKING_GOOGLE_MODELS`** gains `gemini-3.8-flash`, `gemini-3.7-flash` and
  `gemini-3.1-pro-preview`. The last was already in upstream's set before this sync and had been missing
  from the mirror's copy, unnoticed until the parity harness began comparing the sets' contents.
- **`BaseLLMConfig.api_key`'s description** now states the server's role rule: an admin is shown the
  stored key, and an admin who sends a config with the key cleared removes it.
- **Companion threads now stop when the conversation does, by default.** `stop_with_main_thread`
  defaults to `True`, following the server (upstream 2026-10-01): a fork companion ends as soon as every
  main thread has ended, instead of running out its self-loop budget. A companion that must outlive the
  conversation — a write-back, or a result that arrives after the goodbye — needs
  `stop_with_main_thread=False`. The behaviour is the server's; a server that predates the change
  ignores the field.
- **`SelfLoopConfig.max_retries` has no upper bound.** The old `le=100` cap was lifted upstream.
- **Defaults are published in the JSON Schema.** `variable_arguments`, `result_variable_mappings`,
  `api_headers`, `target_knowledge_base_ids` and `static_messages` declare `default=[]` / `{}` rather
  than a factory, and `WorkflowConfig.llms_config` and the events' `llm_usage_info` declare instances, all
  as upstream does. Runtime behaviour is unchanged, since Pydantic copies a mutable default per instance.
  A tool's `logical_id` stays a factory on purpose, so no shared id is published.
- **`llm_configs.update(..., config=...)` now keeps the stored API key by default.** With an admin or
  super-admin token, the server deletes a saved config's key when an update's `config` has none, because
  an admin is shown the key and could only have cleared it on purpose. A config built fresh in code has
  none, so updates silently deleted provider keys. With `preserve_api_key=True` (the default), when
  `config` leaves `api_key` unset, `update` reads the stored config first and carries its key across,
  including group members' keys (paired by `logical_id`), at the cost of one extra GET. A key is never
  carried onto a config of a different provider type. `preserve_api_key=False` sends `config` exactly as
  given, which is how an admin deliberately removes a key.
- **`runs.list()` accepts at most a 31-day `start`–`end` window**, server-side; a wider one is a
  `BadRequestError` carrying the server's message. Results are now ordered by creation time. (The server
  applies the same window to the simulations list, but `simulations.list()` takes no dates, so it cannot
  be hit from the SDK.)

### Docs
- **The guides follow the October server**: the Vertex-served providers and the Anthropic and Google
  backends, Gemini thinking levels, `preserve_api_key` and role-dependent key visibility (LLM configs);
  how long a companion runs and `stop_with_main_thread` (companion threads); the lifted `max_retries` cap
  (self-loops); `clone`, `result_as_media`, codebase functions, import `warnings` and inline-Python test
  execution (nodes, edges and tools); lints, realtime compatibility and voice persona (workflows);
  counter-workflow generation (simulations); the 31-day run window (monitoring runs); refusals and
  hidden resources (error handling).
- **Six documented claims that were false when run**, now corrected:
  - `llm_configs.test()` / `test_inline()` examples used message role `"user"`, which the server rejects
    with a 422. The roles are `human`, `ai` and `system`.
  - "Reference a saved config in a node" used `llms_config={"named_llm_config_id": ...}`, which fails
    validation and never referenced anything. The field is `attachable_llm_config_id`, and there is no
    lookup by name.
  - The configs guide named the union discriminators `edge_type` / `tool_type`, and its example failed.
    The field is `type`.
  - `workflows.dynamic_variables()` was documented as returning `{var_name: spec}`. It returns
    `{"dynamic_variables": ..., "global_variables_resolved": ...}`.
  - "Secrets are redacted — always": admins and super-admins are shown the stored key.
  - A draft line in this update itself said the server rejects a Gemini thinking level the model does not
    offer. A live call showed that it substitutes the nearest level instead.
- `gpt-4` examples in the LLM-configs guide now use `gpt-5.4-mini`; OpenAI shuts `gpt-4` down on 2026-10-23.

### Notebooks and examples
- **`10_llm_configs`**:
  - Adds the Vertex-served providers and backends, each exercised with one real `test_inline` call:
    Grok, Claude on Vertex, and Gemini 3.8 with a thinking level.
  - Notes `preserve_api_key`.
  - Corrects the saved-config reference. It used `named_llm_config_id`, which references nothing; its run
    only succeeded because a default `OpenAILLMConfig` works on team credentials. It now uses
    `attachable_llm_config_id`, and reads the workflow back to show the server resolving it before the
    run.
- **`04_tools_and_inbuilt`**:
  - Its execution cells passed while executing nothing: inline-Python test execution is off by default,
    so both calls returned `success=False`. Execution is now shown with an inbuilt function, which runs
    everywhere, and the inline-Python calls report plainly when an environment refuses them.
  - Adds `tools.clone`, variables travelling by name (`required_dynamic_variables` and the import
    `warnings`), and `result_as_media`.
- **`19_companion_threads`** and **example 24**: how long a companion runs, and why the lab poller leaves
  `stop_with_main_thread` at its default.

### Removed
- **`OPENAIModel.GPT_5_2_CHAT_LATEST`, `GPT_5_3_CHAT_LATEST`** and
  **`ANTHROPICModel.CLAUDE_OPUS_4_1_20250805`.** Removed server-side; each returns 404 on every call.
  A config naming one now fails validation in the SDK instead of at the provider.

### Testing
- **Behaviour parity, not just structural parity.** `make parity-check` ignores module-level functions
  and does not compare `validation_alias`, so some of this release's changes are invisible to it. They are
  covered instead by tests that assert the behaviour directly: the old auth keyword still parsing onto the
  new attribute, the class alias being the same object, and `secret_variables` staying out of
  `model_dump()` while remaining readable in-process.
- **The drift harnesses see more.** `config_parity` compares validators by name (a second same-mode
  validator used to be invisible), keeps `default=[]` and `default_factory=list` apart, compares the
  contents of hoisted capability sets, compares discriminated-union membership, and reports classes
  imported from files it does not parse. `schema_sync` compares every nested `$defs` model, reports
  server classes the mirror lacks, discovers tool types from the server, and compares published defaults.
  Each check has a fixture test proving it fires.
- **`schema_sync` can run ahead of a deploy.** `KNOWN_NOT_YET_DEPLOYED` lists fields the mirror carries
  from upstream source that the server under test does not serve yet (today:
  `CompanionThreadConfig.stop_with_main_thread`). The live guard fails once an entry stops suppressing
  anything, which signals that the deploy has landed.
- **Live round trips for the new fields** (`tests/integration/test_tools_workflow_e2e.py`): a saved tool
  with `result_as_media`, a workflow with `voice_persona`, and a codebase-function tool node, each written
  to the server and read back intact. Plus `realtime_overrides` on an LLM node.
- **The new HTTP surface is pinned at the wire and proven live.** `tests/unit/resources/test_http_surface.py`
  asserts what each new method sends and parses, using response shapes captured from dev, plus the
  403 / 404 / 409 / 400 mappings. `tests/integration/test_http_surface_e2e.py` runs clone, import
  warnings, the codebase-function catalogue, lints, realtime compatibility and the counter-workflow
  status against dev, and proves `preserve_api_key` both keeps a key and, opted out, removes it.
- **Recorded out of scope:** the `/secure-notifications` routes, the copilot WebSocket and its proposal
  routes (staff-only), `copilot_runs_only` on the run list (super-admin only), and internal routes
  (`/chat/completions`, `/scheduler/...`, `/update_log_level`, `/medical-copilot`).
- **Parity is zero, and the guard asserts it again.** `KNOWN_UPSTREAM_DEBT` is 0: the mirror has no
  structural difference from upstream source, and `make schema-check` reports no finding against dev.

### Fixed
- **`tools.update()` with a typed config overwrote fields it was not asked to change.** It sent the whole
  config, every unset field included as its default. The server merges a tool update onto the stored
  config, so an update setting only `description` or `code` wiped the tool's `name`, `signature` and
  `args_schema`, and replaced its `logical_id` with a freshly minted one, silently changing its identity.
  It now sends only the fields set on the config, as `nodes.update()` always has; a dict is still sent as
  given. Found by reading notebook 04's output, where a clone came back named `"tool (Clone)"`.
- **A workflow using a new provider or model lost its node types.** A node on Grok, Gemma, GLM,
  DeepSeek, or Gemini 3.7/3.8 hydrated as `UnknownNodeConfig`, with every typed field gone, and
  validating such an `LLMConfig` on its own raised. An `AnthropicLLMConfig` with `backend="vertex"`
  parsed but silently dropped the backend, so reading a config and writing it back moved it to the
  direct API.
- **A workflow with a codebase-function tool node lost that node's type**, hydrating it as
  `UnknownNodeConfig`. And `result_as_media` parsed but was dropped, so reading an external-API tool and
  writing it back turned a media result into a parsed one.
- **Per-node realtime settings were dropped**, so reading a workflow and writing it back erased every
  node's `realtime_overrides`. **A copilot event carrying a proposal failed validation**, because the
  payload union had no member for it.
- **Examples 11–23 crashed on launch.** `main()` passed a `dynamic_variables` that was never defined
  in its scope, so `python wf_examples/wf_example_progression_11.py` raised `NameError` on the first
  call it made. The notebook counterparts never caught it because they import the *builder* and drive
  the run themselves, never calling `main()`.

### Changed
- **Every curriculum builder now returns the config alone.** Examples 1–10 returned
  `(config, dynamic_variables)`, where the second element was either empty (1, 2, 8, 9) or a
  byte-identical copy of `miscellaneous["default_dynamic_variables"]` (3–7, 10) — so it carried
  nothing the config did not already hold. The integration test that had to accept both shapes now
  requires the single one.

### Testing
- **The parity allow-lists are themselves audited.** Each entry suppresses a real difference for a
  stated reason; nothing checked that the reason had not expired. `tests/unit/test_drift_guards.py`
  now asserts every entry still corresponds to a live divergence, and that each carries a reason.
  It immediately found a dead one: `BaseAPIModel` sat on `KNOWN_ONLY_MIRROR` while living in
  `src/interactly/` — outside the tree the harness parses — so it suppressed nothing on either side.

---

## [0.2.0] — 2026-08-08

First release since the SDK was brought back in sync with the workflow service.

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

#### Packaging & self-containment
- **`pyproject.toml` now reads the version from `_version.py`** in both packages
  (`[tool.hatch.version]`). Each file previously hardcoded the number *alongside* `_version.py`,
  which claimed to be the only source — two values free to disagree.
- **`tests/unit/test_self_contained.py`** enforces the constraint the whole vendoring arrangement
  rests on: no shipped module imports `common`, `agentic_workflow_framework`, `workflow_service`,
  `beanie`, `bson` or `pymongo`; nothing imports the drift harnesses; `interactly_configs` is never
  imported unguarded at module scope; and the wheels ship the package and nothing else.
- Verified in a fresh venv outside the monorepo: the base install imports and builds a client with
  **no** `interactly_configs` present, and the facades fail with installation instructions rather
  than a bare `ModuleNotFoundError`.

#### Testing
- **The drift harnesses are now tests, not just make targets.** `tests/unit/test_drift_guards.py`
  runs the source-parity and symbol-reference checks (skipping cleanly when the monorepo or the
  packages are absent); `tests/integration/test_schema_sync_guard.py` runs the live schema check.
  Each also asserts it *compared something* — a harness that silently finds no input reports zero
  differences too, which is how three of four quality gates were passing in Phase 0.
- **`tests/integration/test_background_execution_e2e.py`** — end-to-end coverage against a live
  server for companion threads, evaluate-while-waiting, bounded self-loops, no-op nodes, re-runs
  (including `amend_token`), run feedback, and the hydrated-config round trip. Includes the four
  graph-validation rejections, asserted rather than described, so a server-side relaxation surfaces
  as a test failure instead of a workflow that silently never advances.
- **`tests/integration/test_examples_upload.py`** — every one of the 25 curriculum examples still
  builds a config the server accepts.
- **`tests/unit/test_run_event_shapes.py`** and **`tests/unit/resources/test_phase6_wire_shapes.py`**
  — pin the `RunEvent` contract (top-level extras rather than `data`, internal companion ids, the
  three lifecycle events that diverge) and the tool export/import, `is_system` and run-feedback wire
  shapes.
- New make targets: `make test-integration` and `make test-configs`.

#### Notebooks & examples
- Four new notebooks: `18_reruns_and_replay`, `19_companion_threads`, `20_waiting_conditions`,
  `21_run_feedback`. All four execute end to end against a live server.
- Two new curriculum examples: `wf_example_progression_24` (companion thread polling in the
  background, with an evaluate-while-waiting edge that interrupts the conversation when the result
  lands) and `_25` (bounded retries branching on `[[self_loop_outcome]]`, with a no-op fan-in
  junction). Each with its illustrated `.md`.
- Existing notebooks updated for the new surface: `15` (background/self-loop events,
  `thread_reference_id`, close codes 4006/4007), `16` (the no-op node, `SelfLoopConfig`,
  edge-level configs and the four accessors), `07` (`is_system`), `04` (tool export/import).

#### Server-side issues found while writing the above
- **Companion threads did not run over the REST driver** — fixed upstream in
  `interactly-ai@6b09ada25`, verified live on dev 2026-08-08. `execute()` returned as soon as the main thread parked; the companion's
  first node emitted `start_node_run` and was then abandoned, so `has_background_work` stayed
  `False` and `pump_companions()` / `drive_background_work()` had nothing to advance. The REST turn
  loop was breaking out of the runtime generator on the busy-wait event, cancelling the drain loop
  mid-companion. **Pumping requires a server build that includes that commit**; `stream()` was never
  affected.
- **`Run.feedback_users` is empty on a fetched run**, even when the run carries ratings and
  comments. Read the map off the write response instead.
- `add_comment()` and `add_event_comment()` return a single `RunComment`, not the full
  `RunFeedbackResponse` the newer feedback endpoints return.

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
  <br>_Correction (Phase 6): this script is not in the repository and never was. Its upload check now lives in `tests/integration/test_examples_upload.py`, where it runs as part of the suite; driving turns is covered by the notebook counterparts in `notebooks/wf_example_notebooks/`._
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

