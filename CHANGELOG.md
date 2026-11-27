# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### LLM configs: a credential header a header map leaves out is kept
#### Changed
- **`llm_configs.update(..., preserve_credentials=True)` carries a stored credential header that the new
  `default_headers` leaves out**, as it already carried one the map sends blank or a config with no map at all.
  - **Before:** a map built in code with only the header it meant to change deleted the gateway's `Authorization`.
    That held for every role, since the server deletes a credential header an update leaves out.
  - **Now:** an admin's update carries the stored value. One below admin sends the header by name, blank, which the
    server keeps.
  - **Unchanged:** names match ignoring case, a header you fill in keeps your value, and a plain header the new map
    leaves out is still dropped.
- **To drop one credential header and keep the others, pass `preserve_credentials=False`** and send the credentials
  you keep.

### A node failure the server tolerates ends only its turn
#### Changed
- **`RunEvent.is_terminal()` is False for a `workflow_error` the server tolerated.**
  - **What the server sends:** under a workflow's default error limits, the run socket sends a failed node's
    `workflow_error` with `fatal: false` and keeps the socket open, and the run takes the next message.
  - **Before:** `is_terminal()` called every `workflow_error` the end of the run, so a loop that stopped on it left a
    run that was still going (and leaving the stream then cancelled it).
  - **Now:** it is True for `end_workflow`, and for a `workflow_error` with `fatal: true` or with no flag. That covers
    the last error the server sends, with the whole reason, before closing a run with 1011, and every error from a
    server that sends no flag.
- **A stream marks a tolerated failure `is_ready_for_input()`, once per turn,** so a conversation loop sends the next
  message instead of waiting for a hand-over that never comes. The server sends that error before it checks the
  workflow's error limits (`num_errors_tolerated`, `num_consecutive_errors_tolerated`, `stop_workflow_on_error`).
  When they end the run after all, the stream raises `StreamServerError` (1011) after the last error, as before.
- **A loop that reads only until `is_terminal()` now waits after a tolerated failure**, as it already waits after any
  turn that hands over to the user. Answer `is_ready_for_input()` with `send()` or `stop()`.

#### Added
- **`RunEvent.fatal`**: the flag the server puts on a `workflow_error`; `None` when a frame carries none.

---

## [0.4.0] — 2026-11-27

Brings the SDK in line with the workflow service as of `interactly-ai@ac21297a1` (2026-11-27): the config mirror,
the HTTP routes and their query fields, the run socket's frames and close codes, and the server's enums. Against that
source, `make parity-check`, `make route-check` and `make wire-check` each read 0. `make schema-check` reads 0 findings
against EKS dev, with simulations compared. On dev, the integration suite passes, durable runs and the developer and
viewer roles included: 99 of its 100 tests, the other being a Grok-on-Vertex reply the dev project has no access to.
All 48 notebooks pass there too. Install both packages at 0.4.0: `pip install "interactly[configs]>=0.4.0"`.

### Upgrading from 0.3.0

The changes that can alter what existing code does:

- **`llm_configs.update(..., preserve_api_key=)` is now `preserve_credentials=`**, with no alias. It keeps every
  stored credential a config built in code leaves blank: `api_key`, Bedrock's AWS key pair, and a custom gateway's
  credential headers. Pass `preserve_credentials=False` to remove them on purpose.
- **Leaving a stream before its run ends cancels the run**, on a current server, unless a durable run is waiting on a
  pause of its own. Keep iterating until the run ends, or end it with `stream.stop()`.
- **`stream.stop()` and `command="stop"` store the run `cancelled`** (`termination_source` `client_stop`), not
  `completed`.
- **`event.is_ready_for_input()` fires once per turn that hands over to the user, in every workflow.** Before, it fired
  only while fork companions ran. A loop that waited on it no longer hangs; one that broke on another event may now see
  this one first.
- **`list_all()`, `iter_pages()` and `next_page()` page past the first page** on every list. Code that read one page
  through them now reads them all.
- **`runs.execute(version_number=N)` runs version N.** It ran the active version before, whatever was asked.
- **`workflows.versions.update_config()` changes the settings it is given.** It changed nothing before, so a call that
  was a no-op now takes effect. A config holding nodes or edges raises `ValueError`.
