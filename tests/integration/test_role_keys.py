"""The developer and viewer keys act with the roles the role-gated tests assume.

Every role-gated integration test leans on these two keys, so this checks the keys themselves first: that each
one reaches the server, and that the server treats it as the role it is named for. Each test skips while its
key is unset.
"""

from __future__ import annotations

import os
from typing import Any, List

import pytest
from pydantic import BaseModel

from interactly import NotFoundError, PermissionDeniedError, StreamPermissionError

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
    # Below admin, the server clears every credential before it answers, on the list and on a single read.
    async with request.getfixturevalue(client_fixture) as client:
        page = await client.llm_configs.list(size=5)
        if not page.items:
            pytest.skip("the team has no saved LLM configs to read")
        read_one = await client.llm_configs.get(page.items[0].id)
        for config in [*page.items, read_one]:
            assert _credentials_shown(config.config) == [], config.name


async def test_a_viewer_key_is_refused_the_run_socket(viewer_client):
    # The server accepts the socket and closes it at once with 1008, naming the role it needs.
    async with viewer_client as client:
        with pytest.raises(StreamPermissionError) as caught:
            async with client.runs.stream(workflow_id=_NO_SUCH_NODE) as events:
                async for _ in events:
                    pass
        assert caught.value.code == 1008


async def test_a_viewer_key_is_refused_run_control(viewer_client):
    async with viewer_client as client:
        with pytest.raises(PermissionDeniedError):
            await client.runs.pause(_NO_SUCH_NODE, reason="role check")


async def test_a_developer_key_reaches_run_control(developer_client):
    # Allowed past the role gate, so the server looks the run up, and there is none.
    async with developer_client as client:
        with pytest.raises(NotFoundError):
            await client.runs.pause(_NO_SUCH_NODE, reason="role check")


async def test_a_viewer_key_is_refused_a_simulation_groups_pause(viewer_client):
    # A group's pause pauses its workflow runs, so it takes run control's role.
    async with viewer_client as client:
        with pytest.raises(PermissionDeniedError):
            await client.simulations.pause_run(_NO_SUCH_NODE, reason="role check")


async def test_a_developer_key_reaches_a_simulation_groups_pause(developer_client):
    async with developer_client as client:
        with pytest.raises(NotFoundError):
            await client.simulations.pause_run(_NO_SUCH_NODE, reason="role check")


def _credentials_shown(config: Any) -> List[str]:
    """Where ``config`` still carries a credential, as dotted paths; group members are walked too.

    ``config`` is the plain dict, or the typed config when the ``[configs]`` extra is installed. The typed
    config dumps ``api_key`` unmasked, so a dump shows exactly what the server sent.
    """
    if isinstance(config, BaseModel):
        config = config.model_dump()
    found: List[str] = []
    _collect_credentials(config, "", found)
    return found


#: The credential fields the provider configs declare, which the server sets to None for a caller below admin.
_CREDENTIAL_FIELDS = frozenset({"api_key", "aws_access_key_id", "aws_secret_access_key"})
#: Credential headers in a header map such as the custom gateway's ``default_headers``, whose values it empties.
_CREDENTIAL_HEADERS = frozenset({"authorization", "proxy-authorization", "x-api-key", "api-key"})


def _collect_credentials(value: Any, path: str, found: List[str]) -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            _collect_credentials(item, f"{path}[{index}]", found)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        where = f"{path}.{key}" if path else key
        if key in _CREDENTIAL_FIELDS:
            if item:
                found.append(where)
        elif key == "default_headers" and isinstance(item, dict):
            found.extend(
                f"{where}.{name}" for name, text in item.items() if name.lower() in _CREDENTIAL_HEADERS and text
            )
        else:
            _collect_credentials(item, where, found)
