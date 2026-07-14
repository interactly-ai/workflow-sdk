"""Tool configuration models."""

import json
from enum import Enum
from typing import Annotated, Dict, List, Literal, Optional, Type, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from interactly_configs.prompt import StaticMessagesConfig


class ToolType(str, Enum):
    """Enumeration of tool types."""

    INBUILT_FUNCTION = "inbuilt_function"
    INLINE_PYTHON = "inline_python"
    EXTERNAL_API = "external_api"
    KNOWLEDGE_BASE = "knowledge_base"

    @classmethod
    def list(cls) -> List["ToolType"]:
        return [cls.INBUILT_FUNCTION, cls.INLINE_PYTHON, cls.EXTERNAL_API, cls.KNOWLEDGE_BASE]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.list()

    @classmethod
    def get_description(cls) -> str:
        return f"Type of the tool. Must be one of: {', '.join(t.value for t in cls.list())}"

    @classmethod
    def get_type_to_config_map(cls) -> dict["ToolType", Type["BaseToolConfig"]]:
        """Returns a mapping of tool types to their respective configuration classes."""
        return {
            cls.INBUILT_FUNCTION: InbuiltFunctionToolConfig,
            cls.INLINE_PYTHON: InlinePythonToolConfig,
            cls.EXTERNAL_API: ExternalAPIToolConfig,
            cls.KNOWLEDGE_BASE: KnowledgeBaseToolConfig,
        }


class BaseToolConfig(BaseModel):
    """Base configuration for a tool."""

    logical_id: Optional[str] = Field(
        default_factory=lambda: "tool_" + str(uuid4()),
        description="Unique identifier for the tool",
        title="Tool ID",
    )
    tool_id: Optional[str] = Field(
        default=None,
        description=(
            "Reference to the tool already created in the Workflow System. "
            "If not provided, the tool config is assumed to be provided inline here."
        ),
        title="Attachable Tool ID",
    )
    name: Optional[str] = Field(default=None, description="Name for the tool", title="Tool Name")
    description: Optional[str] = Field(
        default=None,
        description="Human friendly description for the tool (not used by AI)",
        title="Tool Description",
    )
    category: Optional[str] = Field(
        default=None,
        description="Category for the tool. E.g math, ehr, etc",
        title="Tool Category",
    )
    signature: Optional[str] = Field(
        default=None,
        description=(
            "Docstring or signature for the tool used by AI. "
            "If provided and there is a default signature already, it will override the default signature."
        ),
        title="Tool Signature",
    )
    args_schema: Optional[dict] = Field(
        default=None,
        description=(
            "Schema for the arguments that the tool accepts. "
            "This should be a JSON schema dictionary."
        ),
        title="Tool Arguments Schema",
    )
    static_messages_config: Optional[StaticMessagesConfig] = Field(
        default=None,
        description="Static messages that an LLM node should emit while this tool is being invoked",
        title="Static Messages Configuration",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default="tool_result",
        description="Name of the runtime variable to store the result from this tool call",
        title="Result Runtime Variable Name",
    )
    ignore_content_received_during_llm_tool_call_specification: bool = Field(
        default=False,
        description=(
            "If true, any free-text content the LLM returns in the same response as a call to "
            "this tool is ignored: not emitted via AssistantResponseEvent, not added to chat "
            "history, and not added to the node's structured output. When a response contains "
            "multiple tool calls, the text is ignored only if every tool call targets a tool "
            "for which this flag is set."
        ),
        title="Ignore content received during LLM tool call specification",
    )


class InbuiltFunctionToolConfig(BaseToolConfig):
    """Configuration for an inbuilt function tool registered in the tools registry."""

    type: Literal["inbuilt_function"] = Field(
        default=ToolType.INBUILT_FUNCTION.value,
        description="Type of the tool. Must be 'inbuilt_function'",
        title="Tool Type",
    )
    configurable_key: Optional[str] = Field(
        default=None,
        description=(
            "Stable key identifying which configurable inbuilt tool this is (e.g. 'call_forward'). "
            "None for plain static inbuilt references."
        ),
        title="Configurable Tool Key",
    )
    extra_config: Optional[dict] = Field(
        default=None,
        description="Tool-specific user configuration values. Schema is defined per configurable key.",
        title="Extra Configuration",
    )

    model_config = ConfigDict(title="Inbuilt Function Tool")


