"""LLM configuration models — stripped of all server-side dependencies."""

from enum import Enum
from typing import Annotated, Any, Dict, FrozenSet, Literal, Optional, Union
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, field_serializer, field_validator

from interactly_configs.auth import IntegrationAuthConfig
from interactly_configs.gemini_models import GeminiThinkingLevel


class LLMProvider(str, Enum):
    DEFAULTPROVIDER = "default_provider"
    AZUREOPENAI = "azure_openai"
    OPENAI = "openai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    XAI = "xai"
    GEMMA = "gemma"
    GLM = "glm"
    DEEPSEEK = "deepseek"
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
    # GPT 5.6 tiers, newest first. Served only by the Responses API -- Chat Completions rejects a
    # tool-bearing request for this family outright, which the server handles by routing every
    # "gpt-5*" model there.
    GPT_5_6_SOL = "gpt-5.6-sol"
    GPT_5_6_TERRA = "gpt-5.6-terra"
    GPT_5_6_LUNA = "gpt-5.6-luna"

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

    # REMOVED 2026-09-01: gpt-5.2-chat-latest and gpt-5.3-chat-latest return
    # "404 Model not found" on every call (verified live), joining gpt-5-chat-latest and
    # gpt-5.1-chat-latest, which were already retired. The whole "-chat-latest" alias family is
    # gone, so no GPT-5 chat-optimized model is selectable any more.

    # GPT 4 Models
    GPT_4_1_NANO = "gpt-4.1-nano"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1 = "gpt-4.1"
    # DEPRECATED: OpenAI shuts down gpt-4, gpt-4o and gpt-4o-mini on 2026-10-23.
    # Still callable today; kept only so stored workflows keep deserialising.
    GPT_4 = "gpt-4"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"

    # Audio-in/audio-out on the Chat Completions API (text+audio in, text+audio out; 128K context,
    # streaming + function calling). Successor to the shut-down gpt-4o-audio-preview.
    GPT_AUDIO_1_5 = "gpt-audio-1.5"
    # The cheaper sibling: same input shape (text + wav/mp3 audio, no images), same Chat Completions path.
    GPT_AUDIO_MINI = "gpt-audio-mini"

    # GPT 3.5 Models
    # DEPRECATED: shuts down 2026-10-23. See note above.
    GPT_3_5_TURBO = "gpt-3.5-turbo"


class GOOGLEModel(str, Enum):
    # Floating models that point to the latest stable versions
    GEMINI_FLASH_LATEST = "gemini-flash-latest"
    GEMINI_FLASH_LITE_LATEST = "gemini-flash-lite-latest"

    GEMINI_3_8_FLASH = "gemini-3.8-flash"
    GEMINI_3_7_FLASH = "gemini-3.7-flash"
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


class AnthropicBackend(str, Enum):
    """Which endpoint serves an Anthropic model."""

    # The same Claude models are reachable two ways, and the choice is an auth/billing decision
    # rather than a model one. DIRECT calls api.anthropic.com with an Anthropic API key; VERTEX
    # calls Google Vertex AI Model Garden with the platform's Google Cloud credentials and bills
    # the Google Cloud project.
    #
    # DIRECT is the default, so a config that does not mention a backend keeps calling
    # api.anthropic.com. Choosing VERTEX restricts the model to vertex_selectable_anthropic_models();
    # anything else is rejected by the server rather than silently redirected.
    DIRECT = "direct"
    VERTEX = "vertex"


class GoogleBackend(str, Enum):
    """Which endpoint serves a Google model.

    Left unset, the server keeps its original rule: a team-scoped Gemini key means the public
    Gemini API, and its absence means Vertex. That rule cannot express "Vertex regardless", because
    the team's key is stamped onto the config before the runtime ever sees it — so a configuration
    that deliberately wants Vertex silently gets AI Studio instead, on the team's key and the team's
    bill. Naming the backend is how a config says which one it meant.
    """

    AI_STUDIO = "ai_studio"
    VERTEX = "vertex"


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

    CLAUDE_SONNET_4_6 = "claude-sonnet-4-6"
    CLAUDE_SONNET_4_5_20250929 = "claude-sonnet-4-5-20250929"

    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"
    # Superseded by the CLAUDE_HAIKU_4_5 alias above; retained so stored configs
    # keep deserialising. Both resolve to the same model.
    CLAUDE_HAIKU_4_5_20251001 = "claude-haiku-4-5-20251001"
    # REMOVED 2026-07-30: claude-opus-4-20250514 and claude-sonnet-4-20250514 are
    # retired and return 404 on every call.
    #
    # REMOVED 2026-09-01: claude-opus-4-1-20250805 passed its 2026-08-05 retirement and now
    # returns 404 from api.anthropic.com on every call (verified live). It is still served on
    # Vertex AI, which retires on Google's own schedule, but a model that answers on only one
    # backend is not worth keeping selectable.


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


