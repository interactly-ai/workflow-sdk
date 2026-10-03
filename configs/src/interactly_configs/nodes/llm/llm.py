from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from interactly_configs.llm import WorkflowDefaultLLMConfig
from interactly_configs.llm_group import LLMOrGroupConfig
from interactly_configs.nodes.node import BaseNodeConfig, BaseNodeRunInput, BaseNodeRunOutput, NodeType
from interactly_configs.prompt import PromptConfig
from interactly_configs.tool import ToolsConfig

DEFAULT_LLM_NODE_ERROR_MESSAGE = "I am sorry, there seems to be an issue. Could you please repeat?"


class NodeRealtimeOverrides(BaseModel):
    """Per-node realtime voice settings, applied only while this node is the active one.

    Everything here is optional, and ``None`` means "inherit from the workflow": nothing here turns
    realtime voice on or off. The whole object is ignored unless the workflow runs on a realtime
    (speech-to-speech) model.

    ``transcription_keywords`` is the field worth knowing about, because the classic voice path has no
    equivalent. The realtime session is re-primed at every node transition, so a node that collects a
    member ID can bias speech recognition toward plan names and digit words for the span of that node
    only, and stop biasing the moment the conversation moves on.

    There is deliberately no "say this verbatim" flag: edge messages are spoken in the model's own words.
    """

    reasoning_effort: Optional[str] = Field(
        default=None,
        description=(
            "Reasoning effort while this node is active — one of minimal, low, medium, high, xhigh. "
            "Leave empty to inherit the workflow default. Worth raising on a node that has to choose "
            "between several similar-sounding paths; costly to raise everywhere."
        ),
        title="Reasoning Effort",
    )
    voice: Optional[str] = Field(
        default=None,
        description=(
            "Voice for this node only. Rarely useful: changing voice mid-conversation is jarring to "
            "a caller, who hears it as being handed to a different person."
        ),
        title="Voice",
    )
    preamble_mode: Optional[str] = Field(
        default=None,
        description=(
            "Whether the model may speak a short filler line before a slow answer while this node "
            "is active. Leave empty to inherit."
        ),
        title="Preamble Mode",
    )
    transcription_keywords: List[str] = Field(
        default_factory=list,
        description=(
            "Terms to bias speech recognition toward while this node is active — added to the "
            "workflow-wide list rather than replacing it. Use for the identifiers a node actually "
            "asks for: plan names, member ID formats, provider names."
        ),
        title="Transcription Keywords",
    )
    turn_detection: Optional[dict] = Field(
        default=None,
        description=(
            "Override end-of-speech detection for this node, e.g. to wait longer while a caller "
            "reads out a long number. Leave empty to inherit the session default."
        ),
        title="Turn Detection",
    )

    model_config = ConfigDict(title="Realtime Overrides")


class BaseLLMNodeConfig(BaseNodeConfig):
    primary_category: Optional[str] = Field(
        default="System",
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default="LLM",
        description="Secondary category of the node",
        title="Secondary Category",
    )
    main_response_config: Optional[PromptConfig] = Field(
        default=None,
        description="Main response configuration. Contains either a LLM system prompt or exact static messages",
        title="Main Response Configuration",
    )
    attachable_llm_config_id: Optional[str] = Field(
        default=None,
        description="ID of the named LLM Configuration to use. If provided, overrides inline configuration.",
    )
    llms_config: Optional[LLMOrGroupConfig] = Field(
        default=WorkflowDefaultLLMConfig(),
        description="LLM or a group of LLMs to be used in this node",
        title="LLM Configuration",
    )
    tools_config: Optional[ToolsConfig] = Field(
        default=None,
        description="List of tools available for this node",
        title="Tools Configuration",
    )
    self_loop: bool = Field(
        default=False,
        description="Whether this node will execute again if not transitioned to another node",
        title="Self Loop",
    )
    wait_for_user_message: bool = Field(
        default=True,
        description="Whether the node should wait for a user message before processing",
        title="Wait for User Message",
    )
    max_consecutive_tool_calls: int = Field(
        default=1,
        description="Maximum number of consecutive tool calls allowed in a single node execution",
        title="Max Consecutive Tool Calls",
    )
    default_error_message: Optional[str] = Field(
        default=DEFAULT_LLM_NODE_ERROR_MESSAGE,
        description="Default error message to be returned if the LLM invocation fails",
        title="Default Error Message",
    )
    use_mcp_tools: bool = Field(
        default=False,
        description="Whether this node should use tools discovered from workflow-level MCP server connections",
        title="Use MCP Tools",
    )
    ignore_default_prompt_prefix: bool = Field(
        default=False,
        description="If true, the workflow's default_prompt_prefix will not be prepended to this node's prompt.",
        title="Ignore Default Prompt Prefix",
    )
    ignore_default_prompt_suffix: bool = Field(
        default=False,
        description="If true, the workflow's default_prompt_suffix will not be appended to this node's prompt.",
        title="Ignore Default Prompt Suffix",
    )
    ignore_content_received_during_llm_tool_call_specification: bool = Field(
        default=False,
        description=(
            "If true, any free-text content this node's LLM returns in the same response as one "
            "or more tool calls is ignored: not emitted via AssistantResponseEvent, not added to "
            "chat history, and not added to the node's structured output. Implies the tool-level "
            "flag for every tool call this node makes."
        ),
        title="Ignore content received during LLM tool call specification",
    )
    realtime_overrides: Optional[NodeRealtimeOverrides] = Field(
        default=None,
        description=(
            "Realtime voice settings that apply only while this node is active. Ignored unless the "
            "workflow has realtime voice enabled. None means inherit everything from the workflow."
        ),
        title="Realtime Overrides",
    )

