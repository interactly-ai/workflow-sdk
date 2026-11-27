"""The developer and viewer keys act with the roles the role-gated tests assume.

Every role-gated integration test leans on these two keys, so this checks the keys themselves first: that each
one reaches the server, and that the server treats it as the role it is named for. Each test skips while its
key is unset.
"""

from __future__ import annotations

import os

import pytest

from interactly import NotFoundError, PermissionDeniedError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_BASE_URL"), reason="requires a live INTERACTLY_BASE_URL"),
]

#: A well-formed id no node has. A delete that reaches the lookup answers 404; one the role gate refuses never
#: gets there. Nothing is deleted either way.
_NO_SUCH_NODE = "000000000000000000000000"


async def test_a_viewer_key_is_refused_a_write_before_the_lookup(viewer_client):
    async with viewer_client as client:
        with pytest.raises(PermissionDeniedError):
            await client.nodes.delete(_NO_SUCH_NODE)


async def test_a_developer_key_is_allowed_to_write(developer_client):
    async with developer_client as client:
        with pytest.raises(NotFoundError):
            await client.nodes.delete(_NO_SUCH_NODE)


@pytest.mark.parametrize("client_fixture", ["developer_client", "viewer_client"])
async def test_a_non_admin_key_is_shown_no_llm_config_key(client_fixture, request):
    async with request.getfixturevalue(client_fixture) as client:
        page = await client.llm_configs.list(size=5)
        if not page.items:
            pytest.skip("the team has no saved LLM configs to read")
        config = await client.llm_configs.get(page.items[0].id)
        assert (config.config or {}).get("api_key") is None
