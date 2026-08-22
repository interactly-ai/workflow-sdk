"""Tests for interactly_configs.

Covers:
- WorkflowConfig: minimal instantiation and round-trip JSON
- EdgeConfig: discriminated union resolution for all 3 types
- LLMConfig: discriminated union resolution for all 6 providers
- BaseRunInput: dynamic_variables / runtime_variables
- SelectionMode.select(): random and sequence modes
- ConditionConfig: freeform and expression variants
- ToolConfig: all 4 tool types via discriminator
- ExternalAPIToolConfig: api_body JSON parsing validator
"""


import pytest

from interactly_configs import (
    AnthropicLLMConfig,
    AzureOpenAILLMConfig,
    AZUREOPENAIModel,
    BaseNodeConfig,
    BaseRunInput,
    CompanionEdgeConfig,
    ConditionalEdgeConfig,
    ConditionConfig,
    CustomLLMConfig,
    DirectEdgeConfig,
    DynamicMessagesConfig,
    EdgeConfig,
    EdgeType,
    ExternalAPIToolConfig,
    GoogleLLMConfig,
    InbuiltFunctionToolConfig,
    InlinePythonToolConfig,
    IntegrationAuthConfig,
    KnowledgeBaseToolConfig,
    LLMConfig,
    LLMGroupConfig,
    LLMProvider,
    MCPServerConfig,
    NodeCategory,
    NodeType,
    NoLLMConfig,
    OktaAuthConfig,
    OpenAILLMConfig,
    OperationMode,
    SelectionMode,
    StaticMessagesConfig,
    ToolConfig,
    ToolsConfig,
    ToolType,
    WorkflowCommand,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
    WorkflowDefaultLLMConfig,
    WorkflowExecutionStatus,
    WorkflowRunInput,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edge_payload(type_: str, **extra) -> dict:
    return {"type": type_, **extra}


def _llm_payload(type_: str, **extra) -> dict:
    return {"type": type_, **extra}


def _tool_payload(type_: str, **extra) -> dict:
    return {"type": type_, **extra}


# ---------------------------------------------------------------------------
# WorkflowConfig
# ---------------------------------------------------------------------------


class TestWorkflowConfig:
    def test_minimal_instantiation_has_logical_id(self):
        # Arrange / Act
        wf = WorkflowConfig()

        # Assert
        assert wf.logical_id is not None
        assert wf.logical_id.startswith("workflow_")

    def test_round_trip_json_preserves_name(self):
        # Arrange
        wf = WorkflowConfig(name="My Flow", description="Test workflow")

        # Act
        serialised = wf.model_dump_json()
        restored = WorkflowConfig.model_validate_json(serialised)

        # Assert
        assert restored.name == "My Flow"
        assert restored.description == "Test workflow"

    def test_nodes_and_edges_are_string_lists(self):
        # Arrange
        wf = WorkflowConfig(nodes=["abc123", "def456"], edges=["edge001"])

        # Act
        data = wf.model_dump()

        # Assert
        assert data["nodes"] == ["abc123", "def456"]
        assert data["edges"] == ["edge001"]

    def test_llms_config_defaults_to_no_llm(self):
        # Mirrors the server default (WorkflowConfig.llms_config defaults to NoLLMConfig).
        wf = WorkflowConfig()
        assert isinstance(wf.llms_config, NoLLMConfig)

    def test_fully_hydrated_empty_instantiation(self):
        hydrated = WorkflowConfigFullyHydrated()
        assert hydrated.workflow_config is None
        assert hydrated.node_configs == []
        assert hydrated.edge_configs == []

    def test_fully_hydrated_with_nodes_and_edges(self):
        node = BaseNodeConfig(name="Start")
        edge = DirectEdgeConfig(source_node_logical_id="n1", destination_node_logical_id="n2")
        hydrated = WorkflowConfigFullyHydrated(
            workflow_config=WorkflowConfig(name="Full"),
            node_configs=[node],
            edge_configs=[edge],
        )
        assert len(hydrated.node_configs) == 1
        assert len(hydrated.edge_configs) == 1


# ---------------------------------------------------------------------------
# EdgeConfig discriminated union
# ---------------------------------------------------------------------------


class TestEdgeConfig:
    def test_direct_edge_resolved(self):
        data = _edge_payload("direct")
        edge = DirectEdgeConfig(**data)
        assert edge.type == EdgeType.DIRECT.value

    def test_conditional_edge_resolved_via_union(self):
        data = _edge_payload("conditional")
        edge = ConditionalEdgeConfig(**data)
        assert isinstance(edge, ConditionalEdgeConfig)

    def test_companion_edge_resolved_via_union(self):
        data = _edge_payload("companion")
        edge = CompanionEdgeConfig(**data)
        assert isinstance(edge, CompanionEdgeConfig)

    @pytest.mark.parametrize(
        "payload, expected_class",
        [
            (_edge_payload("direct"), DirectEdgeConfig),
            (_edge_payload("conditional"), ConditionalEdgeConfig),
            (_edge_payload("companion"), CompanionEdgeConfig),
        ],
    )
    def test_discriminator_union_from_dict(self, payload, expected_class):
        # Pydantic resolves the correct subtype via the `type` discriminator
        from pydantic import TypeAdapter

        adapter = TypeAdapter(EdgeConfig)
        edge = adapter.validate_python(payload)
        assert isinstance(edge, expected_class)

    def test_conditional_edge_carries_condition(self):
        condition = ConditionConfig(condition_freeform="caller said yes")
        edge = ConditionalEdgeConfig(condition=condition)
        assert edge.condition.condition_freeform == "caller said yes"

    def test_edge_type_to_config_map_has_all_types(self):
        mapping = EdgeType.get_type_to_config_map()
        assert EdgeType.DIRECT in mapping
        assert EdgeType.CONDITIONAL in mapping
        assert EdgeType.COMPANION in mapping


# ---------------------------------------------------------------------------
# LLMConfig discriminated union
# ---------------------------------------------------------------------------


class TestLLMConfig:
    @pytest.mark.parametrize(
        "payload, expected_class",
        [
            (_llm_payload("azure_openai_llm"), AzureOpenAILLMConfig),
            (_llm_payload("openai_llm"), OpenAILLMConfig),
            (_llm_payload("google_llm"), GoogleLLMConfig),
            (_llm_payload("anthropic_llm"), AnthropicLLMConfig),
            (_llm_payload("custom_llm"), CustomLLMConfig),
            (_llm_payload("global_default_llm"), WorkflowDefaultLLMConfig),
        ],
    )
    def test_discriminator_resolves_correct_subtype(self, payload, expected_class):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(LLMConfig)
        llm = adapter.validate_python(payload)
        assert isinstance(llm, expected_class)

    def test_azure_openai_default_model(self):
        llm = AzureOpenAILLMConfig()
        assert llm.model == AZUREOPENAIModel.GPT_5_MINI
        assert llm.provider == LLMProvider.AZUREOPENAI

    def test_api_key_serialised_as_plain_string(self):
        llm = CustomLLMConfig(api_key="sk-secret")
        data = llm.model_dump()
        assert data["api_key"] == "sk-secret"

    def test_api_key_none_serialises_to_none(self):
        llm = AzureOpenAILLMConfig()
        data = llm.model_dump()
        assert data["api_key"] is None

    def test_temperature_bounds(self):
        llm = AzureOpenAILLMConfig(temperature=0.7)
        assert llm.temperature == 0.7

    def test_temperature_out_of_bounds_raises(self):
        with pytest.raises(Exception):
            AzureOpenAILLMConfig(temperature=1.5)

    def test_okta_auth_keyword_is_still_accepted(self):
        """The field was renamed to ``integration_auth`` upstream, provider-agnostically, and upstream
        kept ``okta_auth`` as a *validation* alias so previously saved configs keep deserializing. The
        mirror follows exactly: the old keyword is accepted on construction, and the value lands on the
        new attribute. Reading ``.okta_auth`` no longer works — on the server either — which is why this
        test asserts the shape of the migration rather than just that it parses.
        """
        llm = CustomLLMConfig(okta_auth=OktaAuthConfig(integration_id="okta-123"))
        assert llm.integration_auth.integration_id == "okta-123"
        assert not hasattr(llm, "okta_auth")

    def test_the_canonical_keyword_works_too(self):
        llm = CustomLLMConfig(integration_auth=IntegrationAuthConfig(integration_id="int-9"))
        assert llm.integration_auth.integration_id == "int-9"

    def test_the_old_class_name_is_the_same_class(self):
        """``OktaAuthConfig`` stays importable as an alias, matching upstream, so existing imports do not
        break even though the name the server leads with has changed."""
        assert OktaAuthConfig is IntegrationAuthConfig

    def test_llm_group_config_instantiation(self):
        group = LLMGroupConfig(
            llms=[AzureOpenAILLMConfig(), GoogleLLMConfig()],
            operation_mode=OperationMode.PARALLEL_SELECT_ONE,
        )
        assert len(group.llms) == 2
        assert group.operation_mode == OperationMode.PARALLEL_SELECT_ONE


# ---------------------------------------------------------------------------
# ToolConfig discriminated union
# ---------------------------------------------------------------------------


class TestToolConfig:
    @pytest.mark.parametrize(
        "payload, expected_class",
        [
            (_tool_payload("inbuilt_function"), InbuiltFunctionToolConfig),
            (_tool_payload("inline_python"), InlinePythonToolConfig),
            (_tool_payload("external_api"), ExternalAPIToolConfig),
            (_tool_payload("knowledge_base"), KnowledgeBaseToolConfig),
        ],
    )
    def test_discriminator_resolves_correct_subtype(self, payload, expected_class):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ToolConfig)
        tool = adapter.validate_python(payload)
        assert isinstance(tool, expected_class)

    def test_external_api_body_parsed_from_json_string(self):
        tool = ExternalAPIToolConfig(
            api_endpoint="https://api.example.com/v1/data",
            api_body='{"key": "value"}',
        )
        assert tool.api_body == {"key": "value"}

    def test_external_api_body_empty_string_becomes_none(self):
        tool = ExternalAPIToolConfig(api_body="   ")
        assert tool.api_body is None

    def test_external_api_body_invalid_json_raises(self):
        with pytest.raises(Exception, match="valid JSON"):
            ExternalAPIToolConfig(api_body="{not json}")

    def test_tools_config_wraps_multiple_tools(self):
        tc = ToolsConfig(
            tools=[
                InbuiltFunctionToolConfig(tool_id="search"),
                KnowledgeBaseToolConfig(target_knowledge_base_ids=["kb-1", "kb-2"]),
            ]
        )
        assert len(tc.tools) == 2

    def test_mcp_server_config(self):
        mcp = MCPServerConfig(name="My MCP", server_url="https://mcp.example.com/mcp")
        assert mcp.server_url == "https://mcp.example.com/mcp"


