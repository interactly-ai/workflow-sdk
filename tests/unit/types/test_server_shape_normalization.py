"""Regression tests for server-shape normalization in response models.

These lock in the fixes surfaced by the live dev E2E runs: ``_id``/logical-id
mapping, envelope unwrapping, nested-document flattening, discriminated-union
config parsing, pagination item extraction, and convenience accessors. They are
pure (no network) — they validate the models against representative server
payloads.
"""

from __future__ import annotations

import pytest

from interactly._pagination import _extract_items
from interactly.types.edges.edge import Edge
from interactly.types.global_variables.global_variable import GlobalVariable
from interactly.types.llm_configs.llm_config import LLMConfig
from interactly.types.node_libraries.node_library import NodeLibrary
from interactly.types.nodes.node import Node
from interactly.types.runs.run import Run, RunComment
from interactly.types.runs.run_event import RunEvent
from interactly.types.schedules.schedule import Schedule
from interactly.types.simulations.simulation import Simulation
from interactly.types.tools.tool import Tool
from interactly.types.workflows.workflow import Workflow


class TestIdMapping:
    def test_node_maps_underscore_id(self):
        assert Node.model_validate({"_id": "abc123", "node_config": None}).id == "abc123"

    def test_edge_maps_underscore_id(self):
        assert Edge.model_validate({"_id": "e1", "edge_config": None}).id == "e1"

    def test_tool_maps_underscore_id(self):
        assert Tool.model_validate({"_id": "t1", "tool_config": None}).id == "t1"

    def test_node_library_maps_underscore_id(self):
        assert NodeLibrary.model_validate({"_id": "nl1", "node_library_config": None}).id == "nl1"

    def test_schedule_maps_underscore_id(self):
        row = {
            "_id": "s1", "workflow_id": "w1", "team_id": "team",
            "status": "pending", "scheduled_time": "2026-07-07T00:00:00Z",
        }
        assert Schedule.model_validate(row).id == "s1"

    def test_global_variable_maps_underscore_id(self):
        assert GlobalVariable.model_validate({"_id": "g1", "name": "company_name"}).id == "g1"

    def test_llm_config_id_comes_from_logical_id_not_underscore_id(self):
        model = LLMConfig.model_validate({"_id": "mongo123", "llm_config_id": "uuid-abc", "config": None})
        assert model.id == "uuid-abc"

    def test_simulation_maps_underscore_id(self):
        assert Simulation.model_validate({"_id": "sim1", "simulation_config": {"name": "S"}}).id == "sim1"


class TestConvenienceAccessors:
    def test_tool_name_and_description_from_config(self):
        tool = Tool.model_validate({"_id": "t1", "tool_config": {"name": "Doubler", "description": "x2"}})
        assert tool.name == "Doubler"
        assert tool.description == "x2"

    def test_simulation_name_and_description_from_config(self):
        sim = Simulation.model_validate({"_id": "s1", "simulation_config": {"name": "Sweep", "description": "d"}})
        assert sim.name == "Sweep"
        assert sim.description == "d"


class TestWorkflowRobustness:
    def test_name_optional_for_incomplete_workflow(self):
        # An empty workflow comes back with a null config and therefore no name.
        wf = Workflow.model_validate({"_id": "w1", "workflow_config": None})
        assert wf.id == "w1"
        assert wf.name is None


class TestNodeConfigSubclass:
    def test_node_config_parses_to_concrete_subclass(self):
        node = Node.model_validate(
            {"_id": "n1", "node_config": {"type": "say_llm", "name": "Greet",
                                          "main_response_config": {"prompt": "hi"}}}
        )
        assert type(node.node_config).__name__ == "SayLLMNodeConfig"
        assert node.node_config.type == "say_llm"


class TestRunFlattening:
    def test_run_flattens_nested_get_envelope(self):
        payload = {
            "workflow_run": {
                "_id": "doc1", "team_id": "team", "created_at": "2026-07-07T00:00:00Z",
                "updated_at": "2026-07-07T00:00:01Z", "created_by": "u1",
                "workflow_run": {
                    "workflow_run_id": "run1", "workflow_id": "wf1",
                    "status": "completed", "run_by": "api", "version_number": 0,
                    "input_output_pairs": [
                        {
                            "run_input": {"command": "start"},
                            "run_output": {"events": [{"type": "user_messages", "logical_id": "e1"}]},
                        }
                    ],
                    "comments": [],
                },
            }
        }
        run = Run.model_validate(payload)
        assert run.id == "run1"
        assert run.workflow_id == "wf1"
        assert run.status == "completed"
        # The nested state's input_output_pairs survive flattening onto the DTO.
        assert len(run.input_output_pairs) == 1

    def test_run_comment_extracted_from_run_envelope(self):
        payload = {
            "workflow_run": {
                "_id": "doc1",
                "workflow_run": {"comments": [{"logical_id": "c1", "content": "first"},
                                              {"logical_id": "c2", "content": "newest"}]},
            }
        }
        comment = RunComment.model_validate(payload)
        assert comment.logical_id == "c2"
        assert comment.content == "newest"


class TestRunEventNormalization:
    def test_ack_frame_without_type_gets_synthetic_type(self):
        event = RunEvent.model_validate(
            {"workflow_run_id": "r1", "workflow_id": "w1", "message": "started"}
        )
        assert event.type == "run_ack"
        assert not event.is_terminal()

    def test_rich_event_maps_node_and_content(self):
        event = RunEvent.model_validate(
            {"type": "say_llm", "origin_node_logical_id": "node_x", "content": "Hello!"}
        )
        assert event.node_id == "node_x"
        assert event.output == "Hello!"

    def test_end_workflow_is_terminal(self):
        assert RunEvent.model_validate({"type": "end_workflow"}).is_terminal()


class TestExtractItems:
    @pytest.mark.parametrize(
        "envelope_key",
        ["items", "workflows", "versions", "llm_configs", "variables", "workflow_runs", "tools", "subscriptions"],
    )
    def test_recognises_resource_envelopes(self, envelope_key):
        raw = {envelope_key: [{"a": 1}, {"a": 2}], "total": 2}
        assert _extract_items(raw) == [{"a": 1}, {"a": 2}]

    def test_ignores_categories_metadata_list(self):
        raw = {"categories": ["contact"], "variables": [{"name": "x"}], "total": 1}
        assert _extract_items(raw) == [{"name": "x"}]
