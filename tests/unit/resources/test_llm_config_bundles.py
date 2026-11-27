"""LLM-config export and import, a test result's new fields, and how 422 and 413 answers read, on the wire.

Every answer replayed here was captured from a workflow-service (``fixtures/llm_configs.json``), with its ids replaced.
The exported config is a custom gateway whose key and ``Authorization`` header are made-up values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    LLMConfigImportResult,
    NotFoundError,
    RequestTooLargeError,
    UnprocessableEntityError,
    WorkflowClient,
)

BASE = "http://localhost:8611"
ANSWERS: Dict[str, Dict[str, Any]] = json.loads((Path(__file__).parent / "fixtures" / "llm_configs.json").read_text())
BUNDLE = ANSWERS["export"]["body"]
PATHS = [r["path"] for r in BUNDLE["redactions"]]


def _client() -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _aclient() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _replay(calls: List[httpx.Request], name: str):
    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(ANSWERS[name]["status"], json=ANSWERS[name]["body"])

    return _handler


def _body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None


class TestExportAndImport:
    @respx.mock
    def test_export_names_the_configs_and_lists_each_redacted_secret(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/llm-configs/export").mock(side_effect=_replay(calls, "export"))

        # Act
        bundle = _client().llm_configs.export(llm_config_ids=["llm-1"])

        # Assert
        assert _body(calls[0]) == {"llm_config_ids": ["llm-1"]}
        assert [(r["path"], r["reason"]) for r in bundle["redactions"]] == [
            ("configs.0.config.api_key", "secret field"),
            ("configs.0.config.default_headers.Authorization", "sensitive header"),
        ]
        assert bundle["configs"][0]["config"]["default_headers"]["Authorization"] == "<REDACTED>"

    @respx.mock
    def test_exporting_every_config_sends_no_ids_and_an_unknown_id_is_not_found(self):
        # Arrange
        route = respx.post(f"{BASE}/v1/llm-configs/export")
        route.side_effect = [
            httpx.Response(200, json=BUNDLE),
            httpx.Response(ANSWERS["export_unknown"]["status"], json=ANSWERS["export_unknown"]["body"]),
        ]

        # Act
        _client().llm_configs.export()
        with pytest.raises(NotFoundError):
            _client().llm_configs.export(llm_config_ids=["llm_config_sdk_no_such"])

        # Assert
        # The route needs a body even for every config: null ids ask for all of them.
        assert [_body(c.request) for c in route.calls] == [
            {"llm_config_ids": None},
            {"llm_config_ids": ["llm_config_sdk_no_such"]},
        ]

    @respx.mock
    def test_import_sends_the_secrets_and_says_what_it_created(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/llm-configs/import").mock(side_effect=_replay(calls, "import"))
        overrides = {path: "value" for path in PATHS}

        # Act
        result = _client().llm_configs.import_bundle(BUNDLE, secret_overrides=overrides)

        # Assert
        assert _body(calls[0]) == {"bundle": BUNDLE, "secret_overrides": overrides}
        assert isinstance(result, LLMConfigImportResult)
        [item] = result.imported
        assert (item.renamed_from, item.ids_reminted, item.llm_config.name) == (
            "SDK_E2E gateway",
            True,
            "SDK_E2E gateway (imported)",
        )

    @respx.mock
    def test_an_import_missing_a_secret_is_refused_with_the_servers_message_and_the_paths(self):
        # Arrange
        respx.post(f"{BASE}/v1/llm-configs/import").mock(side_effect=_replay([], "import_missing_secrets"))

        # Act
        with pytest.raises(UnprocessableEntityError) as err:
            _client().llm_configs.import_bundle(BUNDLE)

        # Assert
        assert str(err.value) == "Redacted fields must be supplied again before import"
        assert err.value.body["message"]["field_errors"] == PATHS

    @respx.mock
    async def test_the_async_client_exports_and_imports(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/llm-configs/export").mock(side_effect=_replay(calls, "export"))
        respx.post(f"{BASE}/v1/llm-configs/import").mock(side_effect=_replay(calls, "import"))
        client = _aclient()

        # Act
        bundle = await client.llm_configs.export()
        result = await client.llm_configs.import_bundle(bundle, secret_overrides={PATHS[0]: "v"})

        # Assert
        assert [_body(c) for c in calls] == [
            {"llm_config_ids": None},
            {"bundle": BUNDLE, "secret_overrides": {PATHS[0]: "v"}},
        ]
        assert len(result.imported) == 1


class TestTestResult:
    @respx.mock
    def test_a_failed_test_says_what_kind_of_failure_and_whose_key_it_used(self):
        # Arrange
        respx.post(f"{BASE}/v1/llm-configs/test").mock(side_effect=_replay([], "test_inline_unreachable"))

        # Act
        result = _client().llm_configs.test_inline(
            config={"type": "custom_llm", "base_url": "https://llm.unreachable.invalid/v1"}, system_prompt="Say hi."
        )

        # Assert
        assert (result.success, result.error_category, result.used_user_api_key) == (False, "unavailable", True)


class TestErrorText:
    @respx.mock
    def test_a_refused_node_config_reads_as_the_servers_message_not_the_error_list(self):
        # Arrange
        respx.post(f"{BASE}/v1/nodes").mock(side_effect=_replay([], "node_422"))

        # Act
        with pytest.raises(UnprocessableEntityError) as err:
            _client().nodes.create(node_config={"type": "say_llm", "name": 123})

        # Assert
        assert str(err.value) == ANSWERS["node_422"]["body"]["message"]
        assert isinstance(err.value.body["detail"], list)

    @respx.mock
    def test_a_validation_error_list_alone_reads_as_where_and_why(self):
        # Arrange
        body = {"detail": [{"type": "missing", "loc": ["body", "version_name"], "msg": "Field required"}]}
        respx.post(f"{BASE}/v1/nodes").mock(return_value=httpx.Response(422, json=body))

        # Act / Assert
        with pytest.raises(UnprocessableEntityError, match="^version_name: Field required$"):
            _client().nodes.create(node_config={})

    @respx.mock
    def test_an_oversized_signal_raises_request_too_large(self):
        # Arrange
        run = "0" * 24
        respx.post(f"{BASE}/v1/workflow-runs/{run}/signals/go").mock(side_effect=_replay([], "signal_413"))

        # Act / Assert
        with pytest.raises(RequestTooLargeError, match="over the 65536 byte limit"):
            _client().runs.send_signal(run, "go", {"blob": "x"})
