# Config parity report — `interactly_configs` vs upstream

- Upstream sources (3): `configs`, `event.py`, `acls.py`
- Mirror:   `/Users/shivachaitanya/Documents/work/Interactly/repos_for_shiva_learnings/workflow-sdk/configs/src/interactly_configs`
- **Total differences: 143** (2 placement differences, reported but not counted)

## Classes missing from the mirror (31)

| Class | Upstream module |
|---|---|
| `AgenticGraphHolder` | `workflow.py` |
| `BEDROCKModel` | `llm.py` |
| `CallForwardExtraConfig` | `configurable_inbuilt_tools/call_forward.py` |
| `CommentRequest` | `comment.py` |
| `CompanionStepBoundaryEvent` | `event.py` |
| `CompanionThreadConfig` | `edge.py` |
| `ConfigurableInbuiltToolEntry` | `configurable_inbuilt_tools/__init__.py` |
| `EvaluateWhileWaitingConfig` | `edge.py` |
| `GuardrailEscalationEdgeEvent` | `event.py` |
| `IterationCallLatencyStats` | `event.py` |
| `NoOpNodeConfig` | `nodes/utility/no_op.py` |
| `NoOpNodeRunInput` | `nodes/utility/no_op.py` |
| `NoOpNodeRunOutput` | `nodes/utility/no_op.py` |
| `NodeExpiredEvent` | `event.py` |
| `RatingConfig` | `rating.py` |
| `RatingRequest` | `rating.py` |
| `RatingValue` | `rating.py` |
| `SelfLoopConfig` | `nodes/node.py` |
| `SelfLoopDelayEvent` | `event.py` |
| `SelfLoopExhaustedEvent` | `event.py` |
| `StructuredOutputRetryAttempt` | `event.py` |
| `StructuredOutputRetryMetadata` | `event.py` |
| `UILoginRole` | `acls.py` |
| `UISpecialFieldTypes` | `acls.py` |
| `WaitingConditionMatchedEvent` | `event.py` |
| `WaitingEvaluationBoundaryEvent` | `event.py` |
| `WaitingEvaluationTriggerMode` | `edge.py` |
| `WorkflowAccessConfig` | `workflow.py` |
| `WorkflowDefaultLLMConfig` | `llm.py` |
| `WorkflowIterationMetrics` | `event.py` |
| `WorkflowReadyForInputEvent` | `event.py` |

## Classes only in the mirror (3)

| Class | Mirror module |
|---|---|
| `AccessControlLevelConfig` | `acls.py` |
| `GlobalDefaultLLMConfig` | `llm.py` |
| `WorkflowExecutionStatus` | `run_output.py` |

## Fields missing from the mirror (46)

