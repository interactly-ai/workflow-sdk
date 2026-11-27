"""Configs whose ``type`` this package does not know yet, and the paused simulation group.

A client lags the server, so a workflow can name an LLM provider or a tool type added after this package was
released. Before the fallbacks, one such config failed the node that held it, and the node came back as
`UnknownNodeConfig` with every typed field lost. These pin the narrower failure: only the config is unknown, it keeps
and writes back exactly what the server sent, the published JSON Schema does not change, and a known type with a
mistake in it still raises.
"""

from __future__ import annotations

import json
import warnings
from typing import Any, Dict, Iterator

import pytest
from pydantic import TypeAdapter, ValidationError

import interactly_configs as ic

_FUTURE_LLM: Dict[str, Any] = {
    "type": "mistral_llm",
    "provider": "mistral",
    "model": "mistral-large-3",
    "vertex_location": "global",
    "temperature": 0.2,
}
_FUTURE_TOOL: Dict[str, Any] = {
    "type": "mcp_server",
    "name": "lookup",
    "server_url": "https://mcp.example.com/mcp",
    "result_variable_mappings": [{"result_path": "patient.id", "target_variable_name": "patient_id"}],
}


@pytest.fixture(autouse=True)
def no_serializer_warnings() -> Iterator[None]:
    """A fallback serialized inside a union must not warn that it matched no member."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        yield


class TestUnknownLLMProvider:
    def test_an_llm_node_keeps_its_class_and_only_the_config_is_unknown(self):
        # Act
        node = ic.SayLLMNodeConfig.model_validate({"type": "say_llm", "name": "greet", "llms_config": _FUTURE_LLM})
        # Assert
        assert isinstance(node.llms_config, ic.UnknownLLMConfig)
        assert node.llms_config.model == "mistral-large-3"
        assert node.llms_config.temperature == 0.2

    def test_it_is_written_back_with_exactly_the_fields_it_arrived_with(self):
        node = ic.SayLLMNodeConfig.model_validate({"type": "say_llm", "name": "greet", "llms_config": _FUTURE_LLM})
        assert node.model_dump()["llms_config"] == _FUTURE_LLM
        assert json.loads(node.model_dump_json())["llms_config"] == _FUTURE_LLM

    def test_on_its_own_it_also_writes_back_only_what_arrived(self):
        # Not the defaults it inherits from BaseLLMConfig, and not a logical_id minted afresh on every read.
        assert ic.UnknownLLMConfig.model_validate(_FUTURE_LLM).model_dump() == _FUTURE_LLM

    def test_a_group_member_of_an_unknown_provider_does_not_fail_the_group(self):
        group = ic.LLMGroupConfig.model_validate(
            {"type": "llm_group", "llms": [{"type": "openai_llm", "model": "gpt-4.1"}, _FUTURE_LLM]}
        )
        assert [type(member).__name__ for member in group.llms] == ["OpenAILLMConfig", "UnknownLLMConfig"]
        assert group.model_dump()["llms"][1] == _FUTURE_LLM

    def test_a_workflow_default_of_an_unknown_provider_is_kept(self):
        workflow = ic.WorkflowConfig.model_validate({"name": "w", "llms_config": _FUTURE_LLM})
        assert isinstance(workflow.llms_config, ic.UnknownLLMConfig)

    def test_a_hydrated_workflow_keeps_its_node_classes(self):
        hydrated = ic.WorkflowConfigFullyHydrated.model_validate(
            {
                "workflow_config": {"name": "w"},
                "node_configs": [
                    {"type": "say_llm", "name": "greet", "llms_config": _FUTURE_LLM},
                    {"type": "tool_node", "name": "lookup", "tool_config": _FUTURE_TOOL},
                ],
            }
        )
        assert [type(node).__name__ for node in hydrated.node_configs] == ["SayLLMNodeConfig", "ToolNodeConfig"]

    def test_a_known_provider_with_an_invalid_field_still_raises(self):
        bad = {"type": "openai_llm", "model": "gpt-4.1", "temperature": -5}
        with pytest.raises(ValidationError) as caught:
            ic.SayLLMNodeConfig.model_validate({"type": "say_llm", "name": "greet", "llms_config": bad})
        assert {e["type"] for e in caught.value.errors()} == {"greater_than_equal"}

    def test_a_config_with_no_type_still_raises(self):
        with pytest.raises(ValidationError) as caught:
            ic.SayLLMNodeConfig.model_validate({"type": "say_llm", "name": "greet", "llms_config": {"model": "x"}})
        assert {e["type"] for e in caught.value.errors()} == {"union_tag_not_found"}


class TestUnknownToolType:
    def test_a_tool_node_keeps_its_class_and_only_the_config_is_unknown(self):
        node = ic.ToolNodeConfig.model_validate({"type": "tool_node", "name": "lookup", "tool_config": _FUTURE_TOOL})
        assert isinstance(node.tool_config, ic.UnknownToolConfig)
        # The fields every tool shares are typed, so the checks that run on any tool node run on this one too.
        assert node.tool_config.result_variable_mappings[0].target_variable_name == "patient_id"

    def test_it_is_written_back_with_exactly_the_fields_it_arrived_with(self):
        node = ic.ToolNodeConfig.model_validate({"type": "tool_node", "name": "lookup", "tool_config": _FUTURE_TOOL})
        assert node.model_dump(mode="json")["tool_config"] == _FUTURE_TOOL

    def test_a_standalone_tool_config_of_an_unknown_type_validates(self):
        tool = TypeAdapter(ic.ToolConfig).validate_python(_FUTURE_TOOL)
        assert isinstance(tool, ic.UnknownToolConfig)


class TestThePublishedSchemaIsUnchanged:
    """The fallbacks are client-side behaviour; the JSON Schema must stay identical to upstream's."""

    @pytest.mark.parametrize("model", [ic.SayLLMNodeConfig, ic.LLMGroupConfig, ic.ToolNodeConfig, ic.ToolsConfig])
    @pytest.mark.parametrize("mode", ["validation", "serialization"])
    def test_no_fallback_class_appears_in_the_schema(self, model, mode):
        schema = json.dumps(model.model_json_schema(mode=mode))
        assert "UnknownLLMConfig" not in schema
        assert "UnknownToolConfig" not in schema

    def test_a_nested_llm_union_still_merges_into_one_discriminator(self):
        # A validator on the nested `LLMConfig` would stop pydantic merging its tags into the outer union, and each
        # mapping entry would become an inline schema rather than a reference.
        schema = ic.SayLLMNodeConfig.model_json_schema(mode="serialization")
        union = next(option for option in schema["properties"]["llms_config"]["anyOf"] if "discriminator" in option)
        mapping = union["discriminator"]["mapping"]
        assert all(isinstance(target, str) and target.startswith("#/$defs/") for target in mapping.values())
        assert {"openai_llm", "llm_group", "llm_group_with_backchannel"} <= set(mapping)


class TestPausedSimulationGroup:
    def test_paused_is_a_simulation_status(self):
        assert ic.SimulationStatus("paused") is ic.SimulationStatus.PAUSED

    def test_a_simulation_carrying_it_validates(self):
        config = ic.SimulationConfig.model_validate({"name": "s", "status": "paused"})
        assert config.status is ic.SimulationStatus.PAUSED