EXAMPLE_STRUCTURED_SCHEMA = """
{
        "name": "SearchQuery",
        "description": "A search query with justification",
        "input_schema": {
            "title": "AnswerWithJustification",
            "type": "object",
            "properties": {
                "search_query": {
                    "title": "Search Query",
                    "type": "string",
                    "description": "The field where search query is stored"
                },
                "justification": {
                    "title": "Justification",
                    "type": "string",
                    "description": "The field where justification string is stored"
                }
            },
            "required": ["search_query", "justification"]
        }
    }
"""

class WorkerLLMNodeConfig(BaseLLMNodeConfig):
    type: Literal["worker_llm"] = Field(
        default=NodeType.WORKER_LLM.value,
        description="Type of the node. Must be 'worker_llm'",
        title="Node Type",
    )
    structured_output_schema: Optional[dict] = Field(
        default=None,
        description=f"Schema for the structured output of the worker node. Example: {EXAMPLE_STRUCTURED_SCHEMA}",
        title="Structured Output Schema",
    )
    self_loop: bool = Field(
        default=False,
        description="Whether this node will execute again if not transitioned to another node",
        title="Self Loop",
    )
    backchannel_response_config: Optional[PromptConfig] = Field(
        default=None,
        description="Backchannel response configuration. Contains either a LLM system prompt or exact static messages",
        title="Backchannel Response Configuration",
    )

    model_config = ConfigDict(
        title="Worker LLM Node",
    )

class SayLLMNodeConfig(BaseLLMNodeConfig):
    type: Literal["say_llm"] = Field(
        default=NodeType.SAY_LLM.value,
        description="Type of the node. Must be 'say_llm'",
        title="Node Type",
    )
    structured_output_schema: Optional[dict] = Field(
        default=None,
        description=f"Schema for the structured output requested from the say node after it produces a response. Example: {EXAMPLE_STRUCTURED_SCHEMA}",
        title="Structured Output Schema",
    )
    backchannel_response_config: Optional[PromptConfig] = Field(
        default=None,
        description="Backchannel response configuration. Contains either a LLM system prompt or exact static messages",
        title="Backchannel Response Configuration",
    )
    self_loop: bool = Field(
        default=True,
        description="Whether this node will execute again if not transitioned to another node",
        title="Self Loop",
    )

    model_config = ConfigDict(
        title="LLM Node",
    )

class LLMNodeRunInput(BaseNodeRunInput):
    type: Literal["llm"] = Field(default="llm", description="Discriminator field which must always be 'llm'")
    messages: List[Any] = Field(
        default_factory=list,
        description="Input user messages to be processed by the LLM node",
        title="Input User Messages",
    )

class SayLLMNodeRunOutput(BaseNodeRunOutput):
    type: Literal["say_llm"] = Field(
        default="say_llm", description="Discriminator field which must always be 'say_llm'"
    )
    structured_output: dict = Field(
        default_factory=dict,
        description="Structured output from the say node",
        title="Structured Output",
    )

class WorkerLLMNodeRunOutput(BaseNodeRunOutput):
    type: Literal["worker_llm"] = Field(
        default="worker_llm",
        description="Discriminator field which must always be 'worker_llm'",
    )
    structured_output: dict = Field(
        default_factory=dict,
        description="Structured output from the worker node",
        title="Structured Output",
    )
