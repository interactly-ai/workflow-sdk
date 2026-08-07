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
    # These are Azure *deployment* names, not vendor model names: a value is only
    # usable if a deployment with that name exists on the configured Azure OpenAI
    # resource. Verified against the dev resource on 2026-07-30; the GPT-5.4/5.5/5.6
    # series exist in the Foundry catalogue but are not deployed for us yet, so they
    # are deliberately absent here.
    GPT_5_CHAT = "gpt-5-chat"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_NANO = "gpt-5-nano"
    GPT_4_1_NANO = "gpt-4.1-nano"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1 = "gpt-4.1"


class OPENAIModel(str, Enum):
    # GPT 5.x Models. These do not consume reasoning tokens by default (unlike the original GPT-5 series)
    GPT_5_4 = "gpt-5.4"
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_4_NANO = "gpt-5.4-nano"
    GPT_5_2 = "gpt-5.2"
    GPT_5_1 = "gpt-5.1"

    # GPT 5 Models (they consume reasoning tokens by default)
    GPT_5_NANO = "gpt-5-nano"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5 = "gpt-5"

    # Reasoning-heavy "pro" variants. These are served only by the Responses API
    # (/v1/chat/completions returns "This is not a chat model").
    GPT_5_4_PRO = "gpt-5.4-pro"
    GPT_5_2_PRO = "gpt-5.2-pro"

    # GPT 5.x Chat Optimized Models. These do not consume reasoning tokens by default (unlike the original GPT-5 series)
    GPT_5_2_CHAT_LATEST = "gpt-5.2-chat-latest"
    GPT_5_3_CHAT_LATEST = "gpt-5.3-chat-latest"

    # GPT 4 Models
    GPT_4_1_NANO = "gpt-4.1-nano"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1 = "gpt-4.1"
    # DEPRECATED: OpenAI shuts down gpt-4, gpt-4o and gpt-4o-mini on 2026-10-23.
    # Still callable today; kept only so stored workflows keep deserialising.
    GPT_4 = "gpt-4"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"

    # GPT 3.5 Models
    # DEPRECATED: shuts down 2026-10-23. See note above.
    GPT_3_5_TURBO = "gpt-3.5-turbo"


class GOOGLEModel(str, Enum):
    # Floating models that point to the latest stable versions
    GEMINI_FLASH_LATEST = "gemini-flash-latest"
    GEMINI_FLASH_LITE_LATEST = "gemini-flash-lite-latest"

    GEMINI_3_6_FLASH = "gemini-3.6-flash"
    GEMINI_3_1_PRO_PREVIEW = "gemini-3.1-pro-preview"
    GEMINI_3_5_FLASH = "gemini-3.5-flash"
    GEMINI_3_5_FLASH_LITE = "gemini-3.5-flash-lite"
    GEMINI_3_1_FLASH_LITE = "gemini-3.1-flash-lite"
    GEMINI_3_FLASH_PREVIEW = "gemini-3-flash-preview"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    # REMOVED 2026-07-30: gemini-2.0-flash, gemini-2.0-flash-lite, gemini-1.5-pro,
    # gemini-1.5-flash and gemini-1.5-flash-8b are shut down and return 404 on
    # every call, so leaving them selectable only produced runtime failures.


class ANTHROPICModel(str, Enum):
    # Claude 5 models. These reject `temperature` and the legacy
    # thinking={"type": "enabled", "budget_tokens": N} shape -- see
    # ADAPTIVE_THINKING_ANTHROPIC_MODELS below.
    CLAUDE_OPUS_5 = "claude-opus-5"
    CLAUDE_SONNET_5 = "claude-sonnet-5"
    # Highest-capability tier. Requires 30-day data retention (unavailable under
    # zero data retention) and thinking cannot be turned off.
    CLAUDE_FABLE_5 = "claude-fable-5"

    # Claude 4 models
    CLAUDE_OPUS_4_8 = "claude-opus-4-8"
    CLAUDE_OPUS_4_7 = "claude-opus-4-7"
    CLAUDE_OPUS_4_6 = "claude-opus-4-6"
    CLAUDE_OPUS_4_5_20251101 = "claude-opus-4-5-20251101"
    # DEPRECATED: retires 2026-08-05.
    CLAUDE_OPUS_4_1_20250805 = "claude-opus-4-1-20250805"

    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_SONNET_4_5_20250929 = "claude-sonnet-4-5-20250929"

    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"
    # Superseded by the CLAUDE_HAIKU_4_5 alias above; retained so stored configs
    # keep deserialising. Both resolve to the same model.
    CLAUDE_HAIKU_4_5_20251001 = "claude-haiku-4-5-20251001"
    # REMOVED 2026-07-30: claude-opus-4-20250514 and claude-sonnet-4-20250514 are
    # retired and return 404 on every call.


