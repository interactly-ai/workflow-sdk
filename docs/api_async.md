# API reference (async)

> **Generated file — do not edit by hand.** Regenerate with `python wf_examples/internal/gen_api_reference.py`.

Every method below is on `AsyncWorkflowClient` — **the preferred way to use the SDK** (`await` each call). The synchronous surface is identical; see [api_sync.md](api_sync.md).

Construct the client from `INTERACTLY_*` environment variables:

```python
from interactly import AsyncWorkflowClient

async with AsyncWorkflowClient() as client:
    workflow = await client.workflows.get("wf-123")
```

See the [capability guides](README.md#capability-guides) for runnable examples.

## Workflows

`client.workflows`


| Method | Signature | Description |
|---|---|---|
| `clone` | `(workflow_id: 'str', *, name: 'Optional[str]' = None, description: 'Optional[str]' = None, clone_all_versions: 'bool' = True, version_numbers: 'Optional[List[int]]' = None, fallback_active_version: 'Optional[int]' = None) -> 'Workflow'` | Duplicate a workflow (deep copy of nodes, edges, and versions). |
| `create` | `(*, name: 'str', description: 'Optional[str]' = None, config: 'Optional[WorkflowConfigOrDict]' = None) -> 'Workflow'` |  |
| `create_from_config` | `(config: "'WorkflowConfigFullyHydrated'", *, name: 'Optional[str]' = None, description: 'Optional[str]' = None) -> 'Workflow'` | Async variant of :meth:`WorkflowsResource.create_from_config`. |
| `delete` | `(workflow_id: 'str') -> 'None'` |  |
| `dynamic_variables` | `(workflow_id: 'str') -> 'Dict[str, Any]'` |  |
| `export` | `(workflow_id: 'str', *, version_numbers: 'List[int]', active_version_number: 'int') -> 'Dict[str, Any]'` | Export a workflow as a portable bundle dict. |
| `favorite` | `(workflow_id: 'str') -> 'Dict[str, Any]'` | Mark a workflow as a favorite for the requesting user (idempotent). |
| `get` | `(workflow_id: 'str') -> 'Workflow'` |  |
| `get_fully_hydrated` | `(workflow_id: 'str') -> "'WorkflowConfigFullyHydrated'"` | Async variant of :meth:`WorkflowsResource.get_fully_hydrated`. |
| `global_node_config_schema` | `() -> 'Dict[str, Any]'` |  |
| `handle` | `(workflow_id: 'str', *, dynamic_variables: 'Optional[Dict[str, Any]]' = None) -> "'AsyncWorkflowHandle'"` | Async variant of :meth:`WorkflowsResource.handle`. |
| `import_bundle` | `(bundle: 'Dict[str, Any]', *, versions_to_import: 'Optional[List[int]]' = None, active_version_number: 'Optional[int]' = None, workflow_name: 'Optional[str]' = None) -> 'Workflow'` | Import a previously exported workflow bundle. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None) -> 'AsyncPage[Workflow]'` |  |
| `schema` | `() -> 'Dict[str, Any]'` |  |
| `unfavorite` | `(workflow_id: 'str') -> 'Dict[str, Any]'` | Remove a workflow from the requesting user's favorites. |
| `update` | `(workflow_id: 'str', *, name: 'NotGivenOr[str]' = NOT_GIVEN, description: 'NotGivenOr[Optional[str]]' = NOT_GIVEN) -> 'Workflow'` |  |
| `update_concurrency` | `(workflow_id: 'str', *, max_concurrent_runs: 'int') -> 'Dict[str, Any]'` | Set the maximum number of simultaneous runs for a workflow. |

### `client.workflows.versions`

| Method | Signature | Description |
|---|---|---|
| `activate` | `(workflow_id: 'str', version_number: 'int') -> 'Workflow'` | Mark a specific version as the active version. |
| `create` | `(workflow_id: 'str', *, version_name: 'Optional[str]' = None, mark_as_active: 'bool' = False, source_version_number: 'Optional[int]' = None) -> 'WorkflowVersion'` |  |
| `delete` | `(workflow_id: 'str', version_number: 'int') -> 'None'` |  |
| `diff` | `(workflow_id: 'str', version1: 'int', version2: 'int') -> 'VersionDiff'` | Compare two workflow versions and return a structured diff. |
| `list` | `(workflow_id: 'str') -> 'List[WorkflowVersion]'` | Return all versions for the given workflow. |
| `list_active` | `(*, page: 'int' = 1, size: 'int' = 20, favorites: 'Optional[bool]' = None, created_by_me: 'Optional[bool]' = None, category: 'Optional[str]' = None, categories: 'Optional[List[str]]' = None, logical_id: 'Optional[str]' = None) -> 'AsyncPage[WorkflowVersion]'` | List every workflow's active version across the team (paginated). |
| `update` | `(workflow_id: 'str', version_number: 'int', *, version_name: 'str') -> 'WorkflowVersion'` |  |
| `update_config` | `(workflow_id: 'str', version_number: 'int', *, config: 'WorkflowConfigOrDict') -> 'WorkflowVersion'` |  |

## Nodes

`client.nodes`


| Method | Signature | Description |
|---|---|---|
| `create` | `(*, node_config: 'NodeConfigOrDict') -> 'Node'` | Create a new standalone node. |
| `delete` | `(node_id: 'str') -> 'None'` | Delete a node. |
| `get` | `(node_id: 'str') -> 'Node'` | Retrieve a single node by ID. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, node_type: 'Optional[str]' = None, workflow_id: 'Optional[str]' = None) -> 'AsyncPage[Node]'` | List nodes. |
| `schema` | `(node_type: 'str') -> 'Dict[str, Any]'` | Retrieve the JSON Schema for a specific node type. |
| `types` | `() -> 'List[Dict[str, Any]]'` | Retrieve all available node types with their categories. |
| `update` | `(node_id: 'str', *, node_config: 'NotGivenOr[Optional[NodeConfigOrDict]]' = NOT_GIVEN) -> 'Node'` | Update a node's config. |

