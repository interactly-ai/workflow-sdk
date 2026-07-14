"""LLM configuration models — stripped of all server-side dependencies."""

from enum import Enum
from typing import Annotated, Any, Dict, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer

from interactly_configs.auth import OktaAuthConfig


class LLMProvider(str, Enum):
    DEFAULTPROVIDER = "default_provider"
    AZUREOPENAI = "azure_openai"
    OPENAI = "openai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    CUSTOM = "custom"


class AZUREOPENAIModel(str, Enum):
    GPT_5_CHAT = "gpt-5-chat"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_NANO = "gpt-5-nano"
    GPT_4_1_NANO = "gpt-4.1-nano"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1 = "gpt-4.1"


class OPENAIModel(str, Enum):
    # GPT 5.x Models
    GPT_5_4 = "gpt-5.4"
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_4_NANO = "gpt-5.4-nano"
    GPT_5_2 = "gpt-5.2"
    GPT_5_1 = "gpt-5.1"

    # GPT 5.x Chat Optimized Models
    GPT_5_CHAT_LATEST = "gpt-5-chat-latest"
    GPT_5_1_CHAT_LATEST = "gpt-5.1-chat-latest"
    GPT_5_2_CHAT_LATEST = "gpt-5.2-chat-latest"
    GPT_5_3_CHAT_LATEST = "gpt-5.3-chat-latest"

    # GPT 5 Models (consume reasoning tokens by default)
    GPT_5_NANO = "gpt-5-nano"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5 = "gpt-5"

    # GPT 4 Models
    GPT_4_1_NANO = "gpt-4.1-nano"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1 = "gpt-4.1"
    GPT_4 = "gpt-4"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"

    # GPT 3.5 Models
    GPT_3_5_TURBO = "gpt-3.5-turbo"


class GOOGLEModel(str, Enum):
    # Floating models pointing to latest stable versions
    GEMINI_FLASH_LATEST = "gemini-flash-latest"
    GEMINI_FLASH_LITE_LATEST = "gemini-flash-lite-latest"

    GEMINI_3_1_PRO_PREVIEW = "gemini-3.1-pro-preview"
    GEMINI_3_FLASH_PREVIEW = "gemini-3-flash-preview"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_0_FLASH_LITE = "gemini-2.0-flash-lite"
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_3_5_FLASH = "gemini-3.5-flash"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"
    GEMINI_1_5_FLASH_8B = "gemini-1.5-flash-8b"


class ANTHROPICModel(str, Enum):
    CLAUDE_OPUS_4_6 = "claude-opus-4-6"
    CLAUDE_OPUS_4_5_20251101 = "claude-opus-4-5-20251101"
    CLAUDE_OPUS_4_1_20250805 = "claude-opus-4-1-20250805"
    CLAUDE_OPUS_4_20250514 = "claude-opus-4-20250514"

    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_SONNET_4_5_20250929 = "claude-sonnet-4-5-20250929"
    CLAUDE_SONNET_4_20250514 = "claude-sonnet-4-20250514"

    CLAUDE_HAIKU_4_5_20251001 = "claude-haiku-4-5-20251001"


class BaseLLMConfig(BaseModel):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "llm_" + str(uuid4()),
        description="Unique identifier for the LLM configuration",
        title="LLM Configuration ID",
    )
    named_llm_config_id: Optional[str] = Field(
        default=None,
        description="If this configuration was resolved from a reusable named LLM configuration, this holds its ID.",
        title="Named LLM Config ID",
    )
    named_llm_config_name: Optional[str] = Field(
        default=None,
        description="If this configuration was resolved from a reusable named LLM configuration, this holds its name.",
        title="Named LLM Config Name",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.DEFAULTPROVIDER,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    streaming: bool = Field(
        default=False,
        description="Whether to enable streaming for the LLM response.",
        title="Enable Streaming",
    )
    max_retries: Optional[int] = Field(
        default=3,
        description="Maximum number of retries for the LLM request in case of failure.",
        title="Max Retries",
    )
    max_parse_retries: Optional[int] = Field(
        default=3,
        description=(
            "Maximum number of times to re-invoke the LLM when a successful response cannot be parsed "
            "into the expected structured (JSON) output. Distinct from `max_retries`, which controls "
            "transport-level retries (network errors, rate limits, 5xx) inside the LLM client."
        ),
        title="Max Parse Retries",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum number of tokens to generate in the response.",
        title="Max Tokens",
    )
    temperature: Optional[float] = Field(
        default=None,
        description="Controls the randomness of the model's output. Lower values make the output more deterministic.",
        title="Temperature",
        ge=0.0,
        le=1.0,
    )
    request_timeout_ms: Optional[int] = Field(
        default=None,
        description="Timeout for the request in milliseconds.",
        title="Request Timeout (ms)",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Seed for random number generation to ensure reproducibility.",
        title="Random Seed",
    )
    model_kwargs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional keyword arguments to pass to the LLM provider's API.",
        title="Model Keyword Arguments",
    )
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="API KEY to access the LLM provider endpoint",
        title="API Key",
    )
    do_not_split_sentences: bool = Field(
        default=False,
        description="Whether to avoid splitting sentences in the LLM response.",
        title="Do Not Split Sentences",
    )
    truncated_max_recent_messages: Optional[int] = Field(
        default=None,
        description=(
            "Maximum number of recent messages to keep when truncating the conversation history. "
            "If not set, no truncation is applied."
        ),
        title="Truncated Max Recent Messages",
    )

    @field_serializer("api_key")
    def serialize_api_key(self, value: Optional[SecretStr]) -> Optional[str]:
        if value is None:
            return None
        return value.get_secret_value()


