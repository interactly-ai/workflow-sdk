# Live schema drift report — `interactly_configs` vs the running server

- Server: `https://api-dev.interactly.ai/workflows/`
- Schemas compared: **33**
- **Findings: 50**

## enum-extra (9)

| Endpoint | Model | Detail |
|---|---|---|
| `(shared enum)` | `ANTHROPICModel` | mirror offers `claude-opus-4-20250514` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `ANTHROPICModel` | mirror offers `claude-sonnet-4-20250514` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | mirror offers `gemini-1.5-flash` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | mirror offers `gemini-1.5-flash-8b` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | mirror offers `gemini-1.5-pro` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | mirror offers `gemini-2.0-flash` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | mirror offers `gemini-2.0-flash-lite` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `OPENAIModel` | mirror offers `gpt-5-chat-latest` — **server would reject it** _(in 7 schemas)_ |
| `(shared enum)` | `OPENAIModel` | mirror offers `gpt-5.1-chat-latest` — **server would reject it** _(in 7 schemas)_ |

## enum-missing (12)

| Endpoint | Model | Detail |
|---|---|---|
| `(shared enum)` | `ANTHROPICModel` | server offers `claude-fable-5` _(in 7 schemas)_ |
| `(shared enum)` | `ANTHROPICModel` | server offers `claude-haiku-4-5` _(in 7 schemas)_ |
| `(shared enum)` | `ANTHROPICModel` | server offers `claude-opus-4-7` _(in 7 schemas)_ |
| `(shared enum)` | `ANTHROPICModel` | server offers `claude-opus-4-8` _(in 7 schemas)_ |
| `(shared enum)` | `ANTHROPICModel` | server offers `claude-opus-5` _(in 7 schemas)_ |
| `(shared enum)` | `ANTHROPICModel` | server offers `claude-sonnet-5` _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | server offers `gemini-2.5-flash-lite` _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | server offers `gemini-3.1-flash-lite` _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | server offers `gemini-3.5-flash-lite` _(in 7 schemas)_ |
| `(shared enum)` | `GOOGLEModel` | server offers `gemini-3.6-flash` _(in 7 schemas)_ |
| `(shared enum)` | `OPENAIModel` | server offers `gpt-5.2-pro` _(in 7 schemas)_ |
| `(shared enum)` | `OPENAIModel` | server offers `gpt-5.4-pro` _(in 7 schemas)_ |

## missing-property (29)

| Endpoint | Model | Detail |
|---|---|---|
| `/v1/nodes/schema/say_llm` | `SayLLMNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/worker_llm` | `WorkerLLMNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/super_node` | `SuperNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/say_static` | `SayStaticMessageNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/tool_node` | `ToolNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/workflow_run_fetch` | `WorkflowRunFetchNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/workflow_run_evaluator` | `WorkflowRunEvalLLMNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/start_conversation` | `StartConversationNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/end_conversation` | `EndConversationNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/send_sms` | `SendSMSNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/google_docs` | `GoogleDocsNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/http_request` | `HttpRequestNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/athena_patients_search` | `AthenaPatientsSearchNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/athena_patients_update` | `AthenaPatientsUpdateNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/athena_patients_create` | `AthenaPatientsCreateNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/athena_appointments_create` | `AthenaAppointmentsCreateNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/deduplicate` | `DeduplicateNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/nodes/schema/field_extractor` | `FieldExtractorNodeConfig` | server has `self_loop_config`, mirror does not |
| `/v1/edges/schema/direct` | `DirectEdgeConfig` | server has `companion_thread_config`, mirror does not |
| `/v1/edges/schema/conditional` | `ConditionalEdgeConfig` | server has `evaluate_while_waiting_config`, mirror does not |
| `/v1/tools/schema/inline_python` | `InlinePythonToolConfig` | server has `side_effect`, mirror does not |
| `/v1/tools/schema/external_api` | `ExternalAPIToolConfig` | server has `side_effect`, mirror does not |
| `/v1/tools/schema/knowledge_base` | `KnowledgeBaseToolConfig` | server has `side_effect`, mirror does not |
| `/v1/tools/schema/inbuilt_function` | `InbuiltFunctionToolConfig` | server has `side_effect`, mirror does not |
| `/v1/workflows/schema` | `WorkflowConfig` | server has `access_config`, mirror does not |
| `/v1/workflow-runs/schema#run_schema` | `WorkflowRun` | server has `voice_conversation_id`, mirror does not |
| `/v1/workflow-runs/schema#run_input_schema` | `WorkflowRunInput` | server has `welcome_message`, mirror does not |
| `/v1/workflow-runs/schema#run_input_output_pair_schema` | `WorkflowRunInputOutputPair` | server has `comments`, mirror does not |
| `/v1/workflow-runs/schema#run_input_output_pair_schema` | `WorkflowRunInputOutputPair` | server has `ratings`, mirror does not |

## Endpoints with no local model (1)

The server serves these but the mirror has no class for them — usually a genuinely new type.

- `/v1/nodes/schema/no_op`