## Edges

`client.edges`


| Method | Signature | Description |
|---|---|---|
| `create` | `(*, edge_config: 'EdgeConfigOrDict') -> 'Edge'` | Create a new standalone edge. |
| `delete` | `(edge_id: 'str') -> 'None'` | Delete an edge. |
| `get` | `(edge_id: 'str') -> 'Edge'` | Retrieve a single edge by ID. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, edge_type: 'Optional[str]' = None, workflow_id: 'Optional[str]' = None) -> 'AsyncPage[Edge]'` | List edges. |
| `schema` | `(edge_type: 'str') -> 'Dict[str, Any]'` | Retrieve the JSON Schema for a specific edge type. |
| `types` | `() -> 'List[str]'` | Retrieve all available edge type identifiers. |
| `update` | `(edge_id: 'str', *, edge_config: 'NotGivenOr[Optional[EdgeConfigOrDict]]' = NOT_GIVEN) -> 'Edge'` | Update an edge's config. |

## Tools

`client.tools`


| Method | Signature | Description |
|---|---|---|
| `configurable_inbuilt` | `() -> 'List[Dict[str, Any]]'` | List configurable inbuilt tools from the catalogue. |
| `configurable_inbuilt_schema` | `(key: 'str') -> 'Dict[str, Any]'` | Retrieve the descriptor + config schema for a single configurable inbuilt tool. |
| `create` | `(*, tool_config: 'ToolConfigOrDict') -> 'Tool'` | Create a new custom tool. |
| `delete` | `(tool_id: 'str') -> 'None'` | Delete a tool. |
| `execute` | `(tool_id: 'str', *, args: 'Optional[Dict[str, Any]]' = None) -> 'ToolExecuteResult'` | Execute a saved tool with the given argument values and return its output. |
| `execute_inline` | `(*, tool_config: 'ToolConfigOrDict', args: 'Optional[Dict[str, Any]]' = None) -> 'ToolExecuteResult'` | Execute an inline (unsaved) tool config with the given argument values. |
| `export` | `(tool_id: 'str') -> 'Dict[str, Any]'` | Export a tool as a portable bundle. Secrets are redacted by the server. |
| `get` | `(tool_id: 'str') -> 'Tool'` | Retrieve a single tool by ID. |
| `import_bundle` | `(bundle: 'Dict[str, Any]', *, name_override: 'Optional[str]' = None, secret_overrides: 'Optional[Dict[str, Any]]' = None, clear_unresolved_refs: 'bool' = True, confirm_executable: 'bool' = False) -> 'Tool'` | Import a tool bundle produced by :meth:`export`. See the sync counterpart. |
| `inbuilt` | `() -> 'List[Dict[str, Any]]'` | Retrieve all inbuilt tools from the registry. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, tool_type: 'Optional[str]' = None, workflow_id: 'Optional[str]' = None) -> 'AsyncPage[Tool]'` | List tools. |
| `schema` | `(tool_type: 'str') -> 'Dict[str, Any]'` | Retrieve the JSON Schema for a specific tool type. |
| `types` | `() -> 'List[str]'` | Retrieve all available tool type identifiers. |
| `update` | `(tool_id: 'str', *, tool_config: 'NotGivenOr[Optional[ToolConfigOrDict]]' = NOT_GIVEN) -> 'Tool'` | Update a tool's config. |