# ---------------------------------------------------------------------------
# BaseRunInput
# ---------------------------------------------------------------------------


class TestBaseRunInput:
    def test_default_empty_dicts(self):
        run_input = BaseRunInput()
        assert run_input.dynamic_variables == {}
        assert run_input.runtime_variables == {}
        assert run_input.miscellaneous == {}

    def test_accepts_arbitrary_dynamic_variables(self):
        run_input = BaseRunInput(
            dynamic_variables={"patient_name": "Alice", "dob": "1990-01-01"},
            runtime_variables={"session_id": "sess-42"},
        )
        assert run_input.dynamic_variables["patient_name"] == "Alice"
        assert run_input.runtime_variables["session_id"] == "sess-42"

    def test_round_trip_json(self):
        run_input = BaseRunInput(dynamic_variables={"key": "val"})
        restored = BaseRunInput.model_validate_json(run_input.model_dump_json())
        assert restored.dynamic_variables == {"key": "val"}


# ---------------------------------------------------------------------------
# SelectionMode helper
# ---------------------------------------------------------------------------


class TestSelectionMode:
    def test_random_returns_item_from_list(self):
        result = SelectionMode.RANDOM.select(["a", "b", "c"])
        assert result in ["a", "b", "c"]

    def test_sequence_returns_next_item(self):
        result = SelectionMode.SEQUENCE.select(["x", "y", "z"], prev_index=0)
        assert result == "y"

    def test_sequence_clamps_at_last_item(self):
        result = SelectionMode.SEQUENCE.select(["x", "y", "z"], prev_index=10)
        assert result == "z"

    def test_empty_list_returns_none(self):
        result = SelectionMode.RANDOM.select([])
        assert result is None