- **`workflows.versions.create()` requires `version_name`.**
- **Removed filters the server never read:** `tools.list(workflow_id=)`, and `category` and `created_by_me` on
  `workflows.versions.list_active()`. Use `categories=[...]` and `created_by=[...]`.
- **Removed:** `RunStatus.PENDING`, `WorkflowConfig.voice_persona` (with `generated_voice_persona`,
  `resolved_voice_persona()` and `VOICE_PERSONA_MAX_LENGTH`) and `WorkflowStatus.is_active_run_status()`.
- **A config of a type this package does not know** reads as `UnknownLLMConfig` or `UnknownToolConfig`, where it
  failed the node before; a saved LLM config of an unknown provider reads as `UnknownLLMConfig`, not a `dict`.
- **Stream errors are typed by close code.** Each is a `StreamError` subclass, so `except StreamError` still catches
  them. A viewer's socket raises `StreamPermissionError`, where it raised `websockets`' `ConnectionClosedError`.
- **An error's message reads differently** for a 422 that carries the server's `message`: it reads as that message,
  not as FastAPI's error list. Code matching on `str(err)` may need updating; the full body is still `err.body`.
- **Fields that read `None` before now hold values:** `Simulation.status` and `WorkflowVersion.config`.
- **The `configs` extra requires `interactly-configs>=0.4.0`.** `interactly.configs` re-exports names that only
  exist from 0.4.0, so with an older configs package `import interactly.configs` fails.

### Drift harnesses
#### Added
- **`make route-check`** (`tests/tools/route_coverage.py`): the routes and query parameters the SDK's resources send,
  against the workflow service's routers. It reports routes no method calls, query fields no method can send, calls
  to routes upstream does not declare, and query keys upstream does not read. Against `interactly-ai@a87b31348` it
  read 91 when it was added (11 routes, 77 query fields, and three filters the server ignores) and reads 0 now; the
  routes and fields left out on purpose are listed, with their reasons, under "Not covered, by choice" below. A live
  guard checks that every route the SDK calls is in the server's OpenAPI document.
- **`make wire-check`** (`tests/tools/wire_values.py`): the SDK's own copies of server enums (`RunStatus`,
  `ScheduleStatus`, `SimulationStatus`, `WebhookAction`, ...) and the run socket's close codes, against upstream. It
  read 15 when it was added and reads 0 now.
- Both are ratcheted in `tests/unit/test_drift_guards.py`, like parity: a new gap fails the unit tests until it is
  closed or allow-listed with a reason.
- **Class docstrings are compared** by `make parity-check`: reported apart from the total, with their own ratchet
  (78 differ today).
- `INTERACTLY_DEVELOPER_API_KEY` and `INTERACTLY_VIEWER_API_KEY` (`.env.example`): keys acting as a developer and
  as a viewer, for role-gated integration tests, which skip while they are unset.

#### Fixed
- **`make schema-check` compared `/v1/simulations/schema` for the first time.** It dropped any endpoint whose model
  is not a top-level export of `interactly_configs`, without a word, and `SimulationConfig` never was one. It now
  finds the class anywhere in the package, and reports an endpoint with no class as unmapped. Against dev it reads
  one finding: `SimulationStatus` lacks `paused`.

### LLM configs: every credential kept, export and import, and clearer errors
#### Added
- **`llm_configs.export(llm_config_ids=None)` and `llm_configs.import_bundle(bundle, secret_overrides=None)`.** An
  export replaces every secret with `"<REDACTED>"` and lists it in `bundle["redactions"]`, whatever the caller's
  role. An import is all or nothing: every redacted secret must come back in `secret_overrides`, keyed by its path.
  It returns an `LLMConfigImportResult` (`imported`, each with `renamed_from` and `ids_reminted`, and `warnings`).
- **`LLMConfigTestResult.used_user_api_key` and `error_category`** (`auth`, `permission`, `quota`, `rate_limit`,
  `model`, `timeout`, `unavailable` or `other`); `error` holds the provider's own message.
- **`RequestTooLargeError`** for a 413, such as a signal body over 64 KiB.