## Runs

`client.runs`


| Method | Signature | Description |
|---|---|---|
| `add_comment` | `(run_id: 'str', *, content: 'str') -> 'RunComment'` |  |
| `add_event_comment` | `(run_id: 'str', event_logical_id: 'str', *, content: 'str') -> 'RunComment'` | Add a comment to a specific event within a run. |
| `add_turn_comment` | `(run_id: 'str', turn_index: 'int', content: 'str') -> 'RunFeedbackResponse'` | Comment on a turn as a whole. Content is trimmed and may not be blank. |
| `delete` | `(run_id: 'str') -> 'None'` |  |
| `delete_comment` | `(run_id: 'str', comment_logical_id: 'str') -> 'None'` |  |
| `delete_event_comment` | `(run_id: 'str', event_logical_id: 'str', comment_logical_id: 'str') -> 'None'` | Delete a comment from a specific event within a run. |
| `delete_event_rating` | `(run_id: 'str', event_logical_id: 'str') -> 'RunFeedbackResponse'` | Remove the caller's rating from an event. |
| `delete_turn_comment` | `(run_id: 'str', turn_index: 'int', comment_logical_id: 'str') -> 'RunFeedbackResponse'` | Delete one comment from a turn. |
| `delete_turn_rating` | `(run_id: 'str', turn_index: 'int') -> 'RunFeedbackResponse'` | Remove the caller's rating from a turn. |
| `drive_background_work` | `(workflow_id: 'str', run_id: 'str', *, interval_seconds: 'float' = 1.0, max_iterations: 'int' = 60) -> 'List[InteractiveRunResponse]'` | Poll :meth:`pump_companions` until no background work remains. See the sync counterpart. |
| `evaluation_result` | `(run_id: 'str') -> 'RunEvaluationResult'` |  |
| `execute` | `(workflow_id: 'str', *, run_id: 'Optional[str]' = None, command: "'WorkflowCommand \| str'" = 'start', run_by: 'Optional[str]' = None, version_number: 'Optional[int]' = None, dynamic_variables: 'Optional[Dict[str, Any]]' = None, runtime_variables: 'Optional[Dict[str, Any]]' = None, miscellaneous: 'Optional[Dict[str, Any]]' = None, run_input: "Optional['WorkflowRunInput']" = None) -> 'InteractiveRunResponse'` | Execute one turn of an interactive workflow session (async). |
| `execute_with_input` | `(workflow_id: 'str', *, run_input: "'WorkflowRunInput'", run_id: 'Optional[str]' = None) -> 'InteractiveRunResponse'` | Async variant of :meth:`RunsResource.execute_with_input`. |
| `get` | `(run_id: 'str') -> 'Run'` |  |
| `list` | `(*, workflow_id: 'Optional[str]' = None, status: 'Optional[str]' = None, start: 'Optional[datetime]' = None, end: 'Optional[datetime]' = None, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, source_workflow_run_id: 'Optional[str]' = None, source_turn_index: 'Optional[int]' = None) -> 'AsyncPage[Run]'` | List workflow runs with optional filtering (paginated). |
| `pump_companions` | `(workflow_id: 'str', run_id: 'str') -> 'InteractiveRunResponse'` | Advance due background work for a paused interactive run, without consuming a user turn. |
| `schema` | `() -> 'Dict[str, Any]'` | Return the JSON schemas for workflow run structures. |
| `set_event_rating` | `(run_id: 'str', event_logical_id: 'str', value: 'str') -> 'RunFeedbackResponse'` | Rate one event of a run. At most one rating per user per target. |
| `set_turn_rating` | `(run_id: 'str', turn_index: 'int', value: 'str') -> 'RunFeedbackResponse'` | Rate a whole turn, as opposed to one of its events. |
| `stream` | `(*, workflow_id: 'str', command: 'WorkflowCommand' = <WorkflowCommand.START: 'start'>, run_by: 'str' = 'api', version_number: 'Optional[int]' = None, dynamic_variables: 'Optional[Dict[str, Any]]' = None, runtime_variables: 'Optional[Dict[str, Any]]' = None, run_input: "Optional['WorkflowRunInput']" = None, rerun_token: 'Optional[str]' = None, cast_to: 'Type[RunEvent]' = <class 'interactly.types.runs.run_event.RunEvent'>) -> 'AsyncStream[RunEvent]'` | Open an async WebSocket connection and stream workflow run events. |