# The four providers below are served through Google Vertex AI and authenticate with the platform's
# Google Cloud credentials: there is no provider API key, and usage is billed to the Google Cloud
# project. Each stores the bare model id a human recognises; the server prepends the Vertex publisher
# prefix ("xai/", "google/", "zai-org/", "deepseek-ai/"). Mind the dash/dot trap these publishers
# share: `glm-5-2` and `deepseek-v3-2` are self-deploy cards that 404 here, while `glm-5.2-maas` and
# `deepseek-v3.2-maas` are the serverless models. All four are served ONLY by Vertex's global endpoint
# (see the `*_VERTEX_GLOBAL_ONLY` flags below).


class XAIModel(str, Enum):
    # xAI's Grok. Every id live-verified on the global endpoint on 2026-09-02. The version numbers do
    # not sort as decimals: 4.20 is a later release than 4.3, and 4.6 later still.
    GROK_4_6 = "grok-4.6"
    GROK_4_3 = "grok-4.3"

    # The 4.20 and 4.1-fast lines ship as explicit reasoning / non-reasoning pairs rather than taking
    # a reasoning switch. The "-non-reasoning" variants return reasoning_tokens=0, which makes them the
    # cheaper, lower-latency choice -- and a better fit for voice nodes, where the reasoning variants'
    # extra tokens are latency the caller hears as silence.
    GROK_4_20_REASONING = "grok-4.20-reasoning"
    GROK_4_20_NON_REASONING = "grok-4.20-non-reasoning"
    GROK_4_1_FAST_REASONING = "grok-4.1-fast-reasoning"
    GROK_4_1_FAST_NON_REASONING = "grok-4.1-fast-non-reasoning"


class GemmaModel(str, Enum):
    # Google's Gemma, an open-weights family, as a fully managed serverless ("MaaS") API. The "-maas"
    # suffix marks the serverless offering; every other plausible Gemma variant returned 404 when
    # probed on 2026-09-02.
    GEMMA_4_26B_A4B_IT_MAAS = "gemma-4-26b-a4b-it-maas"


class GLMModel(str, Enum):
    # Z.ai's GLM as a fully managed serverless ("MaaS") API. The same family is also reachable through
    # Amazon Bedrock (`BEDROCKModel.GLM_*`); the two routes are independent. All three ids
    # live-verified on the global endpoint on 2026-09-02.
    GLM_5_2_MAAS = "glm-5.2-maas"
    GLM_5_MAAS = "glm-5-maas"
    GLM_4_7_MAAS = "glm-4.7-maas"


class DeepSeekModel(str, Enum):
    # DeepSeek as a fully managed serverless ("MaaS") API, roughly an order of magnitude cheaper than
    # the frontier models. Only this id is live-usable: deepseek-v3.1-maas 404s, and
    # deepseek-r1-0528-maas serves only regionally and writes its reasoning as literal
    # "<think>...</think>" into the answer, which a voice node would read aloud.
    DEEPSEEK_V3_2_MAAS = "deepseek-v3.2-maas"


# --------------------------------------------------------------------------------------------- #
# Model capability data                                                                           #
# --------------------------------------------------------------------------------------------- #
# Upstream carries these INSIDE the enum bodies, wrapped in `enum.nonmember(...)` so they stay
# capability data instead of becoming selectable members. `enum.nonmember` is Python 3.11+, and this
# package supports 3.10 (see `requires-python`), so the mirror hoists them to module scope instead —
# the only mechanism available that keeps them out of the enums' member lists on 3.10. The values are
# upstream's. The names are too, except where hoisting would make them ambiguous at module scope:
# those carry the provider (`ALWAYS_THINKING_GOOGLE_MODELS` for `GOOGLEModel.ALWAYS_THINKING_MODELS`),
# and each says which upstream attribute it mirrors.
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