# ---------------------------------------------------------------------------
# ConditionConfig
# ---------------------------------------------------------------------------


class TestConditionConfig:
    def test_freeform_condition(self):
        c = ConditionConfig(condition_freeform="user agreed to terms")
        assert c.condition_freeform == "user agreed to terms"
        assert c.condition_expression is None

    def test_expression_condition(self):
        c = ConditionConfig(condition_expression="{{age}} >= 18")
        assert c.condition_expression == "{{age}} >= 18"

    def test_with_static_messages(self):
        c = ConditionConfig(
            condition_freeform="positive response",
            static_messages_config=StaticMessagesConfig(static_messages=["Great!", "Awesome!"]),
        )
        assert len(c.static_messages_config.static_messages) == 2

    def test_with_dynamic_messages(self):
        c = ConditionConfig(
            condition_freeform="user wants appointment",
            dynamic_messages_config=DynamicMessagesConfig(dynamic_message_prompt="Acknowledge the appointment request"),
        )
        assert c.dynamic_messages_config.dynamic_message_prompt == "Acknowledge the appointment request"


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestEnums:
    def test_node_type_values_are_strings(self):
        assert NodeType.SAY_LLM == "say_llm"
        assert NodeType.END_CONVERSATION == "end_conversation"

    def test_node_category_values(self):
        assert NodeCategory.SYSTEM == "System"
        assert NodeCategory.LLM == "LLM"

    def test_tool_type_list_has_four_members(self):
        assert len(ToolType.list()) == 4

    def test_tool_type_is_valid(self):
        assert ToolType.is_valid("external_api")
        assert not ToolType.is_valid("unknown_type")