## Re-runs

`client.reruns`


| Method | Signature | Description |
|---|---|---|
| `amend_token` | `(workflow_run_id: 'str', turn_index: 'int', rerun_token: 'str', *, dynamic_variables: 'NotGivenOr[Optional[Dict[str, Any]]]' = NOT_GIVEN, runtime_variables: 'NotGivenOr[Optional[Dict[str, Dict[str, Any]]]]' = NOT_GIVEN, message_edits: 'NotGivenOr[Optional[Any]]' = NOT_GIVEN, message_appends: 'NotGivenOr[Optional[Any]]' = NOT_GIVEN, message_deletes: 'NotGivenOr[Optional[Any]]' = NOT_GIVEN) -> 'RerunTokenPreviewResponse'` | Edit a projection before it runs, returning the updated preview. |
| `create_token` | `(workflow_run_id: 'str', turn_index: 'int', *, target_workflow_id: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, target_version_number: 'NotGivenOr[Optional[int]]' = NOT_GIVEN, history_mode: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, entry_node_logical_id: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, node_id_map: 'NotGivenOr[Optional[Dict[str, str]]]' = NOT_GIVEN, requested_mode: 'NotGivenOr[Optional[str]]' = NOT_GIVEN) -> 'RerunTokenResponse'` | Mint a re-run token carrying the projected state. |
| `execute` | `(workflow_run_id: 'str', turn_index: 'int', *, message: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, run_async: 'bool' = True, target_workflow_id: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, target_version_number: 'NotGivenOr[Optional[int]]' = NOT_GIVEN, history_mode: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, entry_node_logical_id: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, node_id_map: 'NotGivenOr[Optional[Dict[str, str]]]' = NOT_GIVEN, requested_mode: 'NotGivenOr[Optional[str]]' = NOT_GIVEN) -> 'RerunStartedResponse'` | Re-run a turn server-side and hand back the new run. |
| `preflight` | `(workflow_run_id: 'str', turn_index: 'int', *, target_workflow_id: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, target_version_number: 'NotGivenOr[Optional[int]]' = NOT_GIVEN, history_mode: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, entry_node_logical_id: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, node_id_map: 'NotGivenOr[Optional[Dict[str, str]]]' = NOT_GIVEN, requested_mode: 'NotGivenOr[Optional[str]]' = NOT_GIVEN) -> 'RerunPreflightResponse'` | Report what a re-run would carry over and drop. No side effects. |
| `preview_token` | `(workflow_run_id: 'str', turn_index: 'int', rerun_token: 'str') -> 'RerunTokenPreviewResponse'` | Show what a token restores, without starting it. |
| `rerunnable_turns` | `(workflow_run_id: 'str') -> 'RerunnableTurnsResponse'` | List which turns of a run can be re-run, and how often each already has been. |

## Schedules