#: OpenAI models that accept audio input. Audio is served on the Chat Completions API only, and only
#: wav/mp3 are valid input formats. Upstream: `OPENAIModel.AUDIO_INPUT_MODELS`.
AUDIO_INPUT_OPENAI_MODELS = frozenset({OPENAIModel.GPT_AUDIO_1_5, OPENAIModel.GPT_AUDIO_MINI})

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

#: Anthropic models callable through Google Vertex AI Model Garden. Live-verified (region "global")
#: on 2026-09-01. Deliberately absent: claude-haiku-4-5 (and its dated form) and
#: claude-opus-4-5-20251101 return 404 in every id form; claude-fable-5 returns 403 until data sharing
#: is enabled for publisher "anthropic". Upstream: `ANTHROPICModel.VERTEX_SUPPORTED_MODELS`.
#:
#: A model outside this set is still usable on the default DIRECT backend -- this constrains only
#: the Vertex path, where the server rejects an unavailable model rather than silently redirecting.
VERTEX_SUPPORTED_ANTHROPIC_MODELS = frozenset(
    {
        ANTHROPICModel.CLAUDE_OPUS_5,
        ANTHROPICModel.CLAUDE_SONNET_5,
        ANTHROPICModel.CLAUDE_OPUS_4_8,
        ANTHROPICModel.CLAUDE_OPUS_4_7,
        ANTHROPICModel.CLAUDE_OPUS_4_6,
        ANTHROPICModel.CLAUDE_SONNET_4_6,
        ANTHROPICModel.CLAUDE_SONNET_4_5_20250929,
    }
)

#: Anthropic models withheld from the Vertex backend by cost policy rather than by availability:
#: claude-opus-5 since 2026-09-04. Upstream: `ANTHROPICModel.VERTEX_DISABLED_MODELS`.
VERTEX_DISABLED_ANTHROPIC_MODELS = frozenset({ANTHROPICModel.CLAUDE_OPUS_5})

#: Google models whose thinking cannot be switched off. The Gemini API rejects
#: thinkingConfig.thinkingBudget=0 on these. The two floating aliases are listed because they
#: currently resolve to the 3.6 family. Upstream: `GOOGLEModel.ALWAYS_THINKING_MODELS`.
ALWAYS_THINKING_GOOGLE_MODELS = frozenset(
    {
        GOOGLEModel.GEMINI_3_8_FLASH,
        GOOGLEModel.GEMINI_3_7_FLASH,
        GOOGLEModel.GEMINI_3_6_FLASH,
        GOOGLEModel.GEMINI_FLASH_LATEST,
        GOOGLEModel.GEMINI_FLASH_LITE_LATEST,
        GOOGLEModel.GEMINI_3_1_PRO_PREVIEW,
    }
)

#: Google models that reject a request ending on a model turn ("400 Requests ending with a model turn
#: are not supported"): 3.6 Flash, 3.5 Flash-Lite and every later model. Earlier 3.x and 2.5 still
#: accept it. The aliases resolve to 3.6. Upstream: `GOOGLEModel.REJECTS_TRAILING_MODEL_TURN_MODELS`.
REJECTS_TRAILING_MODEL_TURN_GOOGLE_MODELS = frozenset(
    {
        GOOGLEModel.GEMINI_3_8_FLASH,
        GOOGLEModel.GEMINI_3_7_FLASH,
        GOOGLEModel.GEMINI_3_6_FLASH,
        GOOGLEModel.GEMINI_3_5_FLASH_LITE,
        GOOGLEModel.GEMINI_FLASH_LATEST,
        GOOGLEModel.GEMINI_FLASH_LITE_LATEST,
    }
)

#: Bedrock models that take images; the rest of the catalogue returns 400 on one.
#: Upstream: `BEDROCKModel.VISION_MODELS`.
VISION_BEDROCK_MODELS = frozenset({BEDROCKModel.QWEN3_VL_235B})

#: The four Vertex-served providers answer only on Vertex's global endpoint: a pinned region returns
#: 400 FAILED_PRECONDITION, so the server rejects a non-global `vertex_location` up front.
#: Upstream: `VERTEX_GLOBAL_ONLY` on each of `XAIModel`, `GemmaModel`, `GLMModel`, `DeepSeekModel`.
XAI_VERTEX_GLOBAL_ONLY = True
GEMMA_VERTEX_GLOBAL_ONLY = True
GLM_VERTEX_GLOBAL_ONLY = True
DEEPSEEK_VERTEX_GLOBAL_ONLY = True

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


