"""Per-node realtime overrides, and the copilot's proposal and turn-done messages.

Both regressions were real. A node's `realtime_overrides` parsed but was dropped, so reading a workflow
and writing it back erased every per-node realtime setting. And a copilot event carrying a proposal
failed validation outright, because the payload union had no member for it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

import interactly_configs as ic
from interactly_configs.nodes.workflows.workflow_run_evaluator import WorkflowRunEvalLLMNodeConfig
from interactly_configs.workflow_copilot import (
    ProposalGraph,
    ProposalOutput,
    ProposedChangeItem,
    WorkflowCopilotCommand,
    WorkflowCopilotEvent,
    WorkflowCopilotInput,
    WorkflowCopilotOutputType,
    WorkflowCopilotTurnDoneEvent,
)

_OVERRIDES = {"reasoning_effort": "high", "transcription_keywords": ["Aetna", "Cigna"]}


class TestRealtimeOverrides:
    def test_everything_inherits_by_default(self):
        overrides = ic.NodeRealtimeOverrides()
        assert (overrides.reasoning_effort, overrides.voice, overrides.preamble_mode, overrides.turn_detection) == (
            None,
            None,
            None,
            None,
        )
        assert overrides.transcription_keywords == []

    def test_keyword_lists_are_not_shared_between_instances(self):
        first, second = ic.NodeRealtimeOverrides(), ic.NodeRealtimeOverrides()
        first.transcription_keywords.append("Aetna")
        assert second.transcription_keywords == []

    @pytest.mark.parametrize("node_cls", [ic.SayLLMNodeConfig, ic.WorkerLLMNodeConfig, WorkflowRunEvalLLMNodeConfig])
    def test_every_llm_node_carries_them(self, node_cls):
        node = node_cls(name="n", realtime_overrides=_OVERRIDES)
        assert node.realtime_overrides.transcription_keywords == ["Aetna", "Cigna"]

    def test_unset_on_a_node_by_default(self):
        assert ic.SayLLMNodeConfig(name="n").realtime_overrides is None

    def test_they_survive_read_then_write(self):
        # Arrange: what a GET returns for a node with overrides.
        hydrated = ic.WorkflowConfigFullyHydrated.model_validate(
            {"node_configs": [{"type": "say_llm", "name": "n", "realtime_overrides": _OVERRIDES}]}
        )
        # Act: what an SDK user sends back.
        written = hydrated.node_configs[0].model_dump(mode="json")
        # Assert
        assert written["realtime_overrides"]["reasoning_effort"] == "high"
        assert written["realtime_overrides"]["transcription_keywords"] == ["Aetna", "Cigna"]


class TestCopilotCommands:
    def test_the_three_ways_to_leave_a_conversation_are_distinct(self):
        assert {WorkflowCopilotCommand.STOP, WorkflowCopilotCommand.NEW_CHAT, WorkflowCopilotCommand.FINISH} == {
            WorkflowCopilotCommand("stop"),
            WorkflowCopilotCommand("new_chat"),
            WorkflowCopilotCommand("finish"),
        }

    def test_input_carries_a_session_and_page_context(self):
        sent = WorkflowCopilotInput(input_text="hi", session_id="s1", page_context={"page": "workflow", "id": "w1"})
        restored = WorkflowCopilotInput.model_validate(sent.model_dump(mode="json"))
        assert (restored.session_id, restored.page_context) == ("s1", {"page": "workflow", "id": "w1"})


class TestProposals:
    _PROPOSAL = {
        "type": "proposal",
        "proposal_id": "p1",
        "summary": "Add a triage node",
        "changes": [{"status": "added", "kind": "node", "name": "Triage"}],
        "graph": {"nodes": [{"logical_id": "n1", "name": "Triage", "status": "added"}], "edges": []},
    }

    def test_a_copilot_event_carrying_a_proposal_parses_typed(self):
        event = WorkflowCopilotEvent.model_validate({"type": "workflow_copilot", "payload": self._PROPOSAL})
        assert isinstance(event.payload, ProposalOutput)
        assert isinstance(event.payload.changes[0], ProposedChangeItem)
        assert isinstance(event.payload.graph, ProposalGraph)

    def test_a_proposal_needs_an_id_to_accept_against(self):
        with pytest.raises(ValidationError):
            ProposalOutput(summary="no id")

    def test_the_graph_is_optional(self):
        # A rename has no useful graph; absence is normal.
        assert ProposalOutput(proposal_id="p1").graph is None

    def test_defaults(self):
        proposal = ProposalOutput(proposal_id="p1")
        assert (proposal.type, proposal.entity, proposal.changes) == (WorkflowCopilotOutputType.PROPOSAL.value, "workflow", [])


class TestTurnDone:
    def test_it_is_a_distinct_top_level_event(self):
        done = WorkflowCopilotTurnDoneEvent(request_id="r1", outcome="ok")
        assert done.type == "workflow_copilot_done"
        assert done.type != WorkflowCopilotEvent().type

    def test_it_carries_no_content(self):
        assert set(WorkflowCopilotTurnDoneEvent.model_fields) == {"type", "request_id", "outcome"}