#### Changed
- **`llm_configs.update(..., preserve_api_key=)` is now `preserve_credentials=`**, with no alias, and it keeps
  every stored credential, not only `api_key`. With an admin token, the server reads a credential the outgoing
  config leaves blank as "delete it", so an update built in code deleted Bedrock's AWS key pair and a custom
  gateway's `Authorization` header. Now the stored config is read first and each blank credential carried over:
  `api_key`, `aws_access_key_id`, `aws_secret_access_key`, and the credential headers of `default_headers`, matched
  by name ignoring case. Only onto a config of the same provider type, and into group members and backchannel
  configs as before. A unit test pins the client's list of credentials to the server's declarations.

#### Fixed
- **A developer's or viewer's update kept no credential headers.** Below admin, every credential reads blank, so
  `preserve_credentials` found nothing to carry. An update whose config had no header map then went out without one,
  and the server, which keeps a stored credential header an update sends blank but deletes one it leaves out, deleted
  a custom gateway's `Authorization`. The stored credential headers are now sent by name, blank, and kept. `api_key`
  and the AWS keys were never at risk: the server restores those below admin whatever the update sends.
- **A 422's message is readable.** A refused node config's 422 carries FastAPI's error list and a `message` naming
  the fields; the exception now reads as the `message`, where it used to read as the list. A list alone reads as
  "where: why", and a refusal nested in a dict (an LLM-config import's) reads as its message. The full body stays
  on `.body`.

### Evaluation workflows and `workflow_type`
#### Added
- **`client.evaluation_workflows`**, sync and async: `templates()`, `node_presets()`, `create_from_template(
  template_id=, name=)` and `list()`. An evaluation workflow analyses a finished conversation (a summary, a success
  verdict, structured data) and stores what it finds; it never runs on a live call. Once created it is an ordinary
  workflow to `client.workflows`. New types: `EvaluationTemplate`, `AnalysisNodePreset`, `EvaluationWorkflow`,
  `EvaluationWorkflowVersion`.
- **`WorkflowType`** (`standard`, `evaluation`), and `workflow_type=` on `workflows.list()`,
  `workflows.versions.list_active()` and `nodes.types()`. The server lists standard workflows unless asked for
  evaluation ones, and offers the analysis nodes only for evaluation workflows.
- **`workflows.list()` filters:** `logical_id`, `categories`, `created_by` and `favorites`.
- **`workflows.versions.get(workflow_id, version_number)`**: one version's snapshot.
- **`workflows.get_fully_hydrated(..., version_number=)`** and **`workflows.realtime_compatibility(..., backend=)`**
  (the assistant's Gemini backend, `vertex` or `ai_studio`, so the check agrees with the call's own about tool names).

#### Changed
- **`workflows.get()` asks for the workflow with its active version** (`find_active_version=true`). The answer is the
  same; the server no longer logs the read as one relying on its old default.

### Lists page past their first page
#### Fixed
- **Every list stopped after its first page.** The list routes send the rows and the total, but not the page or page
  size they served, and twelve list methods handed that answer to the pager as it was. With no page size the pager
  could not count pages, so `has_next_page` was false, `next_page()` raised `NoMorePagesError`, and `list_all()` and
  `iter_pages()` returned the first page only, without a word. Affected: `nodes`, `edges`, `tools`, `workflows`,
  `workflows.versions.list_active`, `node_libraries`, `templates`, `llm_configs`, `global_variables`, `webhooks.list`,
  `runs` (sync and async). Each now tells the pager the page and size it asked for; a page, size or page count the
  server does send still takes precedence. A unit test fails any new list method that doesn't.

### Version guards and the list filters the server reads
#### Added
- **`version_number` on nodes and edges.** `nodes.list()` and `edges.list()` take `version_number` and
  `logical_id`; with only `workflow_id`, the server lists the active version's. `get()`, `update()` and `delete()`
  take `version_number` as a guard: the server refuses (`NotFoundError`) unless the item belongs to that version, so
  an id kept from another version can't reach this one.
- **Super nodes:** `publish(..., version_number=)` publishes a version other than the active one;
  `unpublish(..., dry_run=True)` changes nothing and lists the workflows referencing the super node;
  `snapshot_status(..., version_number=)`.
- **`workflows.dynamic_variables(..., version_number=)`.**
- **List filters:** `tools.list(logical_id=, name=, category=)`; `workflows.versions.list_active(search=,
  created_by=[...])`; `webhooks.list_events(search=)`.

#### Removed
- **Filters the server never read.** `tools.list(workflow_id=)`, and `category` and `created_by_me` on
  `workflows.versions.list_active()`: each was sent and ignored, so it returned everything. Use `categories=[...]`
  and `created_by=[...]` instead.

#### Fixed
- **`super_nodes.publish()` said it created a new version of the workflow.** It records the interface and a snapshot
  of an existing version, and leaves the workflow as it is.

### Workflow bundles with their secrets, usage reports, and version settings
#### Added
- **`workflows.export(..., include_secrets=False)`.** By default the server clears a workflow's secrets from the
  bundle (a secret field becomes `None`, a sensitive header or body entry `""`) and lists each in
  `bundle["redactions"]`; `include_secrets=True` keeps them, in plain text. A viewer asking for them gets
  `PermissionDeniedError`.
- **`workflows.import_bundle(..., secret_overrides=None)`**, named as `tools.import_bundle` names it: the values for
  the cleared secrets, keyed by their `redactions` path (`{r["path"]: value for r in bundle["redactions"]}`). The
  number after `versions.` in a path is the version's position in the bundle, not its version number. A secret not
  supplied stays empty and adds a line to the returned workflow's `warnings`; an unlisted path raises
  `UnprocessableEntityError`, with the paths in `err.body["field_errors"]`.
- **`workflows.usage()`, `tools.usage()` and `llm_configs.usage()`**, returning a `UsageReport`: the team's
  workflows that reference the item, with the versions that do. A delete doesn't consult it.
- **`pruned_global_tool_exclusions`** on `Workflow` and `WorkflowVersion`: the nodes whose exclusions of global tools
  a write dropped because it removed those tools. More generally, every key of a write's envelope now reaches the
  returned model, as a field or an extra.

#### Fixed
- **`workflows.versions.update_config()` changed nothing.** It sent the settings under a `config` key, which the
  server ignores. They now go at the top level, and only the ones given (a typed `WorkflowConfig` sends the fields
  set on it). Its docstring said it replaced a version's nodes and edges; it changes the workflow-level settings, and
  now raises `ValueError` on a config holding nodes or edges instead of sending one the server would ignore.
- **`WorkflowVersion.config` was always `None`.** A version record holds its settings as `workflow_config`; they are
  now read from there, as a `WorkflowConfig`.

#### Changed
- **`workflows.versions.create()` requires `version_name`.** The server refuses a version without one (422), so a
  call without it could never succeed.

### Simulation groups: pause, resume and the list filters
#### Added
- **`simulations.pause_run(run_id, reason=None)` and `simulations.resume_run(run_id)`**, on both clients. A paused
  group starts no simulation and none takes a turn until it is resumed; the workflow runs of each simulation in
  flight are paused too. Both return a `SimulationRunControlResult`: the group, and per run its `role` (`selected`
  or `counter`) and `outcome`. On a server whose simulation runs are not durable, a run answers `not_durable` and
  is held by its group alone. An ended group raises `ConflictError`; a role below Developer, `PermissionDeniedError`.
- **`SimulationStatus.PAUSED`**, the status of a paused group.
- **`simulations.list()` filters:** `logical_id`, `selected_workflow_id`, `counter_workflow_id`,
  `selected_version_number`, `counter_version_number`, `status`, and `start`/`end` (given together, at most 31 days
  apart).
- `SimulationRun.simulation_config_id` and `SimulationRun.result`, which the server sends.

#### Fixed
- **`Simulation.status` was always `None`.** The server keeps it inside `simulation_config`, not beside it; it is
  now read from there. It is the status of the configuration's latest group as the configuration records it: a
  stopped group leaves it `running`, and a paused one is not recorded there.
- **`simulations.stop_run()` said running simulations complete naturally.** They end `cancelled` before their next
  turn. Stopping a group that has already ended returns it unchanged.

### A whole conversation on one stream
#### Added
- **`stream.send()` and `stream.stop()`**, on `Stream` and `AsyncStream`, and **`stream.run_id`.** A stream used to
  send its start frame and only read, so every later turn needed REST execute. Now one `with` block holds a whole
  conversation: send each turn once an event is `is_ready_for_input()`, keep iterating, and end the run with
  `stop()` (stored `cancelled`, `termination_source` `client_stop`).
  - `send(message)` puts the text on the main thread as the user's message, as the workflow editor does; a typed
    `run_input` covers anything more. The variables the stream was opened with go with every turn, because edge
    conditions read them from each turn's input; a turn's own are merged over them for that turn.
  - The server reads the socket only between turns, so a turn sent while one runs is taken when it ends.
  - Sending after the run has ended raises `StreamError`; a refusal met while sending is raised by iteration, as
    its typed exception.
- **`client.runs.stream(..., workflow_run_id=...)` takes back a run** that a stream left while it waited on a pause
  (an approval, a wait, a signal, a job), which the server then carried on. It needs durable socket runs on the
  server; elsewhere it raises `TakeBackRefusedError`. A take-back names the run and nothing else, so `version_number`,
  `run_input`, `rerun_token` and a command other than `START` raise `ValueError`.

#### Fixed
- **`event.is_ready_for_input()` fires in every workflow, once per turn that hands over to the user.** The server
  sends `workflow_ready_for_input` only while fork companions run on, so in a workflow without them it never fired
  and a loop waiting on it hung. A stream now follows each turn as the server settles one, and marks the turn's
  `end_workflow_iteration` when a main thread was left waiting for a message. A take-back's acknowledgement is marked
  when the run waits for its user.

### Runs and the run socket
#### Added
- **A typed exception for every code the run socket closes with.** Each is a `StreamError` subclass carrying
  `code`, `reason` and, when the server sent a `workflow_error` frame just before closing, `server_message`: the
  whole reason, where a close reason is cut at 123 bytes.

  | Close code | Exception | Meaning |
  |---|---|---|
  | 1008 | `StreamPermissionError` | The caller's role may not run workflows |
  | 1011 | `StreamServerError` | The server failed while handling the run |
  | 4000 | `StreamRejectedError` | A malformed frame, a missing version, or a configuration that would not load |
  | 4001, 4002, 4005 | `UnrunnableWorkflowError` | The stored workflow cannot run |
  | 4003 | `ConcurrencyLimitError` | Too many runs at once |
  | 4009 | `RunChangedElsewhereError` | The run was paused, resumed or cancelled elsewhere |
  | 4010 | `TakeBackRefusedError` | The run could not be taken back |
  | 4030 | `TakeBackForbiddenError` | The caller's role may not take back a run |
  | 4040 | `StreamNotFoundError` | The workflow or run does not exist |
  | 4400 | `ResumeInputRejectedError` | The frame carried a resume input |

  `InvalidStreamInputError` (4006) and `RerunTokenError` (4007) are unchanged. A viewer's socket is accepted and
  closed at once, usually before the start frame goes out. Iteration now reports that close too, so it raises
  `StreamPermissionError` and no longer the `websockets` library's own `ConnectionClosedError`.
- **`RunEvent.is_run_paused()` and `is_run_resumed()`** for the `run_paused` and `run_resumed` frames. A durable
  streamed run sends them when a person pauses or resumes it.
- **`client.runs.list(needs_attention=..., logical_id=..., version_number=...)`.** `needs_attention=True` lists the
  runs waiting on a person: a person's pause, or a step waiting for approval.
- **New fields:**
  - `InteractiveRunResponse.pause_summary`, for a durable REST-executed run left paused or waiting;
  - on `Run`: `termination_source`, `workflow_name`, `workflow_deleted`, `is_background_run`, `schedule_id` and
    `can_continue_in_editor`.
- **`ScheduleStatus.IN_PROGRESS`.**

#### Changed
- **`Run` keeps every key the server sends.** Keys of the run record and of the single-run GET's envelope that `Run`
  has no field for are now kept as extras (`run.model_extra`), not dropped.

#### Fixed
- **`client.runs.execute(version_number=N)` runs version N.** The server reads the version to run only from
  `?version=` and overwrites the body's, so the SDK, which sent it in the body, ran the active version on every call.
  `execute` and `execute_with_input` now send it as `?version=`, taking it from `run_input.version_number` when
  given. Only a session's first turn reads it.
- **A schedule fetched while it runs parses.** `Schedule.status` is typed `ScheduleStatus`, which lacked
  `in_progress`, so `client.schedules` raised on such a schedule.

#### Removed
- **`RunStatus.PENDING`.** No server sends it.

### Configs — mirror synced to `interactly-ai@a87b31348` (2026-11-26)
`make parity-check` reads 0 differences again, and `make schema-check` reads 0 findings against dev with
simulations now compared.

#### Added
- **`SimulationStatus.PAUSED`**: a simulation group a person paused.
- **A config of a type this package does not know yet no longer fails the node holding it.**
  - **What changes:** an LLM config naming a newer provider arrives as `UnknownLLMConfig`, and a tool config of a
    newer type as `UnknownToolConfig`. Both keep every field the server sent and are written back with exactly those
    fields. The node keeps its own class: a `say_llm` node stays a `SayLLMNodeConfig`. Before, the whole node fell
    back to `UnknownNodeConfig` and lost every typed field.
  - **What still raises:** a config with no `type`, or a known type with an invalid field. Those are mistakes in
    the config, not newer types.
  - **Where it applies:** every place a single LLM config, an LLM-or-group config or a tool config is held. That
    includes `LLMGroupConfig.llms`, so one unknown provider in a group does not fail the group.
  - **What doesn't change:** the published JSON Schemas are unchanged.
- `UnknownLLMConfig`, `UnknownToolConfig` and `UnknownNodeConfig` are exported from `interactly_configs` and
  `interactly.configs`. So are `SimulationConfig`, `SimulationStatus`, `SimulationWorkflowDetails`,
  `SimulationCommand`, `SimulationInput` and `SimulationEvent`, which needed `interactly_configs.simulation` before.

#### Changed
- **A saved LLM config naming a provider newer than the configs package** reads as an `UnknownLLMConfig` in
  `LLMConfig.config`, not a plain `dict`. A config with no `type` still reads as a `dict`.
- The six ECS node docstrings and the `WorkflowCommand.PAUSE` note follow upstream's text. `PAUSE` is not read by
  anything; a run is paused through `client.runs.pause()`.

### Background runs and the approval example
#### Added
- **`client.workflows.start_background_run(workflow_id, version_number=None, dynamic_variables=None, run_by=None)`**
  starts a workflow now as a durable run, with no user and no socket, so its nodes can wait on a timer, a signal, an
  external job or a person. Returns a `BackgroundRunStarted` with the run's id.
- **`tests/integration/test_run_control_e2e.py`**: the approval flow and a pause, signal and cancel against a live
  server. Each test skips where the server doesn't enable the Pause Workflow node.

#### Changed
- **Example 19 is now an approval flow** ("Approvals: a run that pauses for a person"): a Pause Workflow node holds a
  background run until a manager approves it through `list_pauses` and `resume(pause_ids=...)`. It replaces the
  WorkflowCommand walkthrough, which described pausing a run with `WorkflowCommand.PAUSE`, which no server reads.
  Script, walkthrough and notebook are all rewritten; the example needs no LLM.
- **`tests/integration/test_examples_upload.py` skips an example whose node type the server has not enabled**, naming
  it, instead of failing.

### Run control
#### Added
- **`client.runs.pause()`, `resume()` and `cancel()`** for durable runs (scheduled runs, re-runs, background runs).
  `resume()` takes one of two scopes: lift a person's pause of the run, or approve steps waiting for a person with
  `pause_ids` or `all_waiting_for_person`, with a `note` and `data` for them. Each returns a `RunControlResult`.
- **`client.runs.send_signal(run_id, signal_key, body, idempotency_key=None)`**: any JSON body, and an
  `Idempotency-Key` on every post (one per call unless you pass yours), so a retry never delivers twice. Returns a
  `SignalResult`.
- **`client.runs.list_pauses()`, `list_signals()` and `list_external_jobs()`**, returning `RunPause`, `RunSignal` and
  `RunExternalJob` rows in the new cursor pages, `SyncCursorPage` / `AsyncCursorPage`.
- **Guide:** [Run control](docs/guides/run_control.md).

#### Changed
- **The base client's `post()` takes any JSON value as its body, and per-request `headers`.** A dict body is cleaned
  of unset values as before.
- **A run-control request answered 409 with `Retry-After` is retried** within `max_retries`: the run kept changing
  and nothing was recorded. Every other request keeps its rule, and the run-control 503 is raised at once.

### Runs and webhooks — pausing
#### Added
- **`RunStatus.WAITING`**: a durable run parked until a timer, a signal or an external job wakes it.
- **A run's pause state on `Run`**: `durable`, `pause_summary`, `pause_requested`, `paused_by`, `pause_reason`,
  `paused_since` and `paused_seconds_total`, all optional. The single-run GET fills all seven; a list row fills
  `pause_requested` and `pause_summary`; each is `None` when the answer does not carry it.
- **`WebhookAction.WORKFLOW_RUN_PAUSED` and `WORKFLOW_RUN_RESUMED`.**

#### Changed
- **Webhook actions parse forward-compatibly.** `WebhookSubscription.actions`, `WebhookEvent.action` and
  `WebhookDeliveryAttempt.action` hold a `WebhookAction` member when the value is known and the plain string
  otherwise. Before, a subscription or event naming an action newer than the SDK failed to parse.

#### Fixed
- **`client.runs.get(...).feedback_users` is filled.** The server sends it beside the run record, which the SDK
  unwrapped and dropped, so it always read `{}`.

### Configs — mirror synced to `interactly-ai@8810d0c05` (2026-11-20)
`make parity-check` reads 0 differences again; it read 257 against this upstream. Without this sync a workflow
holding a Pause Workflow, Wait, Wait for signal, Terminate, ECS, analysis or Decisions node parsed each such node as
`UnknownNodeConfig`, and none of them could be built in code.

#### Added
- **Pausing.** `interactly_configs.pauses`: `WakeKind` and the wake conditions (`ManualWake`, `TimerWake`,
  `SignalWake`, `ExternalJobWake`, `RunPauseWake`, as the `WakeCondition` union), `PauseEntry`, `ResumeReason`, the
  resume payloads (`ResumePayload`), `PauseRecord`, `PausableNodeConfig` and `MAX_WAITING_SECONDS` (30 days).
- **Control nodes:** `PauseWorkflowNodeConfig`, `WaitNodeConfig`, `WaitForSignalNodeConfig`,
  `TerminateWorkflowNodeConfig`, each with its run input and output.
- **ECS nodes** (`nodes.aws.ecs`): run, start, get status, stop, wait for and get logs of tasks, with
  `nodes.external_job`'s job types.
- **Analysis nodes** (`conversation_fetch`, `analysis_llm`, `store_analysis`) and the **Decisions** node.
- **`on_failure`** on every node (`NodeFailurePolicy`: `route`, `abort_workflow`). `abort_workflow` cannot be
  combined with an enabled self loop, as the server refuses it.
- **`WorkflowStatus.WAITING`**, and the matching `NodeType` and `NodeCategory` members.
- **Events:** `PauseEvent` carries `wake`, `pause_id`, `entry`, `deadline_at` and `display_refs`; `PauseThreadEvent`
  carries `pause_id` and `wake_kind`; `EndWorkflowEvent` carries `outcome`, `reason` and `cause`;
  `WorkflowErrorEvent` carries `fatal`; new `TerminateWorkflowEvent`.
- `SimulationConfig.simulated_node_outcomes` (one per node), `WorkflowConfig.workflow_type`,
  `CustomLLMConfig.decisions_api`, `StaticMessagesConfig.word_for_word`, LLM nodes' `ignore_global_tools` and
  `excluded_global_tools`, and further `NodeRealtimeOverrides` fields.
- `gpt-6-luna`, `gpt-6.1-sol` and `gpt-6.1-terra`, with their reasoning-effort rules in
  `resolve_reasoning_effort`; `UILoginRole.VIEWER`.
- `nodes.gating`: which server flag enables each gated node type and field, and the refusal error types. Whether a
  flag is on is the server's to say; a refused save arrives as its 400.

#### Changed
- Credential fields are declared with `SecretField` / `SensitiveMapField`, as upstream does. In the mirror they are
  plain `Field`s: the dashboard annotation they add upstream is dropped, as every dashboard annotation is.
- `tests/tools/config_parity.py` compares those two as field declarations, and lists the new hoisted
  capability sets (`MODELS_WITHOUT_MINIMAL_REASONING_EFFORT`, `MODELS_WITHOUT_NO_REASONING_EFFORT`,
  `NO_REASONING_EFFORTS`, `DECISIONS_OPENAI_MODELS`).

#### Removed
- **`WorkflowConfig.voice_persona`, `WorkflowConfigFullyHydrated.generated_voice_persona`,
  `resolved_voice_persona()` and `VOICE_PERSONA_MAX_LENGTH`.** The server removed them: a GPT-Live call takes the
  voice persona of the assistant placing it. A stored workflow that still carries the field loads and sheds it.
- `WorkflowStatus.is_active_run_status()`, removed upstream: which statuses are reaped and which hold a
  concurrency slot differ for `WAITING`, so the server keeps those rules itself.

### Not covered, by choice
The workflow service serves these, and the SDK leaves them out on purpose. `make route-check` holds each in an
allow-list with its reason, so it fails when one goes away or a new route appears without a decision.
- **Secure notifications** (`/v1/secure-notifications`, six routes): raised and approved by the platform's own flows,
  behind a per-team flag; not a client API.
- **The upgrade checklist** (`/v1/upgrade-checklist`, four routes): a deployment operator's tool, for super admins.
- **`runs.list(copilot_runs_only=)`**: lists the copilot's own conversations, which the server refuses to every role
  below super admin.
- **`search`, `start` and `end` on lists that never read them.** The shared pagination model declares them on every
  list route, but most lists ignore them; the SDK offers each only where the server filters by it, so a filter in a
  call always filters. The same holds for `logical_id` and `workflow_id` on the templates list.
- **`version_number` on `workflows.update()`**: the method sends only the name and description, which the server
  writes to every version either way.
- Routes the server hides from its schema (`include_in_schema=False`) and its `/internal/` service-to-service routes.

### Docs
- **The guides describe this release.**
  - [Streaming](docs/streaming.md): a whole conversation on one stream (`send()`, `stop()`), what leaving the stream
    does to a run, taking a run back, the `run_paused` / `run_resumed` frames, and every close code with its
    exception. A gotcha: `is_terminal()` is true for every `workflow_error`, but a node failure the server tolerates
    ends only the turn, and the run goes on; the run has ended when iteration stops.
  - [Companion threads](docs/guides/companion_threads.md): the conversation loop on one stream; companions end with
    the run when the stream is left.
  - [Error handling](docs/error_handling.md): the close-code exceptions, `RequestTooLargeError`, and how an error's
    message is built from its body.
  - [Running workflows](docs/guides/running_workflows.md): later turns on a stream, `data` turns over REST, durable
    REST runs (`pause_summary`, and the 409 the SDK does not retry), and `WorkflowCommand.PAUSE`, which pauses
    nothing.
  - [Run control](docs/guides/run_control.md): which runs are durable, by server flag; `needs_attention`; pausing a
    simulation group.
  - [Pagination](docs/pagination.md) and [Monitoring runs](docs/guides/monitoring_runs.md): every list pages past its
    first page, the newer filters, and the new `Run` fields.
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
- **New: `22_evaluation_workflows`.** Templates and analysis-node presets, the analysis node types offered only for
  `workflow_type="evaluation"`, creating one from a template and finding it in both lists, and naming it as a
  standard workflow's evaluator, seen through `usage()`. It runs nothing and calls no LLM.
- **Updated for this release:**
  - `03_workflow_versions`: `versions.get()` and `update_config()`; export with the secrets cleared and import
    with them supplied again (and without them, left empty with a warning); `workflows.usage()`.
  - `09_simulations`: pause, resume and stop a run group, with each run's role and outcome; the list filters, and
    why a stopped simulation still lists as `running`.
  - `10_llm_configs`: the credentials an update keeps, a failed test's `error_category`, export and import, and
    `usage()`. The new cells use a gateway at a host that can never resolve, so they call no provider.
  - `14_pagination_and_filtering`: page metadata, `needs_attention`, one version's runs and nodes,
    `workflow_type`, simulation date windows, and deduplicating rows that share a timestamp.
  - `15_websocket_streaming_events`: a two-turn conversation on one stream with `send()` and `stop()` (two short
    `gpt-5.4-nano` replies), the `run_paused` / `run_resumed` frames, and every close code with its exception.
  - `19_companion_threads`: `workflow_ready_for_input` is sent only while companions run.
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

