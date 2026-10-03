"""Tools, edges, nodes and workflow: the codebase-function tool, media results, companion lifetime,
voice persona, and the defaults the JSON Schema publishes.

Two regressions are pinned here because both were silent. A workflow with a codebase-function tool node
hydrated that node as `UnknownNodeConfig`, losing every typed field. And `result_as_media` parsed but was
dropped, so reading a tool and writing it back turned a media result into a parsed one.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

import interactly_configs as ic
from interactly_configs.tool import (
    clear_codebase_function_arguments,
    register_codebase_function_arguments,
)
from interactly_configs.utils import derive_dynamic_variables, extract_dynamic_variables
from interactly_configs.workflow_copilot import WorkflowCopilotCommand

_TOOL = TypeAdapter(ic.ToolConfig)


def _binding(name: str) -> dict:
    return {"argument_name": name, "variable_path": f"{name}_var"}


@pytest.fixture
def no_registered_signatures():
    clear_codebase_function_arguments()
    yield
    clear_codebase_function_arguments()


class TestCodebaseFunctionTool:
    def test_the_discriminator_selects_it(self):
        parsed = _TOOL.validate_python({"type": "codebase_function", "function_id": "scheduling.next_slot"})
        assert isinstance(parsed, ic.CodebaseFunctionToolConfig)
        assert parsed.function_id == "scheduling.next_slot"

    def test_it_is_a_registered_tool_type(self):
        assert ic.ToolType.get_type_to_config_map()[ic.ToolType.CODEBASE_FUNCTION] is ic.CodebaseFunctionToolConfig
        assert ic.ToolType.is_valid("codebase_function")

    def test_a_tool_node_using_one_hydrates_typed(self):
        hydrated = ic.WorkflowConfigFullyHydrated.model_validate(
            {
                "node_configs": [
                    {
                        "type": "tool_node",
                        "name": "t",
                        "tool_config": {"type": "codebase_function", "function_id": "scheduling.next_slot"},
                    }
                ]
            }
        )
        node = hydrated.node_configs[0]
        assert isinstance(node, ic.ToolNodeConfig)
        assert isinstance(node.tool_config, ic.CodebaseFunctionToolConfig)

    def test_bindings_are_not_checked_without_registered_signatures(self, no_registered_signatures):
        # Upstream reads the signature from a server-side registry; offline, the server is the authority.
        config = ic.CodebaseFunctionToolConfig(function_id="f", variable_arguments=[_binding("anything")])
        assert config.variable_arguments[0].argument_name == "anything"

    def test_a_binding_the_function_does_not_accept_is_rejected_once_registered(self, no_registered_signatures):
        register_codebase_function_arguments({"f": ["patient_id"]})
        with pytest.raises(ValidationError, match="does not accept"):
            ic.CodebaseFunctionToolConfig(function_id="f", variable_arguments=[_binding("patient_name")])

    def test_a_declared_binding_is_accepted_once_registered(self, no_registered_signatures):
        register_codebase_function_arguments({"f": ["patient_id"]})
        config = ic.CodebaseFunctionToolConfig(function_id="f", variable_arguments=[_binding("patient_id")])
        assert len(config.variable_arguments) == 1

    def test_a_function_registered_with_no_arguments_rejects_every_binding(self, no_registered_signatures):
        # An empty registration means "accepts nothing", which is not the same as "unknown".
        register_codebase_function_arguments({"f": []})
        with pytest.raises(ValidationError):
            ic.CodebaseFunctionToolConfig(function_id="f", variable_arguments=[_binding("x")])


class TestMediaResults:
    def test_off_by_default(self):
        assert ic.ExternalAPIToolConfig().result_as_media is False

    @pytest.mark.parametrize(
        "readers",
        [
            {"result_variable_mappings": [{"result_path": "data", "target_variable_name": "d"}]},
            {"expand_result_into_runtime_variables": True},
        ],
    )
    def test_a_media_result_cannot_also_be_read_into_variables(self, readers):
        # The result is a media:// handle, so there are no fields for a mapping to read.
        with pytest.raises(ValidationError, match="media://"):
            ic.ExternalAPIToolConfig(api_endpoint="https://x", result_as_media=True, **readers)

    def test_a_media_result_with_no_readers_is_accepted(self):
        assert ic.ExternalAPIToolConfig(api_endpoint="https://x", result_as_media=True).result_as_media

    def test_it_survives_read_then_write(self):
        written = _TOOL.validate_python(
            {"type": "external_api", "api_endpoint": "https://x", "result_as_media": True}
        ).model_dump(mode="json")
        assert written["result_as_media"] is True


class TestPublishedDefaults:
    """Only a literal default reaches the JSON Schema a form is seeded from; a factory does not."""

    @pytest.mark.parametrize(
        "model, field, expected",
        [
            (ic.ExternalAPIToolConfig, "variable_arguments", []),
            (ic.ExternalAPIToolConfig, "result_variable_mappings", []),
            (ic.ExternalAPIToolConfig, "api_headers", {}),
            (ic.KnowledgeBaseToolConfig, "target_knowledge_base_ids", []),
            (ic.StaticMessagesConfig, "static_messages", []),
        ],
    )
    def test_the_schema_publishes_the_default(self, model, field, expected):
        schema = model.model_json_schema(mode="serialization")
        assert schema["properties"][field]["default"] == expected

    def test_a_tool_identity_is_never_published(self):
        # A published logical_id would be sent back by every form seeded from the schema, giving
        # distinct tools one shared identity.
        schema = ic.ExternalAPIToolConfig.model_json_schema(mode="serialization")
        assert "default" not in schema["properties"]["logical_id"]

    def test_literal_list_defaults_are_not_shared_between_instances(self):
        first, second = ic.StaticMessagesConfig(), ic.StaticMessagesConfig()
        first.static_messages.append("hello")
        assert second.static_messages == []

    def test_workflow_llm_default_is_no_llm(self):
        assert isinstance(ic.WorkflowConfig().llms_config, ic.NoLLMConfig)


class TestCompanionLifetime:
    def test_a_companion_stops_with_the_main_thread_by_default(self):
        assert ic.CompanionThreadConfig(is_companion_thread=True).stop_with_main_thread is True

    @pytest.mark.parametrize(
        "config, expected",
        [
            ({"is_companion_thread": True}, True),
            ({"is_companion_thread": True, "stop_with_main_thread": False}, False),
            ({"is_companion_thread": False}, False),  # not a companion: nothing to stop
            (None, False),
        ],
    )
    def test_the_edge_helper(self, config, expected):
        edge = ic.DirectEdgeConfig(
            source_node_logical_id="a",
            destination_node_logical_id="b",
            companion_thread_config=ic.CompanionThreadConfig(**config) if config is not None else None,
        )
        assert ic.edge_companion_stops_with_main_thread(edge) is expected


class TestVoicePersona:
    def test_too_long_is_rejected(self):
        with pytest.raises(ValidationError):
            ic.WorkflowConfig(voice_persona="x" * (ic.VOICE_PERSONA_MAX_LENGTH + 1))

    @pytest.mark.parametrize(
        "written, generated, expected",
        [
            ("You are Ada.", "You are Bo.", ("You are Ada.", "workflow")),  # hand-written wins
            (None, "You are Bo.", ("You are Bo.", "generated")),
            ("   ", "You are Bo.", ("You are Bo.", "generated")),  # whitespace is not a persona
            (None, None, (None, None)),
        ],
    )
    def test_resolution_order(self, written, generated, expected):
        hydrated = ic.WorkflowConfigFullyHydrated(
            workflow_config=ic.WorkflowConfig(voice_persona=written), generated_voice_persona=generated
        )
        assert hydrated.resolved_voice_persona() == expected


class TestDynamicVariableExtraction:
    def test_variables_from_several_configs_are_merged_and_none_is_skipped(self):
        tool = ic.ExternalAPIToolConfig(api_endpoint="https://x/{{patient.id}}")
        prompt = ic.PromptConfig(prompt="Hello {{first_name}}")
        assert extract_dynamic_variables(tool, None, prompt) == {"patient": {"id": ""}, "first_name": ""}

    def test_the_workflow_level_derivation_still_reads_nodes(self):
        hydrated = ic.WorkflowConfigFullyHydrated(
            workflow_config=ic.WorkflowConfig(),
            node_configs=[ic.SayLLMNodeConfig(name="n", main_response_config=ic.PromptConfig(prompt="Hi {{name}}"))],
        )
        assert derive_dynamic_variables(hydrated) == {"name": ""}


class TestCopilotCommands:
    def test_finish_is_distinct_from_stop(self):
        assert WorkflowCopilotCommand.FINISH.value == "finish"
        assert WorkflowCopilotCommand.STOP.value == "stop"