class BEDROCKModel(str, Enum):
    # Serverless open-weight models, invoked via the Converse API. All IDs
    # live-verified in us-east-1 on 2026-08-05; availability is region- and
    # account-dependent (`aws bedrock list-foundation-models`).

    # Z.ai GLM
    GLM_5 = "zai.glm-5"
    GLM_4_7 = "zai.glm-4.7"
    GLM_4_7_FLASH = "zai.glm-4.7-flash"

    # Moonshot AI Kimi
    KIMI_K2_5 = "moonshotai.kimi-k2.5"
    # Always-on reasoning; poor fit for latency-sensitive voice nodes.
    KIMI_K2_THINKING = "moonshot.kimi-k2-thinking"

    # Alibaba Qwen. Deliberately absent: qwen3-235b-2507 (not served in
    # us-east-1), qwen3-next-80b (hesitates on edge routing), qwen3-coder-*.
    QWEN3_VL_235B = "qwen.qwen3-vl-235b-a22b"
    QWEN3_32B = "qwen.qwen3-32b-v1:0"


# --------------------------------------------------------------------------------------------- #
# Model capability data                                                                           #
# --------------------------------------------------------------------------------------------- #
# Upstream carries these INSIDE the enum bodies, wrapped in `enum.nonmember(...)` so they stay
# capability data instead of becoming selectable members. `enum.nonmember` is Python 3.11+, and this
# package supports 3.10 (see `requires-python`), so the mirror hoists them to module scope instead —
# the only mechanism available that keeps them out of the enums' member lists on 3.10. The names and
# values are upstream's; only the lookup path differs (`MODELS_WITHOUT_LOW_REASONING_EFFORT` rather
# than `OPENAIModel.MODELS_WITHOUT_LOW_REASONING_EFFORT`).
#
# This is client-side reference data: the SDK never calls a provider itself, but knowing these rules
# lets caller code reject an unsupported combination before paying for a round trip.

#: The "pro" reasoning variants reject the lower effort levels: the Responses API returns 400
#: "Unsupported value: 'low' is not supported with the 'gpt-5.4-pro' model. Supported values are:
#: 'medium', 'high', and 'xhigh'." Since `reasoning_effort` defaults to "low", every call to a pro
#: model would otherwise fail out of the box.
MODELS_WITHOUT_LOW_REASONING_EFFORT = frozenset({OPENAIModel.GPT_5_4_PRO, OPENAIModel.GPT_5_2_PRO})
LOW_REASONING_EFFORTS = frozenset({"minimal", "low"})
MINIMUM_PRO_REASONING_EFFORT = "medium"

#: Anthropic models that reject the `temperature` parameter and the legacy
#: thinking={"type": "enabled", "budget_tokens": N} shape, taking thinking={"type": "adaptive"}
#: instead. An explicit set rather than a version comparison because the model IDs do not sort --
#: "claude-fable-5" carries no version number at all.
ADAPTIVE_THINKING_MODELS = frozenset(
    {
        ANTHROPICModel.CLAUDE_OPUS_5,
        ANTHROPICModel.CLAUDE_SONNET_5,
        ANTHROPICModel.CLAUDE_FABLE_5,
        ANTHROPICModel.CLAUDE_OPUS_4_8,
        ANTHROPICModel.CLAUDE_OPUS_4_7,
    }
)

#: Anthropic models whose thinking cannot be switched off: thinking={"type": "disabled"} returns 400.
ALWAYS_THINKING_ANTHROPIC_MODELS = frozenset({ANTHROPICModel.CLAUDE_FABLE_5})

#: Google models whose thinking cannot be switched off. The Gemini API rejects
#: thinkingConfig.thinkingBudget=0 on these. The two floating aliases are listed because they
#: currently resolve to the 3.6 family.
ALWAYS_THINKING_GOOGLE_MODELS = frozenset(
    {
        GOOGLEModel.GEMINI_3_6_FLASH,
        GOOGLEModel.GEMINI_FLASH_LATEST,
        GOOGLEModel.GEMINI_FLASH_LITE_LATEST,
    }
)