class InlinePythonToolConfig(BaseToolConfig):
    """Configuration for an inline Python tool.

    The ``code`` field should contain a self-contained executable Python function::

        def add(a: float, b: float) -> float:
            return float(a + b)
    """

    type: Literal["inline_python"] = Field(
        default=ToolType.INLINE_PYTHON.value,
        description="Type of the tool. Must be 'inline_python'",
        title="Tool Type",
    )
    code: Optional[str] = Field(
        default=None,
        description=(
            "Python code to be executed by the tool. "
            "It should define a function with proper signature and descriptions for its parameters."
        ),
        title="Tool Code",
    )

    model_config = ConfigDict(title="Inline Python Tool")


class APIMethodType(str, Enum):
    """Enumeration of HTTP methods for API calls."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"

    @classmethod
    def list(cls) -> List["APIMethodType"]:
        return [cls.GET, cls.POST, cls.PUT, cls.DELETE]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.list()

    @classmethod
    def get_description(cls) -> str:
        return f"HTTP method. Must be one of: {', '.join(m.value for m in cls.list())}"


class ExternalAPIToolConfig(BaseToolConfig):
    """Configuration for an external API tool."""

    type: Literal["external_api"] = Field(
        default=ToolType.EXTERNAL_API.value,
        description="Type of the tool. Must be 'external_api'",
        title="Tool Type",
    )
    api_endpoint: Optional[str] = Field(
        default=None,
        description="The endpoint URL of the external API",
        title="API Endpoint",
    )
    api_method: Optional[APIMethodType] = Field(
        default=APIMethodType.GET,
        description="HTTP method to use for the API call (e.g., GET, POST)",
        title="API Method",
    )
    api_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers to include with the API request",
        title="API Headers",
    )
    api_body: Optional[Union[dict, str]] = Field(
        default=None,
        description="The request body payload for the API call.",
        title="API Request Body",
    )

    @field_validator("api_body", mode="before")
    @classmethod
    def parse_api_body(cls, v: Optional[Union[dict, str]]) -> Optional[dict]:
        if isinstance(v, str):
            if not v.strip():
                return None
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"api_body must be valid JSON when provided as a string. Error: {e}") from e
        return v

    model_config = ConfigDict(title="External API Tool")


class KnowledgeBaseToolConfig(BaseToolConfig):
    """Configuration for a knowledge base tool."""

    type: Literal["knowledge_base"] = Field(
        default=ToolType.KNOWLEDGE_BASE.value,
        description="Type of the tool. Must be 'knowledge_base'",
        title="Tool Type",
    )
    target_knowledge_base_ids: List[str] = Field(
        default_factory=list,
        description="The IDs of the knowledge bases to query",
        title="Target Knowledge Base IDs",
    )
    category: Optional[str] = Field(
        default="Knowledge Base",
        description="Category for the tool.",
        title="Tool Category",
    )
    signature: Optional[str] = Field(
        default=(
            "Searches the knowledge bases given a natural language query "
            "and retrieves relevant chunks of information matching the query."
        ),
        description="Docstring or signature for the tool used by AI.",
        title="Tool Signature",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default="kb_tool_result",
        description="Name of the runtime variable to store the result from this tool call",
        title="Result Runtime Variable Name",
    )

    model_config = ConfigDict(title="Knowledge Base Tool")


class MCPServerConfig(BaseModel):
    """Configuration for an MCP (Model Context Protocol) server connection."""

    name: Optional[str] = Field(
        default=None,
        description="Display name for this MCP server connection",
        title="Server Name",
    )
    server_url: str = Field(
        description="MCP server URL (e.g. 'https://mcp.example.com/mcp')",
        title="Server URL",
    )
    api_headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="HTTP headers to include when connecting to the MCP server",
        title="API Headers",
    )

    model_config = ConfigDict(title="MCP Server Configuration")


ToolConfig = Annotated[
    Union[InlinePythonToolConfig, InbuiltFunctionToolConfig, ExternalAPIToolConfig, KnowledgeBaseToolConfig],
    Field(discriminator="type"),
]


class ToolsConfig(BaseModel):
    tools: List[ToolConfig] = Field(
        default_factory=list,
        description="List of tool configurations",
        title="Tools Configuration",
    )

    model_config = ConfigDict(title="Tools Configuration")