class AzureOpenAILLMConfig(BaseLLMConfig):
    model: Optional[AZUREOPENAIModel] = Field(
        default=AZUREOPENAIModel.GPT_5_MINI,
        description="Name of the Azure OpenAI model to use",
        title="Azure OpenAI Model",
    )
    type: Literal["azure_openai_llm"] = Field(
        default="azure_openai_llm",
        description="Discriminator field",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.AZUREOPENAI,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="Endpoint URL for Azure OpenAI API requests.",
        title="Azure OpenAI Endpoint",
    )
    api_version: Optional[str] = Field(
        default=None,
        description="Azure OpenAI API version.",
        title="Azure OpenAI API Version",
    )
    reasoning_effort: Optional[str] = Field(
        default="low",
        description="Reasoning effort level for GPT-5-* models. Options are 'low', 'medium', 'high'.",
        title="Reasoning Effort",
    )

    model_config = ConfigDict(title="Azure OpenAI")


class OpenAILLMConfig(BaseLLMConfig):
    model: Optional[OPENAIModel] = Field(
        default=OPENAIModel.GPT_5_4_MINI,
        description="Name of the OpenAI model to use",
        title="OpenAI Model",
    )
    type: Literal["openai_llm"] = Field(
        default="openai_llm",
        description="Discriminator field",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.OPENAI,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Base URL path for OpenAI API requests.",
        title="OpenAI Base URL",
    )
    organization: Optional[str] = Field(
        default=None,
        description="Organization ID for OpenAI API requests.",
        title="OpenAI Organization ID",
    )
    reasoning_effort: Optional[str] = Field(
        default="low",
        description="Reasoning effort level for GPT-5-* models. Options are 'minimal', 'low', 'medium', 'high'.",
        title="Reasoning Effort",
    )

    model_config = ConfigDict(title="OpenAI")


