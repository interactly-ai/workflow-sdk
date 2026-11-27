"""An admin's update built in code keeps the stored credentials; export and import carry them; a test says why it
failed.

Run with an admin key (the main credential is a super admin's): an admin is shown the credentials, so the server
reads a blank one from an admin as "delete it", and the SDK's carry is all that keeps them. The configs here hold
made-up credentials and point at a host that can never resolve, so no provider is called; each is deleted.

    pytest tests/integration/test_llm_config_credentials_e2e.py -m integration
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Iterator, List

import pytest

from interactly import UnprocessableEntityError, WorkflowClient
from interactly.configs import BedrockLLMConfig, CustomLLMConfig

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]

_GATEWAY = "https://llm.unreachable.invalid/v1"
_AUTH = "Bearer sdk-e2e-not-a-secret"


def _gateway(**fields: Any) -> CustomLLMConfig:
    return CustomLLMConfig(
        base_url=_GATEWAY, model="none", max_retries=0, request_timeout_ms=2000, streaming=False, **fields
    )


def _stored(client: WorkflowClient, llm_config_id: str) -> Dict[str, Any]:
    config = client.llm_configs.get(llm_config_id).config
    return config if isinstance(config, dict) else config.model_dump(mode="json")


@pytest.fixture
def session() -> Iterator[tuple]:
    """A client, and a list the test adds each config id it creates to; each is deleted afterwards."""
    client = WorkflowClient()
    created: List[str] = []
    try:
        yield client, created
    finally:
        for llm_config_id in created:
            client.llm_configs.delete(llm_config_id)
        client.close()


def test_an_admin_update_built_in_code_keeps_every_stored_credential(session):
    client, created = session
    tag = uuid.uuid4().hex[:8]
    bedrock = client.llm_configs.create(
        name=f"SDK_E2E bedrock {tag}",
        config=BedrockLLMConfig(region="us-east-1", aws_access_key_id="AKIASDKE2E", aws_secret_access_key="sdk-e2e"),
    )
    created.append(bedrock.llm_config_id)
    gateway = client.llm_configs.create(
        name=f"SDK_E2E gateway {tag}",
        config=_gateway(api_key="sk-sdk-e2e", default_headers={"Authorization": _AUTH, "X-Tenant": "t1"}),
    )
    created.append(gateway.llm_config_id)

    client.llm_configs.update(bedrock.llm_config_id, config=BedrockLLMConfig(region="eu-west-1"))
    client.llm_configs.update(gateway.llm_config_id, config=_gateway())
    kept_bedrock = _stored(client, bedrock.llm_config_id)
    kept_gateway = _stored(client, gateway.llm_config_id)
    client.llm_configs.update(gateway.llm_config_id, config=_gateway(), preserve_credentials=False)
    cleared = _stored(client, gateway.llm_config_id)

    assert (kept_bedrock["region"], kept_bedrock["aws_access_key_id"], kept_bedrock["aws_secret_access_key"]) == (
        "eu-west-1",
        "AKIASDKE2E",
        "sdk-e2e",
    )
    assert (kept_gateway["api_key"], kept_gateway["default_headers"]) == ("sk-sdk-e2e", {"Authorization": _AUTH})
    assert (cleared.get("api_key"), cleared.get("default_headers")) == (None, None)


def test_an_export_comes_back_through_secret_overrides_and_not_without_them(session):
    client, created = session
    gateway = client.llm_configs.create(
        name=f"SDK_E2E gateway {uuid.uuid4().hex[:8]}",
        config=_gateway(api_key="sk-sdk-e2e", default_headers={"Authorization": _AUTH}),
    )
    created.append(gateway.llm_config_id)

    bundle = client.llm_configs.export(llm_config_ids=[gateway.llm_config_id])
    with pytest.raises(UnprocessableEntityError, match="supplied again"):
        client.llm_configs.import_bundle(bundle)
    overrides = {r["path"]: (_AUTH if "headers" in r["path"] else "sk-sdk-e2e") for r in bundle["redactions"]}
    result = client.llm_configs.import_bundle(bundle, secret_overrides=overrides)
    created.extend(item.llm_config.llm_config_id for item in result.imported)
    copy = _stored(client, result.imported[0].llm_config.llm_config_id)

    assert sorted(r["path"].rsplit(".", 1)[-1] for r in bundle["redactions"]) == ["Authorization", "api_key"]
    assert (copy["api_key"], copy["default_headers"]) == ("sk-sdk-e2e", {"Authorization": _AUTH})


def test_a_failed_test_says_what_kind_of_failure():
    with WorkflowClient() as client:
        result = client.llm_configs.test_inline(
            config=_gateway(api_key="sk-sdk-e2e"),
            system_prompt="Say hi.",
            messages=[{"role": "human", "content": "hi"}],
        )

    assert (result.success, result.error_category, result.used_user_api_key) == (False, "unavailable", True)
