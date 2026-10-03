"""The LLM catalogue: the Vertex-served providers, backend selection, thinking levels, capability data.

The regression these guard against is concrete. Before these models were mirrored, a workflow whose
node used Grok, Gemma, GLM, DeepSeek or a Gemini 3.7/3.8 model hydrated that node as
`UnknownNodeConfig`, losing every typed field, and an Anthropic config with `backend="vertex"` parsed
but silently dropped the backend, so reading a config and writing it back changed where it ran.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

import interactly_configs as ic

_LLM = TypeAdapter(ic.LLMConfig)

_VERTEX_PROVIDERS = [
    (ic.XAILLMConfig, "xai_llm", ic.LLMProvider.XAI, ic.XAIModel.GROK_4_6),
    (ic.GemmaLLMConfig, "gemma_llm", ic.LLMProvider.GEMMA, ic.GemmaModel.GEMMA_4_26B_A4B_IT_MAAS),
    (ic.GLMLLMConfig, "glm_llm", ic.LLMProvider.GLM, ic.GLMModel.GLM_5_2_MAAS),
    (ic.DeepSeekLLMConfig, "deepseek_llm", ic.LLMProvider.DEEPSEEK, ic.DeepSeekModel.DEEPSEEK_V3_2_MAAS),
]


def _hydrate_say_node(llms_config: dict):
    hydrated = ic.WorkflowConfigFullyHydrated.model_validate(
        {"node_configs": [{"type": "say_llm", "name": "n", "llms_config": llms_config}]}
    )
    return hydrated.node_configs[0]


class TestVertexProviders:
    @pytest.mark.parametrize("config_cls, type_tag, provider, default_model", _VERTEX_PROVIDERS)
    def test_the_discriminator_selects_the_provider_config(self, config_cls, type_tag, provider, default_model):
        # Arrange / Act
        parsed = _LLM.validate_python({"type": type_tag})
        # Assert
        assert isinstance(parsed, config_cls)
        assert parsed.provider == provider
        assert parsed.model == default_model

    @pytest.mark.parametrize("config_cls, type_tag, _provider, _model", _VERTEX_PROVIDERS)
    def test_vertex_settings_survive_a_round_trip(self, config_cls, type_tag, _provider, _model):
        original = config_cls(vertex_project="my-project", vertex_location="global")
        restored = _LLM.validate_python(original.model_dump(mode="json"))
        assert (restored.vertex_project, restored.vertex_location) == ("my-project", "global")

    @pytest.mark.parametrize("config_cls", [ic.GemmaLLMConfig, ic.GLMLLMConfig, ic.DeepSeekLLMConfig])
    def test_thinking_is_off_unless_asked_for(self, config_cls):
        # Thinking on a voice node is latency the caller hears as silence, so the default is off.
        assert config_cls().enable_thinking is False

    def test_grok_has_no_thinking_switch(self):
        # Grok ships reasoning and non-reasoning as separate model ids instead.
        assert "enable_thinking" not in ic.XAILLMConfig.model_fields

    def test_an_unknown_model_id_is_rejected(self):
        with pytest.raises(ValidationError):
            _LLM.validate_python({"type": "glm_llm", "model": "glm-5-2"})  # self-deploy card, not MaaS

    def test_every_vertex_provider_is_global_only(self):
        assert all(
            (ic.XAI_VERTEX_GLOBAL_ONLY, ic.GEMMA_VERTEX_GLOBAL_ONLY, ic.GLM_VERTEX_GLOBAL_ONLY, ic.DEEPSEEK_VERTEX_GLOBAL_ONLY)
        )


class TestHydratedWorkflowsKeepTheirTypes:
    def test_a_grok_node_hydrates_as_a_typed_say_node(self):
        node = _hydrate_say_node({"type": "xai_llm", "model": "grok-4.6"})
        assert isinstance(node, ic.SayLLMNodeConfig)
        assert isinstance(node.llms_config, ic.XAILLMConfig)

    def test_a_gemini_3_8_node_hydrates_as_a_typed_say_node(self):
        node = _hydrate_say_node({"type": "google_llm", "model": "gemini-3.8-flash"})
        assert isinstance(node, ic.SayLLMNodeConfig)
        assert node.llms_config.model == ic.GOOGLEModel.GEMINI_3_8_FLASH

    def test_an_anthropic_vertex_backend_survives_read_then_write(self):
        # Arrange: what a GET returns for a node on the Vertex backend.
        node = _hydrate_say_node({"type": "anthropic_llm", "model": "claude-sonnet-4-6", "backend": "vertex"})
        # Act: what an SDK user sends back on update.
        written = node.model_dump(mode="json")
        # Assert
        assert written["llms_config"]["backend"] == "vertex"


class TestGoogleThinkingLevel:
    @pytest.mark.parametrize("given", ["high", "High", "HIGH", ic.GeminiThinkingLevel.HIGH])
    def test_any_casing_is_accepted(self, given):
        assert ic.GoogleLLMConfig(thinking_level=given).thinking_level is ic.GeminiThinkingLevel.HIGH

    def test_unset_by_default(self):
        assert ic.GoogleLLMConfig().thinking_level is None

    def test_an_unknown_level_is_rejected(self):
        with pytest.raises(ValidationError):
            ic.GoogleLLMConfig(thinking_level="extreme")

    def test_levels_are_declared_in_ascending_effort(self):
        assert [level.value for level in ic.GeminiThinkingLevel] == ["MINIMAL", "LOW", "MEDIUM", "HIGH"]


class TestBackends:
    def test_google_backend_is_unset_by_default(self):
        # Unset keeps the server's own rule (team key -> AI Studio, else Vertex). Not "vertex".
        assert ic.GoogleLLMConfig().backend is None

    def test_google_backend_can_be_pinned(self):
        assert ic.GoogleLLMConfig(backend="vertex").backend is ic.GoogleBackend.VERTEX

    def test_anthropic_backend_defaults_to_direct(self):
        assert ic.AnthropicLLMConfig().backend is ic.AnthropicBackend.DIRECT

    def test_vertex_selectable_models_exclude_the_withheld_and_the_unavailable(self):
        selectable = ic.vertex_selectable_anthropic_models()
        assert ic.ANTHROPICModel.CLAUDE_OPUS_5 not in selectable  # withheld by cost policy
        assert ic.ANTHROPICModel.CLAUDE_FABLE_5 not in selectable  # not carried by Model Garden
        assert ic.ANTHROPICModel.CLAUDE_SONNET_4_6 in selectable
        assert selectable <= ic.VERTEX_SUPPORTED_ANTHROPIC_MODELS


class TestCapabilityData:
    @pytest.mark.parametrize(
        "capability, enum_cls",
        [
            (ic.AUDIO_INPUT_OPENAI_MODELS, ic.OPENAIModel),
            (ic.ALWAYS_THINKING_GOOGLE_MODELS, ic.GOOGLEModel),
            (ic.REJECTS_TRAILING_MODEL_TURN_GOOGLE_MODELS, ic.GOOGLEModel),
            (ic.VISION_BEDROCK_MODELS, ic.BEDROCKModel),
            (ic.VERTEX_SUPPORTED_ANTHROPIC_MODELS, ic.ANTHROPICModel),
            (ic.VERTEX_DISABLED_ANTHROPIC_MODELS, ic.ANTHROPICModel),
        ],
    )
    def test_every_capability_set_names_only_real_models(self, capability, enum_cls):
        assert capability and capability <= set(enum_cls)

    def test_new_gemini_models_cannot_switch_thinking_off(self):
        assert {ic.GOOGLEModel.GEMINI_3_7_FLASH, ic.GOOGLEModel.GEMINI_3_8_FLASH} <= ic.ALWAYS_THINKING_GOOGLE_MODELS

    def test_custom_gateways_do_not_assume_audio_support(self):
        assert ic.CustomLLMConfig().supports_audio_input is False