class GoogleLLMConfig(BaseLLMConfig):
    model: Optional[GOOGLEModel] = Field(
        default=GOOGLEModel.GEMINI_3_FLASH_PREVIEW,
        description="Name of the Google model to use",
        title="Google Model",
    )
    type: Literal["google_llm"] = Field(
        default="google_llm",
        description="Discriminator field",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.GOOGLE,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    thinking_budget: Optional[int] = Field(
        default=0,
        description="Indicates the thinking budget in tokens. By default, it is set to 0.",
        title="Thinking Budget (tokens)",
    )

    model_config = ConfigDict(title="Google")


class AnthropicLLMConfig(BaseLLMConfig):
    model: Optional[ANTHROPICModel] = Field(
        default=ANTHROPICModel.CLAUDE_SONNET_4_6,
        description="Name of the Anthropic Claude model to use",
        title="Anthropic Model",
    )
    type: Literal["anthropic_llm"] = Field(
        default="anthropic_llm",
        description="Discriminator field",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.ANTHROPIC,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    thinking_budget: Optional[int] = Field(
        default=0,
        description=(
            "Token budget for Claude's extended thinking feature. "
            "Set to 0 to disable."
        ),
        title="Thinking Budget (tokens)",
    )

    model_config = ConfigDict(title="Anthropic")


class CustomLLMConfig(BaseLLMConfig):
    model: Optional[str] = Field(
        default=None,
        description="Name of the model served behind the custom LLM gateway.",
        title="Custom Model Name",
    )
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="Reasoning effort level for GPT-5-* models.",
        title="Reasoning Effort",
    )
    type: Literal["custom_llm"] = Field(
        default="custom_llm",
        description="Discriminator field",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.CUSTOM,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Base URL of the custom OpenAI-compatible LLM gateway.",
        title="Gateway Base URL",
    )
    default_headers: Optional[Dict] = Field(
        default=None,
        description="Optional HTTP headers to include in every request to the gateway.",
        title="Headers",
    )
    rewrite_base_url: bool = Field(
        default=False,
        description=(
            "When True, uses an httpx event hook to rewrite every request URL to the exact base_url. "
            "Use this for gateways that don't accept the /chat/completions suffix the SDK appends."
        ),
        title="Rewrite Base URL",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Whether to verify SSL certificates.",
        title="Verify SSL",
    )
    response_unwrap_key: Optional[str] = Field(
        default=None,
        description=(
            "When set, the gateway response JSON is expected to wrap the standard OpenAI response "
            "inside this key. Leave empty for gateways that already return standard format."
        ),
        title="Response Unwrap Key",
    )
    okta_auth: Optional[OktaAuthConfig] = Field(
        default=None,
        description=(
            "Okta authentication configuration for bearer-token injection. "
            "When set, the runtime resolves credentials using the following chain: "
            "(1) explicit ``api_key`` on the request, "
            "(2) team-level ``custom_llm_api_key`` from vendor credentials, "
            "(3) Okta bearer token fetched via this ``integration_id`` from vendor credentials. "
            "Ignored when ``api_key`` or a bearer Authorization header is already resolved."
        ),
        title="Okta Auth",
    )
    use_responses_api: bool = Field(
        default=False,
        description="Whether to use the GPT 5.x+ style Responses API instead of Chat Completions API.",
        title="Use Responses API",
    )

    model_config = ConfigDict(title="Custom LLM")


class BedrockLLMConfig(BaseLLMConfig):
    model: Optional[str] = Field(
        default=None,
        description="Bedrock model identifier or inference profile ARN (e.g. 'anthropic.claude-sonnet-4-6-v1:0').",
        title="Bedrock Model ID",
    )
    type: Literal["bedrock_llm"] = Field(
        default="bedrock_llm",
        description="Discriminator field",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.BEDROCK,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    region_name: Optional[str] = Field(
        default=None,
        description="AWS region hosting the Bedrock endpoint (e.g. 'us-east-1').",
        title="AWS Region",
    )
    aws_access_key_id: Optional[SecretStr] = Field(
        default=None,
        description="AWS access key ID used to authenticate against Bedrock.",
        title="AWS Access Key ID",
    )
    aws_secret_access_key: Optional[SecretStr] = Field(
        default=None,
        description="AWS secret access key used to authenticate against Bedrock.",
        title="AWS Secret Access Key",
    )
    aws_session_token: Optional[SecretStr] = Field(
        default=None,
        description="Optional AWS session token used for temporary credentials.",
        title="AWS Session Token",
    )

    @field_serializer("aws_access_key_id", "aws_secret_access_key", "aws_session_token")
    def serialize_aws_credentials(self, value: Optional[SecretStr]) -> Optional[str]:
        if value is None:
            return None
        return value.get_secret_value()

    model_config = ConfigDict(title="Bedrock")


class GlobalDefaultLLMConfig(BaseLLMConfig):
    type: Literal["global_default_llm"] = Field(
        default="global_default_llm",
        description="Discriminator field",
    )

    model_config = ConfigDict(title="Global Default LLM")


class NoLLMConfig(BaseLLMConfig):
    type: Literal["no_llm"] = Field(
        default="no_llm",
        description=(
            "Differentiator field that helps in identifying this particular type of config "
            "when serializing and deserializing"
        ),
    )

    model_config = ConfigDict(title="No LLM")


LLMConfigUnion = Union[
    AzureOpenAILLMConfig,
    OpenAILLMConfig,
    GoogleLLMConfig,
    AnthropicLLMConfig,
    BedrockLLMConfig,
    CustomLLMConfig,
    GlobalDefaultLLMConfig,
    NoLLMConfig,
]

LLMConfig = Annotated[LLMConfigUnion, Field(discriminator="type")]
