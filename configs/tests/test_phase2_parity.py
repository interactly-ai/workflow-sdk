"""
Coverage for the config models added in the Phase 2 parity pass.

Two kinds of test live here:

1. **Behaviour** of the new models — construction, discriminated-union round-trips, and the
   validators/bounds that make an invalid config fail here rather than at the server.
2. **Anti-regression pins** for decisions that are easy to undo by accident. The enum-membership
   pins are the important ones: the SDK previously offered five Google and two Anthropic models the
   server had already deleted, and nothing caught it. Pinning the member set means re-adding a dead
   model, or dropping a live one, fails a test instead of a production call.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

import interactly_configs as ic
from interactly_configs.events.event import (
    CompanionStepBoundaryEvent,
    WaitingEvaluationBoundaryEvent,
    parse_event,
    should_persist_background_event,
)
from interactly_configs.nodes.node_unions import (
    NodeConfig,
    NodeMetadataRetriever,
    NodeRunInput,
    NodeRunOutput,
)


class TestSelfLoopConfig:
    """Bounded self-loop / retry policy."""

    def test_accepts_a_retry_bound(self):
        cfg = ic.SelfLoopConfig(enabled=True, max_retries=3)
        assert cfg.max_retries == 3
        assert cfg.time_between_retries == 0

    def test_accepts_a_time_bound(self):
        assert ic.SelfLoopConfig(enabled=True, expiry_time=30).expiry_time == 30

    def test_enabled_without_any_bound_is_rejected(self):
        # The whole point of the config is that the loop terminates. Enabling it with neither bound
        # would spin forever, so this must fail client-side rather than at the server.
        with pytest.raises(ValidationError, match="at least one of max_retries or expiry_time"):
            ic.SelfLoopConfig(enabled=True)

    def test_disabled_without_bounds_is_fine(self):
        assert ic.SelfLoopConfig().enabled is False

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"enabled": True, "max_retries": 101},       # le=100
            {"enabled": True, "max_retries": -1},        # ge=0
            {"enabled": True, "expiry_time": 3601},      # le=3600
            {"enabled": True, "expiry_time": 0},         # ge=1
            {"enabled": True, "max_retries": 1, "time_between_retries": 301},  # le=300
        ],
    )
    def test_bounds_are_enforced(self, kwargs):
        with pytest.raises(ValidationError):
            ic.SelfLoopConfig(**kwargs)

    def test_attaches_to_any_node(self):
        node = ic.SayLLMNodeConfig(self_loop_config=ic.SelfLoopConfig(enabled=True, max_retries=2))
        assert node.self_loop_config.max_retries == 2

    def test_defaults_to_none_so_existing_configs_are_unaffected(self):
        assert ic.SayLLMNodeConfig().self_loop_config is None


class TestNoOpNode:
    """The utility no-op node, and its registration across every union and lookup map."""

    def test_defaults(self):
        node = ic.NoOpNodeConfig()
        assert node.type == "no_op"
        assert node.output_runtime_variable_name == "no_op_result"
        assert node.simulate_failure is False
        assert node.secondary_category == ic.NodeCategory.UTILITY.value

    @pytest.mark.parametrize(
        "adapter, payload, expected",
        [
            (TypeAdapter(NodeConfig), {"type": "no_op", "name": "placeholder"}, ic.NoOpNodeConfig),
            (TypeAdapter(NodeRunInput), {"type": "no_op"}, ic.NoOpNodeRunInput),
            (TypeAdapter(NodeRunOutput), {"type": "no_op", "success": True}, ic.NoOpNodeRunOutput),
        ],
    )
    def test_resolves_through_each_discriminated_union(self, adapter, payload, expected):
        assert isinstance(adapter.validate_python(payload), expected)

    @pytest.mark.parametrize(
        "getter",
        [
            NodeMetadataRetriever.get_type_to_default_config_map,
            NodeMetadataRetriever.get_type_to_config_class_map,
            NodeMetadataRetriever.get_type_to_run_input_class_map,
            NodeMetadataRetriever.get_type_to_run_output_class_map,
        ],
    )
    def test_registered_in_every_metadata_map(self, getter):
        # Registering a node type means touching seven separate places. Missing one fails only for
        # the operation that uses that map, which is exactly the kind of gap that ships.
        assert ic.NodeType.NO_OP in getter()

    def test_get_node_config_class_resolves_it(self):
        assert ic.get_node_config_class("no_op") is ic.NoOpNodeConfig


class TestCompanionThreads:
    def test_direct_edge_carries_companion_config(self):
        edge = ic.DirectEdgeConfig(
            companion_thread_config=ic.CompanionThreadConfig(is_companion_thread=True, thread_id="poller")
        )
        assert ic.edge_is_companion(edge) is True
        assert ic.edge_companion_thread_id(edge) == "poller"

    def test_helpers_are_defensive_on_edges_without_the_config(self):
        # The helpers are called against any edge in a graph, not just direct ones, and against
        # configs stored before the feature existed.
        assert ic.edge_is_companion(ic.DirectEdgeConfig()) is False
        assert ic.edge_is_companion(ic.CompanionEdgeConfig()) is False
        assert ic.edge_companion_thread_id(ic.ConditionalEdgeConfig()) is None

    def test_delimiter_is_the_documented_value(self):
        # Load-bearing: thread_reference_id derivation splits on it.
        assert ic.COMPANION_THREAD_DELIMITER == "_companion_"


class TestEvaluateWhileWaiting:
    def test_enabled_config_is_reported_by_the_helper(self):
        edge = ic.ConditionalEdgeConfig(
            evaluate_while_waiting_config=ic.EvaluateWhileWaitingConfig(
                enabled=True, trigger_node_logical_ids=["node_a"]
            )
        )
        assert ic.edge_evaluates_while_waiting(edge) is True
        assert ic.edge_waiting_evaluation_config(edge).trigger_node_logical_ids == ["node_a"]

    def test_disabled_config_reads_as_off(self):
        edge = ic.ConditionalEdgeConfig(
            evaluate_while_waiting_config=ic.EvaluateWhileWaitingConfig(enabled=False)
        )
        assert ic.edge_evaluates_while_waiting(edge) is False
        assert ic.edge_waiting_evaluation_config(edge) is None

    def test_absent_config_reads_as_off(self):
        assert ic.edge_evaluates_while_waiting(ic.ConditionalEdgeConfig()) is False

    def test_default_trigger_mode_is_node_completion(self):
        # The blind-polling mode needs a debounce to be safe, so the safe mode is the default.
        cfg = ic.EvaluateWhileWaitingConfig(enabled=True)
        assert cfg.trigger_mode is ic.WaitingEvaluationTriggerMode.ON_NODE_COMPLETION
        assert cfg.max_transitions_per_wait == 3

    def test_max_transitions_must_be_at_least_one(self):
        with pytest.raises(ValidationError):
            ic.EvaluateWhileWaitingConfig(enabled=True, max_transitions_per_wait=0)


class TestRatingsAndComments:
    def test_rating_request_requires_a_known_value(self):
        assert ic.RatingRequest(value="up").value is ic.RatingValue.UP
        with pytest.raises(ValidationError):
            ic.RatingRequest(value="sideways")

    def test_rating_scores_cover_every_value(self):
        assert set(ic.RATING_SCORES) == set(ic.RatingValue)

    def test_comment_request_trims_and_rejects_blank(self):
        assert ic.CommentRequest(content="  looks good  ").content == "looks good"
        with pytest.raises(ValidationError, match="cannot be blank"):
            ic.CommentRequest(content="   ")

    def test_comment_request_enforces_the_length_cap(self):
        assert ic.CommentRequest(content="x" * ic.MAX_COMMENT_LENGTH)
        with pytest.raises(ValidationError):
            ic.CommentRequest(content="x" * (ic.MAX_COMMENT_LENGTH + 1))

    def test_stored_comment_config_stays_permissive(self):
        # CommentConfig is also the READ shape for records written before the rules existed,
        # including comments stored with null content. Constraining it would make them unreadable.
        assert ic.CommentConfig(content=None).content is None

    def test_turns_carry_comments_and_ratings(self):
        pair = ic.WorkflowRunInputOutputPair(
            comments=[ic.CommentConfig(content="turn note")],
            ratings=[ic.RatingConfig(value=ic.RatingValue.STRONG_UP)],
        )
        assert pair.comments[0].content == "turn note"
        assert pair.ratings[0].value is ic.RatingValue.STRONG_UP


class TestNewEvents:
    @pytest.mark.parametrize(
        "payload, expected_type",
        [
            ({"type": "workflow_ready_for_input"}, "WorkflowReadyForInputEvent"),
            ({"type": "waiting_evaluation_boundary"}, "WaitingEvaluationBoundaryEvent"),
            ({"type": "self_loop_delay"}, "SelfLoopDelayEvent"),
            ({"type": "self_loop_exhausted"}, "SelfLoopExhaustedEvent"),
            ({"type": "node_expired"}, "NodeExpiredEvent"),
            ({"type": "waiting_condition_matched"}, "WaitingConditionMatchedEvent"),
            ({"type": "guardrail_escalation_edge"}, "GuardrailEscalationEdgeEvent"),
            ({"type": "companion_step_boundary", "companion_thread_id": "0_companion_x"},
             "CompanionStepBoundaryEvent"),
        ],
    )
    def test_each_new_event_parses_to_its_class(self, payload, expected_type):
        assert type(parse_event(payload)).__name__ == expected_type

    def test_unknown_event_types_still_degrade_to_base_event(self):
        # Forward compatibility: a client is expected to lag the server.
        event = parse_event({"type": "some_event_from_2027"})
        assert type(event).__name__ == "BaseEvent"

    @pytest.mark.parametrize(
        "origin, expected",
        [
            ("0", "0"),
            ("0_companion_poller", "poller"),
            (None, None),
            ("0_companion_a_companion_b", "b"),  # rsplit: the last segment is the configured id
        ],
    )
    def test_thread_reference_id_derivation(self, origin, expected):
        assert parse_event({"type": "start_workflow", "origin_thread_id": origin}).thread_reference_id == expected

    def test_show_state_derives_from_its_own_thread_id(self):
        event = parse_event(
            {"type": "workflow_show_state", "thread_id": "0_companion_watcher", "origin_thread_id": "0"}
        )
        assert event.thread_reference_id == "watcher"

    def test_self_loop_outcome_values_are_constrained(self):
        assert parse_event({"type": "self_loop_exhausted", "outcome": "max_retries"}).outcome == "max_retries"
        # An unknown outcome fails the typed model and falls back rather than silently accepting.
        assert type(parse_event({"type": "self_loop_exhausted", "outcome": "nope"})).__name__ == "BaseEvent"

    def test_background_boundary_events_are_persisted_only_when_they_transitioned(self):
        # A non-transitioning boundary recurs on every background pass; persisting it would grow the
        # run record without bound.
        assert should_persist_background_event(WaitingEvaluationBoundaryEvent(transitioned=False)) is False
        assert should_persist_background_event(WaitingEvaluationBoundaryEvent(transitioned=True)) is True
        assert should_persist_background_event(CompanionStepBoundaryEvent(companion_thread_id="x")) is True


class TestBedrock:
    def test_default_model_is_the_cheap_tier(self):
        assert ic.BedrockLLMConfig().model is ic.BEDROCKModel.GLM_4_7_FLASH

    def test_model_is_a_closed_enum(self):
        # Previously a free-form string, which let a typo reach the server as a 422.
        with pytest.raises(ValidationError):
            ic.BedrockLLMConfig(model="not-a-bedrock-model")

    def test_credentials_are_plain_strings_matching_the_server(self):
        cfg = ic.BedrockLLMConfig(api_key="bearer-token", region="us-west-2", aws_access_key_id="AKIA")
        dumped = cfg.model_dump()
        assert dumped["api_key"] == "bearer-token"
        assert dumped["region"] == "us-west-2"
        assert dumped["aws_access_key_id"] == "AKIA"

    def test_discriminator_round_trips_through_the_union(self):
        adapter = TypeAdapter(ic.LLMConfigUnion)
        assert isinstance(adapter.validate_python({"type": "bedrock_llm"}), ic.BedrockLLMConfig)


class TestModelCatalogue:
    """Pins on the model lists. See this module's docstring for why these are worth having."""

    def test_models_deleted_server_side_are_gone(self):
        dead = {
            "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b",
            "gemini-2.0-flash", "gemini-2.0-flash-lite",
            "claude-opus-4-20250514", "claude-sonnet-4-20250514",
            "gpt-5-chat-latest", "gpt-5.1-chat-latest",
        }
        offered = (
            {m.value for m in ic.GOOGLEModel}
            | {m.value for m in ic.ANTHROPICModel}
            | {m.value for m in ic.OPENAIModel}
        )
        assert not (offered & dead), f"offering models the server rejects: {sorted(offered & dead)}"

    @pytest.mark.parametrize(
        "enum_cls, value",
        [
            (ic.ANTHROPICModel, "claude-opus-5"),
            (ic.ANTHROPICModel, "claude-sonnet-5"),
            (ic.ANTHROPICModel, "claude-fable-5"),
            (ic.ANTHROPICModel, "claude-haiku-4-5"),
            (ic.GOOGLEModel, "gemini-3.6-flash"),
            (ic.GOOGLEModel, "gemini-2.5-flash-lite"),
            (ic.OPENAIModel, "gpt-5.4-pro"),
            (ic.OPENAIModel, "gpt-5.2-pro"),
        ],
    )
    def test_live_models_are_offered(self, enum_cls, value):
        assert value in {m.value for m in enum_cls}

    def test_capability_data_is_not_selectable_as_a_model(self):
        # Upstream keeps these out of the member list with `enum.nonmember`, which is 3.11+. The
        # mirror hoists them to module scope for 3.10 support; either way they must not appear as
        # models a user could pick.
        for enum_cls in (ic.OPENAIModel, ic.ANTHROPICModel, ic.GOOGLEModel):
            assert not any(m.name.isupper() and "THINKING" in m.name for m in enum_cls)
            assert not any("REASONING" in m.name for m in enum_cls)

    @pytest.mark.parametrize(
        "model, effort, expected",
        [
            ("gpt-5.4-pro", "low", "medium"),      # clamped: pro models reject 'low'
            ("gpt-5.2-pro", "minimal", "medium"),
            ("gpt-5.4-pro", "high", "high"),       # already acceptable
            ("gpt-5", "low", "low"),               # non-pro models accept the full range
            (None, "low", "low"),
            ("gpt-5.4-pro", None, None),
        ],
    )
    def test_reasoning_effort_is_clamped_for_pro_models(self, model, effort, expected):
        assert ic.resolve_reasoning_effort(model, effort) == expected


