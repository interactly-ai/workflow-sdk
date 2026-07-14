"""
Unit tests for response model deserialisation (Phase C).

These tests verify that the model_validator on each response model:
  - Leaves dict values as-is when interactly_configs is not installed or the raw
    value doesn't match the schema.
  - Upgrades dict values to typed Pydantic objects when interactly_configs is
    installed and the data is valid.
  - Never raises — failed coercions are silenced and the field stays as dict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from interactly.types.edges.edge import Edge
from interactly.types.llm_configs.llm_config import LLMConfig
from interactly.types.nodes.node import Node
from interactly.types.node_libraries.node_library import NodeLibrary
from interactly.types.runs.run import Run
from interactly.types.super_nodes.super_node import SuperNodeDetail
from interactly.types.tools.tool import Tool
from interactly.types.workflows.workflow import WorkflowVersion


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

_MINIMAL_NODE_CONFIG = {"node_type": "llm", "name": "Test Node"}
_MINIMAL_EDGE_CONFIG = {"edge_type": "direct", "source_node_logical_id": "a", "destination_node_logical_id": "b"}
_MINIMAL_TOOL_CONFIG = {"tool_type": "api_call", "name": "My Tool"}
_MINIMAL_WORKFLOW_CONFIG = {"nodes": [], "edges": []}
_MINIMAL_RUN_INPUT = {"session_id": "sess-1"}
_MINIMAL_RUN_OUTPUT = {"result": "ok"}


# --------------------------------------------------------------------------- #
# Node                                                                         #
# --------------------------------------------------------------------------- #


class TestNodeResponseDeserialisation:

    def test_node_config_is_none_when_absent(self):
        node = Node.model_validate({"id": "n-1"})
        assert node.node_config is None

    def test_node_config_non_dict_passes_through(self):
        """Non-dict values (e.g. already-parsed objects) are left untouched."""
        sentinel = object()
        node = Node.model_validate({"id": "n-1", "node_config": sentinel})
        assert node.node_config is sentinel

    def test_node_model_validates_without_config_lib(self):
        """Node.model_validate must succeed even without interactly_configs."""
        node = Node.model_validate({
            "id": "n-1",
            "node_config": {"node_type": "say_llm"},
            "team_id": "team-1",
        })
        assert node.id == "n-1"
        assert node.team_id == "team-1"


# --------------------------------------------------------------------------- #
# Edge                                                                         #
# --------------------------------------------------------------------------- #


class TestEdgeResponseDeserialisation:
    def test_edge_config_stays_dict_when_configs_absent(self):
        with patch.dict("sys.modules", {"interactly_configs": None}):
            edge = Edge.model_validate({"id": "e-1", "edge_config": _MINIMAL_EDGE_CONFIG})
        assert isinstance(edge.edge_config, dict)

    def test_edge_config_is_none_when_absent(self):
        edge = Edge.model_validate({"id": "e-1"})
        assert edge.edge_config is None

    def test_bad_edge_config_does_not_raise(self):
        """An invalid edge_config dict must not crash the model validator."""
        edge = Edge.model_validate({"id": "e-1", "edge_config": {"broken": True}})
        # The validator either upgrades to typed or silently keeps dict — never raises
        assert edge is not None


# --------------------------------------------------------------------------- #
# Tool                                                                         #
# --------------------------------------------------------------------------- #


class TestToolResponseDeserialisation:
    def test_tool_config_stays_dict_when_configs_absent(self):
        with patch.dict("sys.modules", {"interactly_configs": None}):
            tool = Tool.model_validate({"id": "t-1", "tool_config": _MINIMAL_TOOL_CONFIG})
        assert isinstance(tool.tool_config, dict)

    def test_tool_config_is_none_when_absent(self):
        tool = Tool.model_validate({"id": "t-1"})
        assert tool.tool_config is None


# --------------------------------------------------------------------------- #
# NodeLibrary                                                                  #
# --------------------------------------------------------------------------- #


class TestNodeLibraryResponseDeserialisation:

    def test_node_library_config_is_none_when_absent(self):
        lib = NodeLibrary.model_validate({"id": "l-1"})
        assert lib.node_library_config is None


# --------------------------------------------------------------------------- #
# WorkflowVersion                                                              #
# --------------------------------------------------------------------------- #


class TestWorkflowVersionResponseDeserialisation:

    def test_config_is_none_when_absent(self):
        ver = WorkflowVersion.model_validate({"version_number": 1, "is_active": False})
        assert ver.config is None


# --------------------------------------------------------------------------- #
# SuperNodeDetail                                                              #
# --------------------------------------------------------------------------- #


class TestSuperNodeDetailResponseDeserialisation:

    def test_encapsulated_config_is_none_when_absent(self):
        detail = SuperNodeDetail.model_validate({"workflow_id": "wf-1", "num_input_fields": 0})
        assert detail.encapsulated_workflow_config is None


# --------------------------------------------------------------------------- #
# Run                                                                          #
# --------------------------------------------------------------------------- #


class TestLLMConfigResponseDeserialisation:

    def test_config_is_none_when_absent(self):
        cfg = LLMConfig.model_validate({"id": "llm-1", "name": "Team GPT"})
        assert cfg.config is None

    def test_unrecognised_config_stays_dict(self):
        # A payload that does not validate against any LLMOrGroupConfig variant
        # must be left as a plain dict (the coercion is silenced, never raised).
        cfg = LLMConfig.model_validate(
            {"id": "llm-1", "config": {"type": "not_a_real_provider", "foo": "bar"}}
        )
        assert isinstance(cfg.config, dict)

    def test_valid_config_coerces_when_configs_installed(self):
        # With the [configs] extra installed, a valid provider config is upgraded
        # from dict to a typed object (no longer a plain dict).
        pytest.importorskip("pydantic")
        cfg = LLMConfig.model_validate(
            {"id": "llm-1", "config": {"type": "openai_llm", "model": "gpt-5"}}
        )
        try:
            from interactly_configs import OpenAILLMConfig  # noqa: F401
        except Exception:
            pytest.skip("interactly_configs not installed")
        assert not isinstance(cfg.config, dict)

    def test_single_object_envelope_is_unwrapped(self):
        cfg = LLMConfig.model_validate({"llm_config": {"id": "llm-1", "name": "Wrapped"}})
        assert cfg.id == "llm-1"
        assert cfg.name == "Wrapped"

    def test_bad_config_does_not_raise(self):
        cfg = LLMConfig.model_validate({"id": "llm-1", "config": {"broken": True}})
        assert cfg is not None


class TestRunResponseDeserialisation:

    def test_input_output_pairs_default_to_empty_list_when_absent(self):
        run = Run.model_validate({"id": "run-1", "workflow_id": "wf-1"})
        assert run.input_output_pairs == []

    def test_run_validates_with_all_fields(self):
        run = Run.model_validate({
            "id": "run-1",
            "workflow_id": "wf-1",
            "status": "completed",
            "run_by": "api",
            "version_number": 2,
            "input_output_pairs": [
                {
                    "run_input": {"command": "start"},
                    "run_output": {"events": [{"type": "user_messages", "logical_id": "e1"}]},
                }
            ],
        })
        assert run.id == "run-1"
        # status is Optional[str] (finding RT-3).
        assert run.status == "completed"
        assert len(run.input_output_pairs) == 1

    def test_input_output_pairs_upgraded_to_typed_when_configs_installed(self):
        # When interactly_configs is available, each pair is upgraded to a typed
        # WorkflowRunInputOutputPair; otherwise it stays a plain dict.
        pytest.importorskip("interactly_configs")
        from interactly_configs import WorkflowRunInputOutputPair

        run = Run.model_validate(
            {
                "id": "run-1",
                "workflow_id": "wf-1",
                "input_output_pairs": [
                    {
                        "run_input": {"command": "start"},
                        "run_output": {"events": [{"type": "user_messages", "logical_id": "e1"}]},
                    }
                ],
            }
        )
        pair = run.input_output_pairs[0]
        assert isinstance(pair, WorkflowRunInputOutputPair)
        assert pair.run_output is not None
        assert len(pair.run_output.events) == 1