`client.schedules`


| Method | Signature | Description |
|---|---|---|
| `cancel` | `(schedule_id: 'str') -> 'None'` | Cancel a pending scheduled run. |
| `create` | `(workflow_id: 'str', *, scheduled_time: 'datetime', run_input: 'Optional[RunInputOrDict]' = None, version: 'Optional[int]' = None, scheduled_by_name: 'Optional[str]' = None) -> 'Schedule'` | Schedule a workflow to run at a future UTC time. |
| `get` | `(schedule_id: 'str') -> 'Schedule'` | Retrieve a single scheduled run by ID. |
| `list` | `(workflow_id: 'str', *, status: 'Optional[ScheduleStatus]' = None, skip: 'int' = 0, limit: 'int' = 50) -> 'List[Schedule]'` | List scheduled runs for a specific workflow. |
| `list_all` | `(*, status: 'Optional[ScheduleStatus]' = None, skip: 'int' = 0, limit: 'int' = 50) -> 'List[Schedule]'` | List all scheduled runs across the entire team. |
| `update` | `(schedule_id: 'str', *, scheduled_time: 'NotGivenOr[Optional[datetime]]' = NOT_GIVEN, run_input: 'NotGivenOr[Optional[RunInputOrDict]]' = NOT_GIVEN, version: 'NotGivenOr[Optional[int]]' = NOT_GIVEN) -> 'Schedule'` | Modify a pending scheduled run. |

## Webhooks

`client.webhooks`


| Method | Signature | Description |
|---|---|---|
| `create` | `(*, name: 'str', url: 'str', actions: 'List[WebhookAction]', enabled: 'bool' = True, bearer_token: 'Optional[str]' = None, timeout_seconds: 'int' = 10, max_retries: 'int' = 3, retry_backoff_seconds: 'int' = 10) -> 'WebhookSubscription'` | Create a new outbound webhook subscription. |
| `delete` | `(webhook_id: 'str') -> 'None'` | Delete a webhook subscription. |
| `get` | `(webhook_id: 'str') -> 'WebhookSubscription'` | Retrieve a single webhook subscription by ID. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, enabled: 'Optional[bool]' = None, action: 'Optional[WebhookAction]' = None) -> 'AsyncPage[WebhookSubscription]'` | List webhook subscriptions for the team. |
| `list_delivery_attempts` | `(event_id: 'str', *, page: 'int' = 1, size: 'int' = 20) -> 'AsyncPage[WebhookDeliveryAttempt]'` | List delivery attempts for a single webhook event. |
| `list_events` | `(*, page: 'int' = 1, size: 'int' = 20, subscription_id: 'Optional[str]' = None, workflow_id: 'Optional[str]' = None, action: 'Optional[WebhookAction]' = None, status: 'Optional[WebhookEventStatus]' = None) -> 'AsyncPage[WebhookEvent]'` | List webhook delivery events for the team. |
| `retry_event` | `(event_id: 'str') -> 'Dict[str, str]'` | Retry delivery of a failed or pending webhook event. |
| `update` | `(webhook_id: 'str', *, name: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, url: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, actions: 'NotGivenOr[Optional[List[WebhookAction]]]' = NOT_GIVEN, enabled: 'NotGivenOr[Optional[bool]]' = NOT_GIVEN, bearer_token: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, clear_bearer_token: 'NotGivenOr[bool]' = NOT_GIVEN, timeout_seconds: 'NotGivenOr[Optional[int]]' = NOT_GIVEN, max_retries: 'NotGivenOr[Optional[int]]' = NOT_GIVEN, retry_backoff_seconds: 'NotGivenOr[Optional[int]]' = NOT_GIVEN) -> 'WebhookSubscription'` | Partially update a webhook subscription. |

## Simulations

`client.simulations`


| Method | Signature | Description |
|---|---|---|
| `create` | `(*, config: 'Dict[str, Any]') -> 'Simulation'` | Create a new simulation configuration (dict or typed Pydantic model). |
| `delete` | `(simulation_id: 'str') -> 'Dict[str, Any]'` | Delete a simulation configuration. |
| `evaluation_summary` | `(simulation_id: 'str', *, group_id: 'Optional[str]' = None) -> 'Dict[str, Any]'` | Get aggregated evaluation results for a simulation. |
| `get` | `(simulation_id: 'str') -> 'Simulation'` | Retrieve a simulation configuration by ID. |
| `get_run` | `(run_id: 'str') -> 'SimulationGroup'` | Get details of a specific simulation run group. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None) -> 'AsyncPage[Simulation]'` | List simulation configurations for the team. |
| `list_detailed_executions` | `(run_id: 'str', *, page: 'int' = 1, size: 'int' = 20) -> 'List[Dict[str, Any]]'` | List individual executions with hydrated workflow run details. |
| `list_executions` | `(run_id: 'str', *, page: 'int' = 1, size: 'int' = 20) -> 'AsyncPage[SimulationRun]'` | List individual executions within a simulation run group. |
| `list_runs` | `(simulation_id: 'str', *, page: 'int' = 1, size: 'int' = 20) -> 'AsyncPage[SimulationGroup]'` | List all run groups for a simulation configuration. |
| `run` | `(simulation_id: 'str', *, runner_name: 'Optional[str]' = None) -> 'SimulationGroup'` | Trigger a new simulation batch run. |
| `schema` | `() -> 'Dict[str, Any]'` | Retrieve the JSON Schema for a simulation configuration. |
| `stop_run` | `(run_id: 'str') -> 'SimulationGroup'` | Cancel a simulation run group. |
| `update` | `(simulation_id: 'str', *, updates: 'Dict[str, Any]') -> 'Simulation'` | Partially update a simulation configuration (dict or typed Pydantic model). |