| Class | Field | Upstream type |
|---|---|---|
| `AthenaAppointmentsCreateNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `AthenaPatientsCreateNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `AthenaPatientsSearchNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `AthenaPatientsUpdateNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `BaseLLMNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `BaseNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `BaseToolConfig` | `side_effect` | `Optional[str]` |
| `BedrockLLMConfig` | `region` | `Optional[str]` |
| `ConditionEvaluatorLLMNodeEvent` | `destination_node_logical_id` | `Optional[str]` |
| `ConditionEvaluatorLLMNodeEvent` | `is_condition_met` | `Optional[bool]` |
| `ConditionalEdgeConfig` | `evaluate_while_waiting_config` | `Optional[EvaluateWhileWaitingConfig]` |
| `ConditionalEdgeEvent` | `super_node_exit_origin` | `Optional[str]` |
| `DeduplicateNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `DirectEdgeConfig` | `companion_thread_config` | `Optional[CompanionThreadConfig]` |
| `DiscardedMainLLMNodeEvent` | `reason` | `Literal['global_condition_matched']` |
| `EndConversationNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `EndWorkflowIterationEvent` | `iteration_metrics` | `Optional[WorkflowIterationMetrics]` |
| `ExternalAPIToolConfig` | `side_effect` | `Optional[str]` |
| `FieldExtractorNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `GoogleDocsNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `HttpRequestNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `InbuiltFunctionToolConfig` | `side_effect` | `Optional[str]` |
| `InlinePythonToolConfig` | `side_effect` | `Optional[str]` |
| `KnowledgeBaseToolConfig` | `side_effect` | `Optional[str]` |
| `LLMGroupConfig` | `named_llm_config_id` | `Optional[str]` |
| `LLMGroupConfig` | `named_llm_config_name` | `Optional[str]` |
| `LLMGroupWithBackchannelConfig` | `named_llm_config_id` | `Optional[str]` |
| `LLMGroupWithBackchannelConfig` | `named_llm_config_name` | `Optional[str]` |
| `LLMUsageInfo` | `named_llm_config_id` | `Optional[str]` |
| `LLMUsageInfo` | `named_llm_config_name` | `Optional[str]` |
| `LLMUsageInfo` | `structured_output_retry_metadata` | `Optional[StructuredOutputRetryMetadata]` |
| `ReverseConditionalEdgeEvent` | `super_node_exit_origin` | `Optional[str]` |
| `SayLLMNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `SayStaticMessageNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `SendSMSNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `StartConversationNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `SuperNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `ToolNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `WorkerLLMNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `WorkflowConfig` | `access_config` | `Optional[WorkflowAccessConfig]` |
| `WorkflowRun` | `voice_conversation_id` | `Optional[str]` |
| `WorkflowRunEvalLLMNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `WorkflowRunFetchNodeConfig` | `self_loop_config` | `Optional[SelfLoopConfig]` |
| `WorkflowRunInput` | `welcome_message` | `Optional[str]` |
| `WorkflowRunInputOutputPair` | `comments` | `List[CommentConfig]` |
| `WorkflowRunInputOutputPair` | `ratings` | `List[RatingConfig]` |

## Fields only in the mirror (4)

| Class | Field | Mirror type |
|---|---|---|
| `BedrockLLMConfig` | `aws_session_token` | `Optional[SecretStr]` |
| `BedrockLLMConfig` | `region_name` | `Optional[str]` |
| `WorkflowTemplateConfig` | `access_level` | `Optional[AccessControlLevel]` |
| `WorkflowTemplateConfig` | `access_list` | `Optional[List[str]]` |

## Field type mismatches (28)

| Class | Field | Upstream | Mirror |
|---|---|---|---|
| `AthenaAppointmentsCreateNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `AthenaPatientsCreateNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `AthenaPatientsSearchNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `AthenaPatientsUpdateNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `BaseNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `BaseRunOutput` | `events` | `StoredEvents` | `List` |
| `BedrockLLMConfig` | `api_key` | `Optional[str]` | `Optional[SecretStr]` |
| `BedrockLLMConfig` | `aws_access_key_id` | `Optional[str]` | `Optional[SecretStr]` |
| `BedrockLLMConfig` | `aws_secret_access_key` | `Optional[str]` | `Optional[SecretStr]` |
| `BedrockLLMConfig` | `model` | `Optional[BEDROCKModel]` | `Optional[str]` |
| `DeduplicateNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `EndConversationNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `FieldExtractorNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `GoogleDocsNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `HttpRequestNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `SayLLMNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `SayStaticMessageNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `SendSMSNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `SimulationEvent` | `payload` | `Optional[Event]` | `Optional[Any]` |
| `StartConversationNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `SuperNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `ToolNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `WorkerLLMNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `WorkflowConfigFullyHydrated` | `node_configs` | `List[NodeConfig]` | `List[SerializeAsAny[BaseNodeConfig]]` |
| `WorkflowRunEvalLLMNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `WorkflowRunFetchNodeRunOutput` | `events` | `StoredEvents` | `List` |
| `WorkflowRunOutput` | `events` | `StoredEvents` | `List` |
| `WorkflowShowStateEvent` | `thread_id` | `str` | `Optional[str]` |

## Enum values missing from the mirror (14)

| Enum | Value |
|---|---|
| `ANTHROPICModel` | `claude-fable-5` |
| `ANTHROPICModel` | `claude-haiku-4-5` |
| `ANTHROPICModel` | `claude-opus-4-7` |
| `ANTHROPICModel` | `claude-opus-4-8` |
| `ANTHROPICModel` | `claude-opus-5` |
| `ANTHROPICModel` | `claude-sonnet-5` |
| `GOOGLEModel` | `gemini-2.5-flash-lite` |
| `GOOGLEModel` | `gemini-3.1-flash-lite` |
| `GOOGLEModel` | `gemini-3.5-flash-lite` |
| `GOOGLEModel` | `gemini-3.6-flash` |
| `NodeCategory` | `Utility` |
| `NodeType` | `no_op` |
| `OPENAIModel` | `gpt-5.2-pro` |
| `OPENAIModel` | `gpt-5.4-pro` |

## Enum values only in the mirror (server would reject these) (9)

| Enum | Value |
|---|---|
| `ANTHROPICModel` | `claude-opus-4-20250514` |
| `ANTHROPICModel` | `claude-sonnet-4-20250514` |
| `GOOGLEModel` | `gemini-1.5-flash` |
| `GOOGLEModel` | `gemini-1.5-flash-8b` |
| `GOOGLEModel` | `gemini-1.5-pro` |
| `GOOGLEModel` | `gemini-2.0-flash` |
| `GOOGLEModel` | `gemini-2.0-flash-lite` |
| `OPENAIModel` | `gpt-5-chat-latest` |
| `OPENAIModel` | `gpt-5.1-chat-latest` |

## Enum capability data (`nonmember`) missing from the mirror (8)

| Enum | Attribute |
|---|---|
| `ANTHROPICModel` | `ADAPTIVE_THINKING_MODELS` |
| `ANTHROPICModel` | `ALWAYS_THINKING_MODELS` |
| `ANTHROPICModel` | `DEFAULT_ADAPTIVE_THINKING_MAX_TOKENS` |
| `ANTHROPICModel` | `DEFAULT_MAX_TOKENS` |
| `GOOGLEModel` | `ALWAYS_THINKING_MODELS` |
| `OPENAIModel` | `LOW_REASONING_EFFORTS` |
| `OPENAIModel` | `MINIMUM_PRO_REASONING_EFFORT` |
| `OPENAIModel` | `MODELS_WITHOUT_LOW_REASONING_EFFORT` |

## Module placement differences (informational) (2)

| Class | Upstream module | Mirror module |
|---|---|---|
| `BaseEntityConfig` | `base_defs.py` | `base.py` |
| `WorkflowCommand` | `workflow_run.py` | `run_input.py` |