# ---------------------------------------------------------------------------
# WorkflowCommand (A-1)
# ---------------------------------------------------------------------------


class TestWorkflowCommand:
    @pytest.mark.parametrize(
        "member, expected_value",
        [
            (WorkflowCommand.START, "start"),
            (WorkflowCommand.DATA, "data"),
            (WorkflowCommand.RESUME, "resume"),
            (WorkflowCommand.PAUSE, "pause"),
            (WorkflowCommand.STOP, "stop"),
        ],
    )
    def test_all_values_round_trip(self, member, expected_value):
        # Arrange / Act / Assert
        assert member.value == expected_value
        assert WorkflowCommand(expected_value) is member

    def test_is_string_enum(self):
        assert isinstance(WorkflowCommand.START, str)

    def test_has_five_members(self):
        assert len(WorkflowCommand) == 5


# ---------------------------------------------------------------------------
# WorkflowRunInput (A-2)
# ---------------------------------------------------------------------------


class TestWorkflowRunInput:
    def test_default_command_is_start(self):
        # Arrange / Act
        run_input = WorkflowRunInput()

        # Assert
        assert run_input.command == WorkflowCommand.START

    def test_inherits_base_run_input_fields(self):
        # Arrange / Act
        run_input = WorkflowRunInput(
            dynamic_variables={"name": "Alice"},
            runtime_variables={"session": "s1"},
        )

        # Assert — fields from BaseRunInput are present
        assert run_input.dynamic_variables["name"] == "Alice"
        assert run_input.runtime_variables["session"] == "s1"
        assert run_input.miscellaneous == {}

    def test_model_dump_contains_all_expected_keys(self):
        # Arrange
        run_input = WorkflowRunInput(
            command=WorkflowCommand.DATA,
            workflow_id="wf-abc",
            version_number=2,
            run_by="test-runner",
            dynamic_variables={"key": "val"},
        )

        # Act
        data = run_input.model_dump()

        # Assert — server-expected fields are all present
        assert data["command"] == "data"
        assert data["workflow_id"] == "wf-abc"
        assert data["version_number"] == 2
        assert data["run_by"] == "test-runner"
        assert data["dynamic_variables"] == {"key": "val"}

    def test_optional_fields_default_to_none(self):
        # Arrange / Act
        data = WorkflowRunInput().model_dump()

        # Assert — matches the WorkflowRunInput contract
        assert data["workflow_id"] is None
        assert data["version_number"] == 0  # 0 == initial version (default)
        assert data["run_by"] is None
        # The essential interactive-turn field must be present and default to empty.
        assert data["thread_to_node_inputs"] == {}

    def test_round_trip_json_preserves_command(self):
        # Arrange
        run_input = WorkflowRunInput(command=WorkflowCommand.STOP)

        # Act
        restored = WorkflowRunInput.model_validate_json(run_input.model_dump_json())

        # Assert
        assert restored.command == WorkflowCommand.STOP