def vertex_selectable_anthropic_models() -> FrozenSet[ANTHROPICModel]:
    """What an `AnthropicLLMConfig` on the Vertex backend may name: carried by Model Garden, and not
    withheld. Upstream: `ANTHROPICModel.vertex_selectable_models()`."""
    return VERTEX_SUPPORTED_ANTHROPIC_MODELS - VERTEX_DISABLED_ANTHROPIC_MODELS


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
        description=(
            "API key to access the LLM provider endpoint. Admins can see the stored key; for every other "
            "role it is stored securely and never shown back, and leaving it blank keeps the existing key "
            "in use. Because an admin is shown the real key, an admin who clears this field removes the "
            "stored key."
        ),
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
    def serialize_api_key(self, value: Union[SecretStr, str, None]) -> Optional[str]:
        """Unmask ``api_key`` on the way out, whatever concrete type the subclass declared.

        Pydantic applies an inherited field serializer to a field a subclass has REDECLARED, using the
        subclass's type. ``BedrockLLMConfig`` narrows ``api_key`` to a plain ``str`` (a Bedrock bearer
        token, alongside its other plain-string AWS credentials), so a serializer that assumed
        ``SecretStr`` unconditionally raised on it:

            PydanticSerializationError: Error calling function `serialize_api_key`:
            AttributeError: 'str' object has no attribute 'get_secret_value'

        That fired on any ``model_dump()`` / ``model_dump_json()`` of a Bedrock config that actually
        had a key set — i.e. persisting one, returning one from the API, or checkpointing a run using
        one. A config with no key serialized fine, which is why it was easy to miss.

        Handled here rather than by overriding in the subclass so the base is correct for any future
        subclass that narrows the field the same way, and handled here rather than by widening
        ``BedrockLLMConfig.api_key`` to ``SecretStr`` because the Bedrock runtime passes the value
        straight through to langchain as ``bedrock_api_key`` (``runtime/llm.py``), where a ``SecretStr``
        is not what the client expects.
        """
        if value is None:
            return None
        if isinstance(value, SecretStr):
            return value.get_secret_value()  # Returns the unmasked value
        return value


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
    thinking_level: Optional[GeminiThinkingLevel] = Field(
        default=None,
        description=(
            "How hard the model should think, for the Gemini 3 models that take a level instead of a "
            "thinking budget in number of tokens"
        ),
        title="Thinking Level",
    )
    backend: Optional[GoogleBackend] = Field(
        default=None,
        description=(
            "Which endpoint serves this model. Left unset, a team-scoped Gemini key selects the "
            "public Gemini API and its absence selects Vertex AI. Set it to pin one regardless: "
            "'vertex' also stops the team's key being applied, so the call authenticates with the "
            "platform's Google Cloud credentials and bills there."
        ),
        title="Google Backend",
    )

    @field_validator("thinking_level", mode="before")
    @classmethod
    def _accept_any_casing_of_thinking_level(cls, value: Any) -> Any:
        """Uppercase a string level before the enum sees it.

        Configs stored while the field was free-form text say "high" at least as often as "HIGH", and
        rejecting those would turn a working config into a validation error on load.
        """
        return value.upper() if isinstance(value, str) else value

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
    backend: AnthropicBackend = Field(
        default=AnthropicBackend.DIRECT,
        description=(
            "Where the Claude model is served from. 'direct' (the default) calls api.anthropic.com "
            "with an Anthropic API key. 'vertex' calls Google Vertex AI Model Garden using the "
            "platform's Google Cloud credentials -- no Anthropic key is needed, and the usage is "
            "billed to the Google Cloud project rather than to Anthropic. The model choices are the "
            "same either way, though a few models are not available on Vertex."
        ),
        title="Anthropic Backend",
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description=(
            "Google Cloud project that serves the model when the backend is 'vertex'. Leave blank to use "
            "the platform default (`GCP_VERTEX_PROJECT` env var)."
        ),
        title="Vertex Project ID",
    )
    vertex_location: Optional[str] = Field(
        default=None,
        description=(
            "Vertex region used when the backend is 'vertex'. Leave blank for the platform default "
            "(`GCP_VERTEX_LOCATION`, itself defaulting to 'global'). The global endpoint is supported by "
            "every Anthropic model in Model Garden; a pinned region (e.g. 'us-east5') restricts inference "
            "geography but is not offered for every model."
        ),
        title="Vertex Location",
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
    integration_auth: Optional[IntegrationAuthConfig] = Field(
        default=None,
        description=(
            "Integration-backed authentication configuration for bearer-token injection. "
            "Point it at any integration that issues OAuth2 client-credentials tokens. "
            "When set, the runtime resolves credentials using the following chain: "
            "(1) explicit ``api_key`` on the request, "
            "(2) team-level ``custom_llm_api_key`` from vendor credentials, "
            "(3) bearer token fetched via this ``integration_id`` from vendor credentials. "
            "Ignored when ``api_key`` or a bearer Authorization header is already resolved."
        ),
        title="Integration Auth",
        # "okta_auth" was the original field name; accepted so previously saved
        # workflow configs keep deserializing.
        validation_alias=AliasChoices("integration_auth", "okta_auth"),
    )
    use_responses_api: bool = Field(
        default=False,
        description="Whether to use the GPT 5.x+ style Responses API instead of Chat Completions API.",
        title="Use Responses API",
    )
    supports_audio_input: bool = Field(
        default=False,
        description=(
            "Whether the model behind this gateway accepts audio input. Off by default: audio sent to a model "
            "that cannot take it fails the request. Chat Completions only; ignored with use_responses_api."
        ),
        title="Supports Audio Input",
    )

    model_config = ConfigDict(title="Custom LLM", populate_by_name=True)


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

    # No serializer override here: `BaseLLMConfig.serialize_api_key` handles both `SecretStr` and
    # plain `str`, matching upstream after interactly-ai@e2885fac1. No aws_* serializer is needed
    # either -- those are plain `str` upstream too, and the base declares no serializer for them.

    model_config = ConfigDict(title="Bedrock")


_VERTEX_PROJECT_DESCRIPTION = (
    "Google Cloud project that serves the model. Leave blank to use the platform default "
    "(`GCP_VERTEX_PROJECT` env var)."
)


class XAILLMConfig(BaseLLMConfig):
    """xAI's Grok, served through Google Vertex AI Model Garden.

    Authentication is the platform's Google Cloud service account -- there is no xAI API key
    involved, and the usage is billed to the Google Cloud project.
    """

    model: Optional[XAIModel] = Field(
        default=XAIModel.GROK_4_6,
        description="Name of the xAI Grok model to use",
        title="Grok Model",
    )
    type: Literal["xai_llm"] = Field(
        default="xai_llm",
        description="Differentiator field that helps in identifying this particular type of config when serializing and deserializing",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.XAI,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description=_VERTEX_PROJECT_DESCRIPTION,
        title="Vertex Project ID",
    )
    vertex_location: Optional[str] = Field(
        default=None,
        description=(
            "Vertex region that serves the model. Grok is served only by Vertex's global endpoint, "
            "so this should be left blank (or set to 'global'); any other region is rejected."
        ),
        title="Vertex Location",
    )

    model_config = ConfigDict(title="Grok (xAI)")


class GemmaLLMConfig(BaseLLMConfig):
    """Google's Gemma, served by Vertex AI as a fully managed serverless API.

    There is no Gemma API key -- usage is billed to the Google Cloud project.
    """

    model: Optional[GemmaModel] = Field(
        default=GemmaModel.GEMMA_4_26B_A4B_IT_MAAS,
        description="Name of the Gemma model to use",
        title="Gemma Model",
    )
    type: Literal["gemma_llm"] = Field(
        default="gemma_llm",
        description="Differentiator field that helps in identifying this particular type of config when serializing and deserializing",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.GEMMA,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    enable_thinking: bool = Field(
        default=False,
        description=(
            "Whether Gemma should reason step by step before answering. Off by default: thinking "
            "is billed as output tokens and adds noticeable latency -- a live comparison measured "
            "13 output tokens with it off against 198 with it on for the same question -- which on "
            "a voice call the caller hears as silence. Turn it on for nodes that do harder "
            "reasoning and are not latency-sensitive. The reasoning itself is returned separately "
            "and never appears in the spoken or displayed answer."
        ),
        title="Enable Thinking",
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description=_VERTEX_PROJECT_DESCRIPTION,
        title="Vertex Project ID",
    )
    vertex_location: Optional[str] = Field(
        default=None,
        description=(
            "Vertex region that serves the model. Gemma is served only by Vertex's global "
            "endpoint, so this should be left blank (or set to 'global'); any other region is "
            "rejected."
        ),
        title="Vertex Location",
    )

    model_config = ConfigDict(title="Gemma (Google)")


class GLMLLMConfig(BaseLLMConfig):
    """Z.ai's GLM, served by Vertex AI as a fully managed serverless API.

    There is no Z.ai API key -- usage is billed to the Google Cloud project.
    """

    model: Optional[GLMModel] = Field(
        default=GLMModel.GLM_5_2_MAAS,
        description="Name of the GLM model to use",
        title="GLM Model",
    )
    type: Literal["glm_llm"] = Field(
        default="glm_llm",
        description="Differentiator field that helps in identifying this particular type of config when serializing and deserializing",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.GLM,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    enable_thinking: bool = Field(
        default=False,
        description=(
            "Whether GLM should reason step by step before answering. Off by default, which is a "
            "change from the model's own behaviour and deliberate: with thinking on, GLM spends "
            "its whole output budget reasoning before it writes anything, so a node with a modest "
            "Max Tokens returns an empty answer (measured empty at both 64 and 256 tokens). "
            "Thinking also costs roughly 17x the output tokens on a simple question, which on a "
            "voice call the caller hears as silence. Turn it on for harder reasoning, together "
            "with a Max Tokens of at least ~1000. The reasoning itself is returned separately and "
            "never appears in the spoken or displayed answer."
        ),
        title="Enable Thinking",
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description=_VERTEX_PROJECT_DESCRIPTION,
        title="Vertex Project ID",
    )
    vertex_location: Optional[str] = Field(
        default=None,
        description=(
            "Vertex region that serves the model. GLM is served only by Vertex's global endpoint, "
            "so this should be left blank (or set to 'global'); any other region is rejected."
        ),
        title="Vertex Location",
    )

    model_config = ConfigDict(title="GLM (Z.ai)")


class DeepSeekLLMConfig(BaseLLMConfig):
    """DeepSeek, served by Vertex AI as a fully managed serverless API.

    There is no DeepSeek API key -- usage is billed to the Google Cloud project.
    """

    model: Optional[DeepSeekModel] = Field(
        default=DeepSeekModel.DEEPSEEK_V3_2_MAAS,
        description=(
            "Name of the DeepSeek model to use. Note DeepSeek routes conditional edges much less "
            "reliably than the other providers here: measured over five runs it called the "
            "navigation tool 1/5 times when the tool's required argument was not already stated in "
            "the conversation, and 3-4/5 when it was, where Grok, Gemma, Claude and GPT all route "
            "first time. It prefers to answer in text and ask a clarifying question instead. Good "
            "for say and worker nodes; prefer another provider for conditional edges, or make sure "
            "the edge tool needs no argument the caller has not already given."
        ),
        title="DeepSeek Model",
    )
    type: Literal["deepseek_llm"] = Field(
        default="deepseek_llm",
        description="Differentiator field that helps in identifying this particular type of config when serializing and deserializing",
    )
    provider: Optional[LLMProvider] = Field(
        default=LLMProvider.DEEPSEEK,
        description="The selected Large Language Model provider from the available options.",
        title="LLM Provider",
    )
    enable_thinking: bool = Field(
        default=False,
        description=(
            "Whether DeepSeek should reason step by step before answering. Off by default, which "
            "is also the model's own default. Thinking costs roughly 13x the output tokens on a "
            "simple question, which on a voice call the caller hears as silence, and it needs room "
            "to work: with thinking on and a Max Tokens of 64 the answer comes back empty, so "
            "allow at least a few hundred. The reasoning itself is returned separately and never "
            "appears in the spoken or displayed answer."
        ),
        title="Enable Thinking",
    )
    vertex_project: Optional[str] = Field(
        default=None,
        description=_VERTEX_PROJECT_DESCRIPTION,
        title="Vertex Project ID",
    )
    vertex_location: Optional[str] = Field(
        default=None,
        description=(
            "Vertex region that serves the model. DeepSeek is served only by Vertex's global "
            "endpoint, so this should be left blank (or set to 'global'); any other region is "
            "rejected."
        ),
        title="Vertex Location",
    )

    model_config = ConfigDict(title="DeepSeek")


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
    XAILLMConfig,
    GemmaLLMConfig,
    GLMLLMConfig,
    DeepSeekLLMConfig,
    CustomLLMConfig,
    WorkflowDefaultLLMConfig,
    NoLLMConfig,
]

LLMConfig = Annotated[LLMConfigUnion, Field(discriminator="type")]