#: Adaptive-thinking models count thinking tokens against max_tokens, and Claude Opus 5 thinks by
#: default, so the 4096 fallback used for older models truncates noticeably sooner on them.
DEFAULT_MAX_TOKENS = 4096
DEFAULT_ADAPTIVE_THINKING_MAX_TOKENS = 8192


def resolve_reasoning_effort(model_name: str | None, reasoning_effort: str | None) -> Optional[str]:
    """Clamp `reasoning_effort` up to the lowest level the given model accepts.

    Takes a plain string rather than an ``OPENAIModel`` because the same rule applies to
    ``CustomLLMConfig``, whose model name is free-form. Returns the effort unchanged for every model
    that accepts the full range.
    """
    if not reasoning_effort or not model_name:
        return reasoning_effort
    if (
        model_name.lower() in MODELS_WITHOUT_LOW_REASONING_EFFORT
        and reasoning_effort.lower() in LOW_REASONING_EFFORTS
    ):
        return MINIMUM_PRO_REASONING_EFFORT
    return reasoning_effort


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
    default_headers: Optional[dict] = Field(
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
    api_key: Optional[str] = Field(
        default=None,
        description=(
            "Amazon Bedrock long-term API key (bearer token). If set, it is used for authentication "
            "and the access-key fields below are ignored. Leave empty to authenticate with an "
            "access-key pair or the default AWS credential chain (IAM role)."
        ),
        title="Bedrock API Key",
    )
    model: Optional[BEDROCKModel] = Field(
        # Cheap/fast tier; routes conditional edges reliably in live tests.
        default=BEDROCKModel.GLM_4_7_FLASH,
        description="Name of the Amazon Bedrock model to use",
        title="Bedrock Model",
    )
    type: Literal["bedrock_llm"] = Field(
        default="bedrock_llm",
        description=(
            "Differentiator field that helps in identifying this particular type of config when "
            "serializing and deserializing"
        ),
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.BEDROCK,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    region: Optional[str] = Field(
        default=None,
        description="AWS region the Bedrock model is invoked in. Defaults to us-east-1 if not provided.",
        title="AWS Region",
    )
    aws_access_key_id: Optional[str] = Field(
        default=None,
        description=(
            "AWS access key ID for Bedrock. Leave empty to use the platform default "
            "(`BEDROCK_ACCESS_KEY` env var, then the AWS credential chain)."
        ),
        title="AWS Access Key ID",
    )
    aws_secret_access_key: Optional[str] = Field(
        default=None,
        description=(
            "AWS secret access key for Bedrock. Leave empty to use the platform default "
            "(`BEDROCK_SECRET_KEY` env var, then the AWS credential chain)."
        ),
        title="AWS Secret Access Key",
    )

    @field_serializer("api_key")
    def serialize_api_key(self, value: Optional[str]) -> Optional[str]:  # type: ignore[override]
        """Pass the Bedrock key through unchanged.

        DELIBERATE DIVERGENCE FROM UPSTREAM, and the only one in this file that changes behaviour.
        `BaseLLMConfig.api_key` is a `SecretStr` and its serializer calls `.get_secret_value()`, but
        this subclass overrides `api_key` with a plain `str` (matching the server's field type).
        Pydantic still applies the inherited serializer, so `model_dump()` on a Bedrock config that
        actually has a key raises `PydanticSerializationError: 'str' object has no attribute
        'get_secret_value'`. Verified against upstream's exact class structure — the defect is
        inherited from the design, not from transcription.

        Mirroring that faithfully would mean the SDK cannot serialize a valid Bedrock config, which
        is its core job, so the mirror overrides the serializer instead. The stored shape is
        unchanged; only the crash goes away.

        No aws_* serializer is needed: those are plain `str` upstream too, and the base class
        declares no serializer for them.
        """
        return value

    model_config = ConfigDict(title="Bedrock")


class WorkflowDefaultLLMConfig(BaseLLMConfig):
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
    WorkflowDefaultLLMConfig,
    NoLLMConfig,
]

LLMConfig = Annotated[LLMConfigUnion, Field(discriminator="type")]
