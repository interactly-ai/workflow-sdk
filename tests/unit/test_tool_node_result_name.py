"""The mirror agrees with the server about where a tool node writes its outcome.

This is not decoration. `ToolNodeConfig._check_mappings_avoid_this_nodes_outcome_keys` reserves
`<name>_success` / `<name>_error` against mapping targets, and *which* name it reserves depends on this
rule. A mirror using the older "the node's field always wins" reading would reject configs the server
accepts and accept configs the server rejects — and `make parity-check` would report nothing, because it
compares a validator as `"{decorator}:{mode}"` and does not look at module-level functions at all. That
is the second instance of that blind spot; the first was the inbuilt binding validator.
"""

import pytest
from pydantic import ValidationError

from interactly_configs.nodes.tool.tool_node import ToolNodeConfig, effective_result_variable_name
from interactly_configs.tool import InlinePythonToolConfig, ToolResultVariableMapping

CODE = "def score():\n    return {'tier': 'high'}\n"


def _tool(**overrides) -> InlinePythonToolConfig:
    defaults = dict(logical_id="tool_score", name="score", signature="Scores.", code=CODE)
    defaults.update(overrides)
    return InlinePythonToolConfig(**defaults)


def _node(*, tool=None, **overrides) -> ToolNodeConfig:
    defaults = dict(logical_id="n", name="Score", tool_config=tool or _tool())
    defaults.update(overrides)
    return ToolNodeConfig(**defaults)


class TestThePrecedenceRule:
    @pytest.mark.parametrize(
        "node_name, tool_name, expected",
        [
            (None, "kb_answer", "kb_answer"),
            ("tool_result", "kb_answer", "kb_answer"),  # indistinguishable from unset; the tool wins
            ("scoring", "kb_answer", "scoring"),
            ("scoring", None, "scoring"),
            (None, None, "tool_result"),
        ],
    )
    def test_the_whole_table(self, node_name, tool_name, expected):
        node = _node(result_runtime_variable_name=node_name) if node_name is not None else _node()
        tool = _tool(result_runtime_variable_name=tool_name) if tool_name else _tool()

        assert effective_result_variable_name(node, tool) == expected

    def test_it_copes_with_no_tool(self):
        assert effective_result_variable_name(_node(), None) == "tool_result"

    def test_it_survives_a_round_trip(self):
        """A `model_fields_set` rule would break here on the server, where every config arrives through
        one. Pinned in the mirror too, so a later "simplification" cannot reintroduce it on this side."""
        tool = _tool(result_runtime_variable_name="kb_answer")
        stored = ToolNodeConfig.model_validate(_node(tool=tool).model_dump())

        assert "result_runtime_variable_name" in stored.model_fields_set
        assert effective_result_variable_name(stored, stored.tool_config) == "kb_answer"

    def test_it_reads_the_declared_default(self):
        assert ToolNodeConfig.model_fields["result_runtime_variable_name"].default == "tool_result"


class TestTheValidatorReservesTheEffectiveName:
    def test_a_mapping_onto_the_tools_derived_key_is_rejected(self):
        with pytest.raises(ValidationError, match="already writes as the outcome"):
            _node(
                tool=_tool(
                    result_runtime_variable_name="kb_answer",
                    result_variable_mappings=[
                        ToolResultVariableMapping(target_variable_name="kb_answer_success", result_path="tier")
                    ],
                )
            )

    def test_a_mapping_onto_the_nodes_derived_key_is_still_rejected(self):
        with pytest.raises(ValidationError, match="already writes as the outcome"):
            _node(
                tool=_tool(
                    result_variable_mappings=[
                        ToolResultVariableMapping(target_variable_name="scoring_error", result_path="tier")
                    ]
                ),
                result_runtime_variable_name="scoring",
            )

    def test_the_superseded_name_is_free(self):
        """Nothing writes `tool_result_success` once the tool names the result, so reserving it would
        reject a legal config — and would differ from the server."""
        node = _node(
            tool=_tool(
                result_runtime_variable_name="kb_answer",
                result_variable_mappings=[
                    ToolResultVariableMapping(target_variable_name="tool_result_success", result_path="tier")
                ],
            )
        )

        assert node.tool_config.result_variable_mappings[0].target_variable_name == "tool_result_success"
