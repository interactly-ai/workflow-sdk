"""The 2026-10 HTTP surface against a running server.

The wire tests in ``tests/unit/resources/test_http_surface.py`` pin what the SDK sends and parses. These
prove the server agrees, for every new method that is safe to call: nothing here starts a generation
or an LLM call, and everything created is tagged and deleted.

The API-key test is the one that matters most. With an admin or super-admin credential, the server
deletes a saved LLM config's key when an update omits it, and ``llm_configs.update`` guards against that
by default. Only a real server can show that the guard and the opt-out both do what they claim.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from interactly import AsyncWorkflowClient, PermissionDeniedError
from interactly.configs import (
    ExternalAPIToolConfig,
    OpenAILLMConfig,
    OPENAIModel,
    PromptConfig,
    SayLLMNodeConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]

RUN_TAG = f"SDK_E2E_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


def _key_of(llm_config: Any) -> Optional[str]:
    key = getattr(llm_config.config, "api_key", None) if not isinstance(llm_config.config, dict) else llm_config.config.get("api_key")
    return key.get_secret_value() if hasattr(key, "get_secret_value") else key


async def _sweep(client: AsyncWorkflowClient) -> list[str]:
    left: list[str] = []
    raw = await client.get("/v1/workflows", params={"page": 1, "size": 100}, cast_to=dict)
    for w in raw.get("workflows", []):
        if RUN_TAG in ((w.get("workflow_config") or {}).get("name") or ""):
            left.append(str(w.get("_id") or w.get("id")))
            await client.workflows.delete(left[-1])
    tools = await client.tools.list(search=RUN_TAG, size=50)
    for tool in tools.items:
        if tool.id and RUN_TAG in (tool.name or ""):
            left.append(tool.id)
            await client.tools.delete(tool.id)
    return left


class _Created:
    """What a test created, so the fixture deletes it explicitly. The sweep then catches only misses."""

    def __init__(self) -> None:
        self.tools: list[str] = []
        self.workflows: list[str] = []


@pytest.fixture
async def created():
    return _Created()


@pytest.fixture
async def client(created):
    c = AsyncWorkflowClient()
    yield c
    for tool_id in created.tools:
        await c.tools.delete(tool_id)
    for workflow_id in created.workflows:
        await c.workflows.delete(workflow_id)
    residual = await _sweep(c)
    await c.close()
    assert not residual, f"residual SDK_E2E assets remained: {residual}"


async def test_clone_names_the_copy_and_keeps_the_config(client, created):
    source = await client.tools.create(
        tool_config=ExternalAPIToolConfig(name=f"{RUN_TAG} lookup", api_endpoint="https://example.com/lookup")
    )
    created.tools.append(source.id)
    default_named = await client.tools.clone(source.id)
    created.tools.append(default_named.id)
    explicitly_named = await client.tools.clone(source.id, name=f"{RUN_TAG} lookup v2")
    created.tools.append(explicitly_named.id)

    assert default_named.id not in (None, source.id)
    assert default_named.name == f"{RUN_TAG} lookup (Clone)"
    assert explicitly_named.name == f"{RUN_TAG} lookup v2"
    assert default_named.tool_config.api_endpoint == "https://example.com/lookup"


async def test_import_reports_a_variable_the_team_has_not_defined(client, created):
    source = await client.tools.create(
        tool_config=ExternalAPIToolConfig(
            name=f"{RUN_TAG} needs var", api_endpoint="https://example.com/{{sdk_e2e_never_defined_variable}}"
        )
    )
    created.tools.append(source.id)
    bundle = await client.tools.export(source.id)
    assert "sdk_e2e_never_defined_variable" in (bundle.get("required_dynamic_variables") or [])

    imported = await client.tools.import_bundle(bundle, name_override=f"{RUN_TAG} imported")
    created.tools.append(imported.id)

    assert any("sdk_e2e_never_defined_variable" in warning for warning in imported.warnings), imported.warnings


async def test_codebase_function_catalogue_and_detail(client):
    try:
        catalogue = await client.tools.codebase_functions()
    except PermissionDeniedError:
        pytest.skip("codebase functions are staff-only and this credential is not")
    if not catalogue.codebase_functions:
        pytest.skip("the server has no codebase function registered")

    first = catalogue.codebase_functions[0]
    detail = await client.tools.get_codebase_function(first.id)

    assert catalogue.total_count == len(catalogue.codebase_functions)
    assert detail.id == first.id and detail.args_schema


async def test_lints_realtime_and_counter_status_on_a_fresh_workflow(client, created):
    node = SayLLMNodeConfig(
        name="Greet",
        is_start=True,
        main_response_config=PromptConfig(prompt="Greet the caller."),
        llms_config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4_MINI),
    )
    workflow = await client.workflows.create_from_config(
        WorkflowConfigFullyHydrated(
            workflow_config=WorkflowConfig(name=f"{RUN_TAG} analysis", category="System Examples"),
            node_configs=[node],
            edge_configs=[],
        )
    )
    created.workflows.append(workflow.id)

    lints = await client.workflows.lints(workflow.id)
    realtime = await client.workflows.realtime_compatibility(workflow.id, model="gpt-realtime")
    counter = await client.workflows.counter_workflow(workflow.id)

    assert lints.workflow_id == workflow.id and isinstance(lints.warnings, list)
    assert realtime.model == "gpt-realtime" and realtime.supported is not None and realtime.summary
    assert counter.counter_workflow is None and counter.generation is None


async def test_an_update_without_a_key_keeps_it_and_the_opt_out_removes_it(client):
    created = await client.llm_configs.create(
        name=f"{RUN_TAG} key", config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4_MINI, api_key="sk-sdk-e2e-not-a-real-key")
    )
    try:
        if _key_of(await client.llm_configs.get(created.id)) is None:
            pytest.skip("this credential is not shown stored keys, so the server preserves them itself")

        # A freshly built config, as code naturally writes one: no key.
        await client.llm_configs.update(created.id, config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4))
        kept = await client.llm_configs.get(created.id)
        assert _key_of(kept) == "sk-sdk-e2e-not-a-real-key", "the stored key was lost on update"

        await client.llm_configs.update(
            created.id, config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4), preserve_api_key=False
        )
        assert _key_of(await client.llm_configs.get(created.id)) is None, "the opt-out did not remove the key"
    finally:
        await client.llm_configs.delete(created.id)
