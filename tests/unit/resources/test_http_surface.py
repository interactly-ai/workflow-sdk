"""Wire-level coverage for the HTTP surface added to follow the 2026-10 server.

Every response body below is a shape captured from the dev server, not one written to suit the client.
That is the rule this suite exists to keep: a mock encoding a shape the server never produces keeps a
broken method green indefinitely.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    WorkflowClient,
)

TEST_BASE_URL = "http://localhost:8611"


@pytest.fixture
def client() -> WorkflowClient:
    return WorkflowClient(
        api_key="test-api-key", team_id="test-team-id", user_id="test-user-id", base_url=TEST_BASE_URL, max_retries=0
    )


@pytest.fixture
def aclient() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(
        api_key="test-api-key", team_id="test-team-id", user_id="test-user-id", base_url=TEST_BASE_URL, max_retries=0
    )


def _recorder(calls: List[Dict[str, Any]], payload: Any, status: int = 200):
    """A respx side effect that records each outgoing request and answers with ``payload``."""

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "body": json.loads(request.content) if request.content else None,
            }
        )
        return httpx.Response(status, json=payload)

    return _handler


# --------------------------------------------------------------------------------------------- #
# Captured from dev                                                                               #
# --------------------------------------------------------------------------------------------- #

_TOOL_DOC = {
    "_id": "6a00000000000000000000aa",
    "team_id": "team",
    "tool_config": {"type": "external_api", "name": "Lookup (Clone)", "api_endpoint": "https://x"},
}

_LINTS = {
    "workflow_id": "6aa8aa9ba6bf56957e81217c",
    "version_number": None,
    "super_nodes_expanded": True,
    "warnings": ["Node 'Chat' reads [[thread_bg.x]], but no companion thread is named 'bg'."],
}

_FINDING = {
    "code": "max_consecutive_tool_calls",
    "severity": "warning",
    "message": "max_consecutive_tool_calls is 2. The realtime session runs its own tool loop.",
    "description": "max_consecutive_tool_calls is 2. The realtime session runs its own tool loop. (at Verify caller)",
    "node_logical_id": "node_3c0b4420-3797-4f6f-b04f-4c91c7f4c47e",
    "node_name": "Verify caller",
    "edge_logical_id": None,
    "super_node_path": None,
}
_REALTIME = {
    "workflow_id": "6aa8aa9ba6bf56957e81217c",
    "version_number": None,
    "model": "gpt-realtime",
    "super_nodes_expanded": True,
    "supported": True,
    "summary": "Realtime-ready with 1 warning(s).",
    "blockers": [],
    "warnings": [_FINDING],
    "indeterminate": [],
}

_COUNTER_NONE = {"message": None, "counter_workflow": None, "generation": None}
_GENERATION = {
    "source_workflow_id": "6aa8aa9ba6bf56957e81217c",
    "source_version_number": None,
    "status": "pending",
    "instructions": None,
    "provider": "gemini",
    "num_cases_requested": 5,
    "num_cases_generated": 0,
    "generated_workflow_id": None,
    "generated_version_number": None,
    "warnings": [],
    "error": None,
    "started_at": "2026-10-02T21:00:00Z",
    "updated_at": "2026-10-02T21:00:00Z",
}

_FUNCTION = {
    "id": "benefits.estimate_member_cost_share",
    "qualified_name": "common.workflow_functions.benefits:estimate_member_cost_share",
    "name": "estimate_member_cost_share",
    "summary": "Estimate what a member will owe for a set of services under their plan.",
    "signature": "Estimate a member's out-of-pocket cost for one or more services.",
    "args_schema": {"type": "object", "properties": {"service_lines": {"type": "array"}}},
    "extra_config_schema": None,
    "category": "benefits",
    "side_effect": "none",
    "tenancy": "static",
    "is_async": True,
    "source_ref": "common/workflow_functions/benefits.py:329",
    "deprecated_by": None,
}


# --------------------------------------------------------------------------------------------- #
# Tools                                                                                           #
# --------------------------------------------------------------------------------------------- #


class TestToolClone:
    @respx.mock
    def test_always_sends_a_body_even_without_a_name(self, client):
        # The server declares a request body; an empty dict would be dropped before sending, which the
        # server answers with a 422. A null name asks for the default "<source> (Clone)".
        calls: List[Dict[str, Any]] = []
        respx.post(f"{TEST_BASE_URL}/v1/tools/t1/clone").mock(side_effect=_recorder(calls, {"tool": _TOOL_DOC}))

        cloned = client.tools.clone("t1")

        assert calls == [{"method": "POST", "path": "/v1/tools/t1/clone", "params": {}, "body": {"name": None}}]
        assert cloned.id == _TOOL_DOC["_id"]
        assert cloned.name == "Lookup (Clone)"

    @respx.mock
    def test_sends_a_name_when_given(self, client):
        calls: List[Dict[str, Any]] = []
        respx.post(f"{TEST_BASE_URL}/v1/tools/t1/clone").mock(side_effect=_recorder(calls, {"tool": _TOOL_DOC}))

        client.tools.clone("t1", name="Lookup v2")

        assert calls[0]["body"] == {"name": "Lookup v2"}

    @respx.mock
    def test_an_inbuilt_tool_cannot_be_cloned(self, client):
        respx.post(f"{TEST_BASE_URL}/v1/tools/calculator/clone").mock(
            return_value=httpx.Response(403, json={"message": "Inbuilt tools cannot be cloned."})
        )
        with pytest.raises(PermissionDeniedError):
            client.tools.clone("calculator")

    @respx.mock
    async def test_async(self, aclient):
        respx.post(f"{TEST_BASE_URL}/v1/tools/t1/clone").mock(return_value=httpx.Response(200, json={"tool": _TOOL_DOC}))
        assert (await aclient.tools.clone("t1")).id == _TOOL_DOC["_id"]


class TestCodebaseFunctions:
    @respx.mock
    def test_the_catalogue_parses(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/tools/codebase-functions").mock(
            return_value=httpx.Response(
                200, json={"codebase_functions": [_FUNCTION], "total_count": 1, "unavailable_modules": {}}
            )
        )
        catalogue = client.tools.codebase_functions()
        assert catalogue.total_count == 1
        assert catalogue.codebase_functions[0].id == "benefits.estimate_member_cost_share"
        assert catalogue.codebase_functions[0].side_effect == "none"

    @respx.mock
    def test_one_function_is_unwrapped_from_its_envelope(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/tools/codebase-functions/benefits.estimate_member_cost_share").mock(
            return_value=httpx.Response(200, json={"function_id": _FUNCTION["id"], "function": _FUNCTION})
        )
        function = client.tools.get_codebase_function("benefits.estimate_member_cost_share")
        assert function.qualified_name == _FUNCTION["qualified_name"]
        assert function.args_schema["properties"].keys() == {"service_lines"}

    @respx.mock
    def test_an_unknown_function_is_not_found_with_a_reason(self, client):
        body = {"message": "No codebase function 'no.such'.", "reason": "no function is registered under that id"}
        respx.get(f"{TEST_BASE_URL}/v1/tools/codebase-functions/no.such").mock(return_value=httpx.Response(404, json=body))
        with pytest.raises(NotFoundError) as caught:
            client.tools.get_codebase_function("no.such")
        assert caught.value.body["reason"] == body["reason"]

    @respx.mock
    def test_a_non_staff_caller_is_refused(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/tools/codebase-functions").mock(
            return_value=httpx.Response(403, json={"detail": "Codebase-function tools are available to Interactly staff only."})
        )
        with pytest.raises(PermissionDeniedError):
            client.tools.codebase_functions()


class TestToolResponsesCarryWarnings:
    @respx.mock
    def test_import_surfaces_the_server_warnings(self, client):
        warning = "Variable 'patient_id' is not defined for this team."
        respx.post(f"{TEST_BASE_URL}/v1/tools/import").mock(
            return_value=httpx.Response(200, json={"tool": _TOOL_DOC, "warnings": [warning]})
        )
        tool = client.tools.import_bundle({"tool_config": {}})
        assert tool.warnings == [warning]
        assert tool.id == _TOOL_DOC["_id"]

    @respx.mock
    def test_a_plain_read_has_no_warnings(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/tools/t1").mock(return_value=httpx.Response(200, json={"tool": _TOOL_DOC}))
        assert client.tools.get("t1").warnings == []

    @respx.mock
    def test_export_keeps_required_dynamic_variables(self, client):
        bundle = {"tool_config": {}, "redactions": [], "required_dynamic_variables": ["patient_id"], "warnings": []}
        respx.get(f"{TEST_BASE_URL}/v1/tools/t1/export").mock(return_value=httpx.Response(200, json=bundle))
        assert client.tools.export("t1")["required_dynamic_variables"] == ["patient_id"]

    @respx.mock
    def test_a_refusal_reaches_the_caller_as_a_refusal(self, client):
        # The server used to report a role-gate refusal on PATCH as a 500.
        respx.patch(f"{TEST_BASE_URL}/v1/tools/t1").mock(
            return_value=httpx.Response(403, json={"detail": "Codebase-function tools are available to Interactly staff only."})
        )
        with pytest.raises(PermissionDeniedError):
            client.tools.update("t1", tool_config={"type": "codebase_function", "function_id": "f"})


class TestToolUpdateSendsOnlyWhatWasSet:
    """The server merges a tool PATCH onto the stored config, so every key sent overwrites."""

    @respx.mock
    def test_a_typed_config_sends_only_its_set_fields(self, client):
        from interactly.configs import InlinePythonToolConfig

        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/tools/t1").mock(side_effect=_recorder(calls, {"tool": _TOOL_DOC}))

        client.tools.update("t1", tool_config=InlinePythonToolConfig(description="New", code="def f(): ..."))

        assert calls[0]["body"] == {"description": "New", "code": "def f(): ..."}

    @respx.mock
    def test_the_tool_identity_and_unset_fields_are_never_sent(self, client):
        from interactly.configs import InlinePythonToolConfig

        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/tools/t1").mock(side_effect=_recorder(calls, {"tool": _TOOL_DOC}))

        client.tools.update("t1", tool_config=InlinePythonToolConfig(code="def f(): ..."))

        assert not {"logical_id", "name", "signature", "args_schema"} & calls[0]["body"].keys()

    @respx.mock
    def test_an_explicit_none_is_sent(self, client):
        from interactly.configs import InlinePythonToolConfig

        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/tools/t1").mock(side_effect=_recorder(calls, {"tool": _TOOL_DOC}))

        client.tools.update("t1", tool_config=InlinePythonToolConfig(description=None))

        assert calls[0]["body"] == {"description": None}

    @respx.mock
    def test_a_dict_is_sent_as_given(self, client):
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/tools/t1").mock(side_effect=_recorder(calls, {"tool": _TOOL_DOC}))

        client.tools.update("t1", tool_config={"type": "inline_python", "name": None})

        assert calls[0]["body"] == {"type": "inline_python", "name": None}

    @respx.mock
    async def test_async(self, aclient):
        from interactly.configs import InlinePythonToolConfig

        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/tools/t1").mock(side_effect=_recorder(calls, {"tool": _TOOL_DOC}))

        await aclient.tools.update("t1", tool_config=InlinePythonToolConfig(code="def f(): ..."))

        assert calls[0]["body"] == {"code": "def f(): ..."}


# --------------------------------------------------------------------------------------------- #
# Nodes and workflows: warnings                                                                   #
# --------------------------------------------------------------------------------------------- #


class TestNodeAndWorkflowWarnings:
    @respx.mock
    def test_a_created_node_carries_its_warnings(self, client):
        warning = "Tool result mapping writes 'x', which no node reads."
        node_doc = {"_id": "n1", "node_config": {"type": "no_op", "name": "Entry"}}
        respx.post(f"{TEST_BASE_URL}/v1/nodes").mock(
            return_value=httpx.Response(200, json={"node": node_doc, "warnings": [warning]})
        )
        node = client.nodes.create(node_config={"type": "no_op", "name": "Entry"})
        assert (node.id, node.warnings) == ("n1", [warning])

    @respx.mock
    def test_a_node_refusal_is_not_reported_as_a_server_fault(self, client):
        respx.post(f"{TEST_BASE_URL}/v1/nodes").mock(
            return_value=httpx.Response(403, json={"detail": "Codebase-function tools are available to Interactly staff only."})
        )
        with pytest.raises(PermissionDeniedError):
            client.nodes.create(node_config={"type": "no_op", "name": "Entry"})

    @respx.mock
    def test_a_created_workflow_carries_its_warnings(self, client):
        warning = "Waiting condition on 'Chat' can never fire."
        workflow_doc = {"_id": "w1", "workflow_config": {"name": "W"}}
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(
                200, json={"workflow": workflow_doc, "execution_url": "/x", "warnings": [warning]}
            )
        )
        workflow = client.workflows.create(name="W")
        assert (workflow.id, workflow.execution_url, workflow.warnings) == ("w1", "/x", [warning])


# --------------------------------------------------------------------------------------------- #
# Workflow analysis                                                                               #
# --------------------------------------------------------------------------------------------- #


class TestLints:
    @respx.mock
    def test_defaults_to_the_active_version(self, client):
        calls: List[Dict[str, Any]] = []
        respx.get(f"{TEST_BASE_URL}/v1/workflows/w1/lints").mock(side_effect=_recorder(calls, _LINTS))

        report = client.workflows.lints("w1")

        assert calls[0]["params"] == {}
        assert report.super_nodes_expanded is True
        assert report.warnings == _LINTS["warnings"]

    @respx.mock
    def test_a_version_can_be_named(self, client):
        calls: List[Dict[str, Any]] = []
        respx.get(f"{TEST_BASE_URL}/v1/workflows/w1/lints").mock(side_effect=_recorder(calls, _LINTS))
        client.workflows.lints("w1", version_number=3)
        assert calls[0]["params"] == {"version_number": "3"}

    @respx.mock
    def test_a_missing_workflow_is_not_found(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/workflows/nope/lints").mock(
            return_value=httpx.Response(404, json={"message": "Workflow not found."})
        )
        with pytest.raises(NotFoundError):
            client.workflows.lints("nope")

    @respx.mock
    async def test_async(self, aclient):
        respx.get(f"{TEST_BASE_URL}/v1/workflows/w1/lints").mock(return_value=httpx.Response(200, json=_LINTS))
        assert (await aclient.workflows.lints("w1")).warnings == _LINTS["warnings"]


class TestRealtimeCompatibility:
    @respx.mock
    def test_the_model_is_sent_and_findings_are_typed(self, client):
        calls: List[Dict[str, Any]] = []
        respx.get(f"{TEST_BASE_URL}/v1/workflows/w1/realtime-compatibility").mock(
            side_effect=_recorder(calls, _REALTIME)
        )

        report = client.workflows.realtime_compatibility("w1", model="gpt-realtime")

        assert calls[0]["params"] == {"model": "gpt-realtime"}
        assert (report.supported, report.model, report.summary) == (True, "gpt-realtime", _REALTIME["summary"])
        assert report.warnings[0].node_name == "Verify caller"
        assert report.blockers == [] and report.indeterminate == []

    @respx.mock
    def test_no_parameters_by_default(self, client):
        calls: List[Dict[str, Any]] = []
        respx.get(f"{TEST_BASE_URL}/v1/workflows/w1/realtime-compatibility").mock(
            side_effect=_recorder(calls, {**_REALTIME, "model": None})
        )
        client.workflows.realtime_compatibility("w1")
        assert calls[0]["params"] == {}


class TestCounterWorkflow:
    @respx.mock
    def test_nothing_generated_yet(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/workflows/w1/counter-workflow").mock(
            return_value=httpx.Response(200, json=_COUNTER_NONE)
        )
        status = client.workflows.counter_workflow("w1")
        assert (status.counter_workflow, status.generation) == (None, None)

    @respx.mock
    def test_an_existing_counter_workflow_and_its_run(self, client):
        payload = {
            "message": None,
            "counter_workflow": {
                "workflow_id": "6aa8aa9ba6bf56957e81217d",
                "name": "Counter: bench",
                "active_version_number": 2,
                "case_count": 12,
                "generated_for_version_number": 1,
            },
            "generation": {**_GENERATION, "status": "completed", "num_cases_generated": 12},
        }
        respx.get(f"{TEST_BASE_URL}/v1/workflows/w1/counter-workflow").mock(return_value=httpx.Response(200, json=payload))
        status = client.workflows.counter_workflow("w1")
        assert status.counter_workflow.case_count == 12
        assert status.generation.status == "completed"

    @respx.mock
    def test_generate_sends_only_what_was_given(self, client):
        calls: List[Dict[str, Any]] = []
        respx.post(f"{TEST_BASE_URL}/v1/workflows/w1/counter-workflow/generate").mock(
            side_effect=_recorder(calls, {"message": None, "generation": _GENERATION})
        )

        state = client.workflows.generate_counter_workflow("w1", num_cases=5, provider="gemini")

        assert calls[0]["body"] == {"num_cases": 5, "new_workflow": False, "provider": "gemini"}
        assert (state.status, state.num_cases_requested) == ("pending", 5)

    @respx.mock
    def test_a_second_concurrent_generation_is_a_conflict(self, client):
        respx.post(f"{TEST_BASE_URL}/v1/workflows/w1/counter-workflow/generate").mock(
            return_value=httpx.Response(409, json={"message": "A generation is already running for this workflow."})
        )
        with pytest.raises(ConflictError):
            client.workflows.generate_counter_workflow("w1")


# --------------------------------------------------------------------------------------------- #
# Run listing window                                                                              #
# --------------------------------------------------------------------------------------------- #


class TestRunListWindow:
    @respx.mock
    def test_a_window_over_31_days_is_a_bad_request_with_the_server_message(self, client):
        from datetime import datetime, timezone

        message = "Date range should be less than or equal to 31 days"
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs").mock(return_value=httpx.Response(400, json={"message": message}))
        with pytest.raises(BadRequestError) as caught:
            client.runs.list(
                start=datetime(2026, 1, 1, tzinfo=timezone.utc), end=datetime(2026, 3, 1, tzinfo=timezone.utc)
            )
        assert message in str(caught.value)


# --------------------------------------------------------------------------------------------- #
# LLM config: keep the stored key                                                                 #
# --------------------------------------------------------------------------------------------- #


def _stored(config: Dict[str, Any]) -> Dict[str, Any]:
    return {"llm_config": {"_id": "c1", "name": "Main", "config": config}}


class TestPreserveApiKey:
    @respx.mock
    def test_an_admin_read_key_is_carried_onto_a_config_that_omits_it(self, client):
        stored = {"type": "openai_llm", "model": "gpt-5.4-mini", "api_key": "sk-stored"}
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(return_value=httpx.Response(200, json=_stored(stored)))
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(side_effect=_recorder(calls, _stored(stored)))

        client.llm_configs.update("c1", config={"type": "openai_llm", "model": "gpt-5.4"})

        assert calls[0]["body"]["config"]["api_key"] == "sk-stored"
        assert calls[0]["body"]["config"]["model"] == "gpt-5.4"

    @respx.mock
    def test_a_key_the_caller_supplies_wins(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(
            return_value=httpx.Response(200, json=_stored({"type": "openai_llm", "api_key": "sk-stored"}))
        )
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(side_effect=_recorder(calls, _stored({})))

        client.llm_configs.update("c1", config={"type": "openai_llm", "api_key": "sk-new"})

        assert calls[0]["body"]["config"]["api_key"] == "sk-new"

    @respx.mock
    def test_opting_out_sends_the_config_as_given_without_a_read(self, client):
        read = respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1")
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(side_effect=_recorder(calls, _stored({})))

        client.llm_configs.update("c1", config={"type": "openai_llm"}, preserve_api_key=False)

        assert not read.called
        assert "api_key" not in calls[0]["body"]["config"]

    @respx.mock
    def test_no_read_when_the_config_is_not_being_replaced(self, client):
        read = respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1")
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(return_value=httpx.Response(200, json=_stored({})))
        client.llm_configs.update("c1", name="Renamed")
        assert not read.called

    @respx.mock
    def test_a_key_is_not_carried_to_a_different_provider(self, client):
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(
            return_value=httpx.Response(200, json=_stored({"type": "openai_llm", "api_key": "sk-openai"}))
        )
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(side_effect=_recorder(calls, _stored({})))

        client.llm_configs.update("c1", config={"type": "anthropic_llm"})

        assert calls[0]["body"]["config"].get("api_key") is None

    @respx.mock
    def test_group_member_keys_follow_their_logical_id_not_their_position(self, client):
        stored = {
            "type": "llm_group",
            "llms": [
                {"type": "openai_llm", "logical_id": "a", "api_key": "sk-a"},
                {"type": "openai_llm", "logical_id": "b", "api_key": "sk-b"},
            ],
        }
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(return_value=httpx.Response(200, json=_stored(stored)))
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(side_effect=_recorder(calls, _stored(stored)))

        # Reordered, and a third member with an id the stored group never had.
        client.llm_configs.update(
            "c1",
            config={
                "type": "llm_group",
                "llms": [
                    {"type": "openai_llm", "logical_id": "b"},
                    {"type": "openai_llm", "logical_id": "a"},
                    {"type": "openai_llm", "logical_id": "c"},
                ],
            },
        )

        members = calls[0]["body"]["config"]["llms"]
        assert [m.get("api_key") for m in members] == ["sk-b", "sk-a", None]

    @respx.mock
    def test_a_non_admin_read_carries_nothing(self, client):
        # A non-admin is never shown the key, and the server preserves it for them itself.
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(
            return_value=httpx.Response(200, json=_stored({"type": "openai_llm", "api_key": None}))
        )
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(side_effect=_recorder(calls, _stored({})))

        client.llm_configs.update("c1", config={"type": "openai_llm"})

        assert calls[0]["body"]["config"].get("api_key") is None

    @respx.mock
    async def test_async(self, aclient):
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(
            return_value=httpx.Response(200, json=_stored({"type": "openai_llm", "api_key": "sk-stored"}))
        )
        calls: List[Dict[str, Any]] = []
        respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/c1").mock(side_effect=_recorder(calls, _stored({})))

        await aclient.llm_configs.update("c1", config={"type": "openai_llm"})

        assert calls[0]["body"]["config"]["api_key"] == "sk-stored"
