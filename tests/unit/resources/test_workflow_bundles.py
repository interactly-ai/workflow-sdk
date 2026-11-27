"""Workflow export and import with their secrets, the usage reports, and a version's settings, on the wire.

Every answer replayed here was captured from a workflow-service (``fixtures/workflow_bundles.json``), with its ids
replaced: a mock encoding a shape the server never produces keeps a broken method green. The exported workflow has one
HTTP Request node whose ``Authorization`` header is a made-up value.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
    UsageReport,
    Workflow,
    WorkflowClient,
    WorkflowVersion,
)
from interactly.resources.workflows.versions import AsyncWorkflowVersionsResource, WorkflowVersionsResource

BASE = "http://localhost:8611"
ANSWERS: Dict[str, Dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "workflow_bundles.json").read_text()
)
WORKFLOW = ANSWERS["export"]["body"]["source_workflow_id"]
SECRET_PATH = "versions.0.workflow_config.node_configs.0.headers.Authorization"


def _client() -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _aclient() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _replay(calls: List[httpx.Request], name: str):
    """Answer every request with one captured answer, recording the requests."""

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(ANSWERS[name]["status"], json=ANSWERS[name]["body"])

    return _handler


def _body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None


def _header(bundle: Dict[str, Any]) -> Any:
    return bundle["versions"][0]["workflow_config"]["node_configs"][0]["headers"]["Authorization"]


class TestExport:
    @respx.mock
    def test_a_default_export_asks_for_no_secrets_and_lists_what_it_cleared(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/export").mock(side_effect=_replay(calls, "export"))

        # Act
        bundle = _client().workflows.export(WORKFLOW, version_numbers=[0], active_version_number=0)

        # Assert
        assert dict(calls[0].url.params.multi_items()) == {"version_numbers": "0", "active_version_number": "0"}
        assert (bundle["secrets_included"], _header(bundle)) == (False, "")
        assert [(r["path"], r["reason"], r["node_name"]) for r in bundle["redactions"]] == [
            (SECRET_PATH, "sensitive header", "Ping")
        ]

    @respx.mock
    def test_include_secrets_keeps_them_in_the_bundle(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/export").mock(side_effect=_replay(calls, "export_with_secrets"))

        # Act
        bundle = _client().workflows.export(
            WORKFLOW, version_numbers=[0], active_version_number=0, include_secrets=True
        )

        # Assert
        assert calls[0].url.params["include_secrets"] == "true"
        assert (bundle["secrets_included"], _header(bundle)) == (True, "Bearer sdk-probe-not-a-secret")

    @respx.mock
    def test_a_viewer_asking_for_the_secrets_is_refused(self):
        # Arrange
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/export").mock(side_effect=_replay([], "export_secrets_viewer"))

        # Act / Assert
        with pytest.raises(PermissionDeniedError, match="can't export a workflow's secrets"):
            _client().workflows.export(WORKFLOW, version_numbers=[0], active_version_number=0, include_secrets=True)


class TestImport:
    @respx.mock
    def test_secret_overrides_go_with_the_bundle(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflows/import/bundle").mock(side_effect=_replay(calls, "import_with_overrides"))
        bundle = ANSWERS["export"]["body"]

        # Act
        workflow = _client().workflows.import_bundle(
            bundle, workflow_name="Copy", secret_overrides={SECRET_PATH: "Bearer restored"}
        )

        # Assert
        assert _body(calls[0]) == {
            "bundle": bundle,
            "workflow_name": "Copy",
            "secret_overrides": {SECRET_PATH: "Bearer restored"},
        }
        assert isinstance(workflow, Workflow)
        assert workflow.warnings == []

    @pytest.mark.parametrize("overrides", [None, {}])
    @respx.mock
    def test_without_overrides_none_are_sent_and_the_workflow_warns_of_each_secret_left_empty(self, overrides):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflows/import/bundle").mock(side_effect=_replay(calls, "import_without_overrides"))

        # Act
        workflow = _client().workflows.import_bundle(ANSWERS["export"]["body"], secret_overrides=overrides)

        # Assert
        assert "secret_overrides" not in _body(calls[0])
        assert workflow.warnings and "were not supplied and are still empty (Ping)" in workflow.warnings[0]

    @respx.mock
    def test_an_override_for_a_path_the_export_did_not_list_is_refused_with_the_path(self):
        # Arrange
        respx.post(f"{BASE}/v1/workflows/import/bundle").mock(side_effect=_replay([], "import_unknown_path"))

        # Act
        with pytest.raises(UnprocessableEntityError, match="only be supplied for values the export listed") as err:
            _client().workflows.import_bundle(
                ANSWERS["export"]["body"], secret_overrides={"versions.0.workflow_config.nope": "x"}
            )

        # Assert
        assert err.value.body["field_errors"] == ["versions.0.workflow_config.nope"]

    @respx.mock
    async def test_the_async_client_exports_and_imports_with_secrets(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/export").mock(side_effect=_replay(calls, "export"))
        respx.post(f"{BASE}/v1/workflows/import/bundle").mock(side_effect=_replay(calls, "import_with_overrides"))
        client = _aclient()

        # Act
        bundle = await client.workflows.export(WORKFLOW, version_numbers=[0], active_version_number=0)
        await client.workflows.import_bundle(bundle, secret_overrides={SECRET_PATH: "Bearer restored"})

        # Assert
        assert "include_secrets" not in calls[0].url.params
        assert _body(calls[1])["secret_overrides"] == {SECRET_PATH: "Bearer restored"}


class TestUsage:
    @respx.mock
    def test_a_workflow_lists_the_workflows_and_versions_that_use_it(self):
        # Arrange
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/usage").mock(side_effect=_replay([], "workflow_usage"))

        # Act
        report = _client().workflows.usage(WORKFLOW)

        # Assert
        assert isinstance(report, UsageReport)
        assert [(u.name, u.version_numbers) for u in report.used_by] == [("SDK_E2E evaluated by A", [0])]

    @respx.mock
    def test_an_unused_workflow_and_an_unused_tool_report_no_one(self):
        # Arrange
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/usage").mock(side_effect=_replay([], "workflow_usage_none"))
        respx.get(f"{BASE}/v1/tools/tool-1/usage").mock(side_effect=_replay([], "tool_usage"))

        # Act
        reports = [_client().workflows.usage(WORKFLOW), _client().tools.usage("tool-1")]

        # Assert
        assert [r.used_by for r in reports] == [[], []]

    @respx.mock
    def test_an_llm_config_lists_its_users_and_an_unknown_one_is_not_found(self):
        # Arrange
        respx.get(f"{BASE}/v1/llm-configs/llm-1/usage").mock(side_effect=_replay([], "llm_config_usage"))
        respx.get(f"{BASE}/v1/llm-configs/llm-gone/usage").mock(side_effect=_replay([], "llm_config_usage_unknown"))

        # Act
        report = _client().llm_configs.usage("llm-1")

        # Assert
        assert [u.name for u in report.used_by] == ["Booking assistant"]
        with pytest.raises(NotFoundError):
            _client().llm_configs.usage("llm-gone")

    @respx.mock
    async def test_the_async_client_reads_all_three(self):
        # Arrange
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/usage").mock(side_effect=_replay([], "workflow_usage"))
        respx.get(f"{BASE}/v1/tools/tool-1/usage").mock(side_effect=_replay([], "tool_usage"))
        respx.get(f"{BASE}/v1/llm-configs/llm-1/usage").mock(side_effect=_replay([], "llm_config_usage"))
        client = _aclient()

        # Act
        reports = [
            await client.workflows.usage(WORKFLOW),
            await client.tools.usage("tool-1"),
            await client.llm_configs.usage("llm-1"),
        ]

        # Assert
        assert [len(r.used_by) for r in reports] == [1, 0, 1]


class TestVersionSettings:
    @respx.mock
    def test_update_config_sends_the_settings_at_the_top_level_and_reads_the_version_back(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.patch(f"{BASE}/v1/workflows/{WORKFLOW}/versions/0/config").mock(
            side_effect=_replay(calls, "update_config")
        )

        # Act
        version = _client().workflows.versions.update_config(
            WORKFLOW, 0, config={"description": "sent at the top level"}
        )

        # Assert
        assert _body(calls[0]) == {"description": "sent at the top level"}
        assert isinstance(version, WorkflowVersion)
        assert (version.version_number, version.is_active, version.pruned_global_tool_exclusions) == (0, True, {})
        description = getattr(version.config, "description", None) or version.config["description"]
        assert description == "sent at the top level"

    @pytest.mark.parametrize("graph_key", ["node_configs", "edges", "workflow_config"])
    @respx.mock
    def test_update_config_refuses_nodes_and_edges_before_any_request(self, graph_key):
        # Arrange
        route = respx.patch(f"{BASE}/v1/workflows/{WORKFLOW}/versions/0/config").mock(
            side_effect=_replay([], "update_config")
        )

        # Act / Assert
        with pytest.raises(ValueError, match="client.nodes and client.edges"):
            _client().workflows.versions.update_config(WORKFLOW, 0, config={graph_key: []})
        assert not route.called

    @respx.mock
    def test_create_sends_the_name_the_server_requires(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflows/{WORKFLOW}/versions").mock(side_effect=_replay(calls, "create_version"))

        # Act
        version = _client().workflows.versions.create(WORKFLOW, version_name="SDK probe v1")

        # Assert
        assert _body(calls[0]) == {"version_name": "SDK probe v1", "mark_as_active": False}
        assert version.version_name == "SDK probe v1"
        # The server answers a create without a name with a 422, so the SDK asks for one.
        assert ANSWERS["create_version_no_name"]["status"] == 422
        for resource in (WorkflowVersionsResource, AsyncWorkflowVersionsResource):
            assert inspect.signature(resource.create).parameters["version_name"].default is inspect.Parameter.empty


class TestEnvelopes:
    def test_every_envelope_key_reaches_the_workflow(self):
        envelope = {**ANSWERS["import_with_overrides"]["body"], "a_key_added_later": 1}

        workflow = Workflow.model_validate(envelope)

        assert (workflow.execution_url, workflow.pruned_global_tool_exclusions) == (envelope["execution_url"], {})
        assert workflow.model_extra["a_key_added_later"] == 1

    def test_a_version_record_holds_its_settings_as_workflow_config(self):
        record = ANSWERS["update_config"]["body"]["version"]

        version = WorkflowVersion.model_validate(record)

        assert version.config is not None