class TestForwardCompatibility:
    """The divergences from upstream that exist so a lagging client keeps working."""

    def test_hydrated_config_accepts_unknown_node_types(self):
        # Typing `node_configs` as upstream's `List[NodeConfig]` would reject this. A client is
        # expected to lag the server, so an unknown node type must not fail the whole workflow.
        hydrated = ic.WorkflowConfigFullyHydrated.model_validate(
            {"node_configs": [{"type": "some_future_node_type", "name": "n"}]}
        )
        assert len(hydrated.node_configs) == 1

    def test_run_output_events_accept_any_shape(self):
        # Events arrive as typed models on a live runtime and as plain dicts once stored.
        output = ic.BaseRunOutput(events=[{"type": "x"}, {"type": "unknown_2027"}])
        assert len(output.events) == 2

    def test_events_field_schema_stays_untyped(self):
        # Pinned: typing this field would balloon the published JSON schema and reject stored events.
        schema = ic.BaseRunOutput.model_json_schema()["properties"]["events"]
        assert schema["type"] == "array"
        assert schema.get("items") == {}


class TestMirrorPlacement:
    """Names and locations that upstream owns; drifting from them makes future syncs manual."""

    def test_workflow_default_llm_config_is_the_upstream_name(self):
        assert ic.WorkflowDefaultLLMConfig.model_fields["type"].default == "global_default_llm"
        assert not hasattr(ic, "GlobalDefaultLLMConfig")

    def test_base_entity_config_lives_in_base_defs(self):
        from interactly_configs.base_defs import BaseEntityConfig

        assert ic.BaseEntityConfig is BaseEntityConfig

    def test_workflow_command_lives_in_workflow_run(self):
        from interactly_configs.workflow_run import WorkflowCommand

        assert ic.WorkflowCommand is WorkflowCommand