## Global variables

`client.global_variables`


| Method | Signature | Description |
|---|---|---|
| `bulk_create` | `(*, variables: 'List[Dict[str, Any]]') -> 'List[GlobalVariable]'` | Create multiple global variables in one request. |
| `create` | `(*, name: 'str', value: 'Optional[str]' = None, description: 'Optional[str]' = None, category: 'Optional[str]' = None, is_secret: 'bool' = False) -> 'GlobalVariable'` | Create a single global variable. |
| `delete` | `(variable_id: 'str') -> 'None'` | Delete a global variable. |
| `get` | `(variable_id: 'str') -> 'GlobalVariable'` | Retrieve a single global variable by ID. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, category: 'Optional[str]' = None) -> 'AsyncPage[GlobalVariable]'` | List global variables. |
| `resolve` | `() -> 'Dict[str, Any]'` | Resolve all global variables for the team into a ``{name: value}`` dict. |
| `update` | `(variable_id: 'str', *, name: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, value: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, description: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, category: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, is_secret: 'NotGivenOr[Optional[bool]]' = NOT_GIVEN) -> 'GlobalVariable'` | Update a global variable. |

## Super nodes

`client.super_nodes`


| Method | Signature | Description |
|---|---|---|
| `dependents` | `(workflow_id: 'str', *, page: 'int' = 1, size: 'int' = 20) -> 'AsyncPage[SuperNodeDependent]'` | List workflows that embed this workflow as a super node (paginated). |
| `expand_preview` | `(workflow_id: 'str', *, version_number: 'Optional[int]' = None) -> 'SuperNodeExpandPreview'` | Preview a workflow with all super nodes inlined as flat nodes/edges. |
| `get` | `(workflow_id: 'str', *, version_number: 'Optional[int]' = None) -> 'SuperNodeDetail'` | Retrieve the full super node definition for a workflow version. |
| `list` | `() -> 'List[SuperNodeSummary]'` | List all super nodes published for the team. |
| `publish` | `(workflow_id: 'str', *, interface: 'SuperNodeInterfaceOrDict') -> 'Dict[str, Any]'` | Publish a workflow as a super node (typed ``SuperNodeInterface`` preferred; dict accepted). |
| `schema` | `(workflow_id: 'str', *, version_number: 'Optional[int]' = None) -> 'Dict[str, Any]'` | Retrieve the JSON Schema for a super node's input fields. |
| `snapshot_status` | `(workflow_id: 'str') -> 'Dict[str, Any]'` | Report whether the workflow's super-node snapshot is current. |
| `unpublish` | `(workflow_id: 'str', *, version_number: 'Optional[int]' = None) -> 'Dict[str, Any]'` | Unpublish a workflow version as a super node. |

## Node libraries

`client.node_libraries`


| Method | Signature | Description |
|---|---|---|
| `create` | `(*, node_library_config: 'NodeConfigOrDict') -> 'NodeLibrary'` | Create a new node library. |
| `delete` | `(library_id: 'str') -> 'None'` | Delete a node library. |
| `get` | `(library_id: 'str') -> 'NodeLibrary'` | Retrieve a single node library by ID. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, access_level: 'Optional[str]' = None) -> 'AsyncPage[NodeLibrary]'` | List node libraries. |
| `schema` | `() -> 'Dict[str, Any]'` | Retrieve the JSON Schema for node library configs. |
| `update` | `(library_id: 'str', *, node_library_config: 'NotGivenOr[Optional[NodeConfigOrDict]]' = NOT_GIVEN) -> 'NodeLibrary'` | Update a node library's config. |