# ---------------------------------------------------------------------------
# WorkflowExecutionStatus (A-3)
# ---------------------------------------------------------------------------


class TestWorkflowExecutionStatus:
    @pytest.mark.parametrize(
        "status",
        [
            WorkflowExecutionStatus.COMPLETED,
            WorkflowExecutionStatus.FAILED,
            WorkflowExecutionStatus.CANCELLED,
            WorkflowExecutionStatus.ABORTED_LOOPING_RISK,
        ],
    )
    def test_is_terminal_returns_true_for_terminal_statuses(self, status):
        assert WorkflowExecutionStatus.is_terminal(status) is True

    @pytest.mark.parametrize(
        "status",
        [
            WorkflowExecutionStatus.NOT_STARTED,
            WorkflowExecutionStatus.STARTED,
            WorkflowExecutionStatus.RUNNING,
            WorkflowExecutionStatus.PAUSED,
            WorkflowExecutionStatus.WAITING_FOR_USER_INPUT,
        ],
    )
    def test_is_terminal_returns_false_for_active_statuses(self, status):
        assert WorkflowExecutionStatus.is_terminal(status) is False

    def test_has_nine_members(self):
        assert len(WorkflowExecutionStatus) == 9

    def test_is_string_enum(self):
        assert isinstance(WorkflowExecutionStatus.RUNNING, str)


# ---------------------------------------------------------------------------
# WorkflowConfig.miscellaneous guard keys (A-4)
# ---------------------------------------------------------------------------


class TestWorkflowConfigMiscellaneousGuardKeys:
    def test_accepts_consecutive_conditional_edges_max_limit(self):
        # Arrange / Act — should not raise
        wf = WorkflowConfig(miscellaneous={"consecutive_conditional_edges_max_limit": "5"})

        # Assert
        assert wf.miscellaneous["consecutive_conditional_edges_max_limit"] == "5"

    def test_accepts_no_consecutive_conditional_edge_flag(self):
        # Arrange / Act — should not raise
        wf = WorkflowConfig(
            miscellaneous={
                "no_consecutive_conditional_edge_after_reverse_conditional_edge_taken": "false"
            }
        )

        # Assert
        assert (
            wf.miscellaneous["no_consecutive_conditional_edge_after_reverse_conditional_edge_taken"]
            == "false"
        )

    def test_miscellaneous_accepts_both_guard_keys_together(self):
        # Arrange
        guard_keys = {
            "consecutive_conditional_edges_max_limit": "3",
            "no_consecutive_conditional_edge_after_reverse_conditional_edge_taken": "true",
        }

        # Act
        wf = WorkflowConfig(miscellaneous=guard_keys)

        # Assert
        assert len(wf.miscellaneous) == 2