## Templates

`client.templates`


| Method | Signature | Description |
|---|---|---|
| `create` | `(*, config: 'WorkflowTemplateConfigOrDict') -> 'Template'` | Create a new workflow template (typed config preferred; dict accepted). |
| `delete` | `(template_id: 'str') -> 'None'` | Delete a workflow template. |
| `get` | `(template_id: 'str') -> 'Template'` | Retrieve a single workflow template by ID. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None, access_level: 'Optional[str]' = None) -> 'AsyncPage[Template]'` | List workflow templates. |
| `schema` | `() -> 'Dict[str, Any]'` | Retrieve the JSON Schema for workflow template configs. |
| `update` | `(template_id: 'str', *, config: 'NotGivenOr[Optional[WorkflowTemplateConfigOrDict]]' = NOT_GIVEN) -> 'Template'` | Update a workflow template's config (typed config preferred; dict accepted). |

## Categories

`client.categories`


| Method | Signature | Description |
|---|---|---|
| `list` | `() -> 'List[str]'` | Retrieve all available workflow category names for the team. |

## LLM configs

`client.llm_configs`


| Method | Signature | Description |
|---|---|---|
| `create` | `(*, name: 'str', config: 'LLMConfigOrDict', description: 'Optional[str]' = None, is_default: 'bool' = False, override_default: 'bool' = False) -> 'LLMConfig'` | Create a saved LLM config (single provider or group). |
| `delete` | `(llm_config_id: 'str') -> 'None'` | Delete a saved LLM config. |
| `get` | `(llm_config_id: 'str') -> 'LLMConfig'` | Retrieve a single saved LLM config by ID. |
| `get_default` | `() -> 'LLMConfig'` | Return the team's default saved LLM config. |
| `list` | `(*, page: 'int' = 1, size: 'int' = 20, search: 'Optional[str]' = None) -> 'AsyncPage[LLMConfig]'` | List the team's saved LLM configs (paginated). |
| `schema` | `() -> 'Dict[str, Any]'` | Return the JSON schema for a saved LLM config (``LLMOrGroupConfig``). |
| `test` | `(llm_config_id: 'str', *, system_prompt: 'str', messages: 'Optional[List[Dict[str, Any]]]' = None, config: 'NotGivenOr[Optional[LLMConfigOrDict]]' = NOT_GIVEN) -> 'LLMConfigTestResult'` | Exercise a saved LLM config against a system prompt + optional messages. |
| `test_inline` | `(*, system_prompt: 'str', config: 'LLMConfigOrDict', messages: 'Optional[List[Dict[str, Any]]]' = None) -> 'LLMConfigTestResult'` | Exercise an unsaved (inline) LLM config before persisting it. |
| `update` | `(llm_config_id: 'str', *, name: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, description: 'NotGivenOr[Optional[str]]' = NOT_GIVEN, config: 'NotGivenOr[Optional[LLMConfigOrDict]]' = NOT_GIVEN, is_default: 'NotGivenOr[Optional[bool]]' = NOT_GIVEN, override_default: 'bool' = False) -> 'LLMConfig'` | Update a saved LLM config; only supplied fields are sent. |
