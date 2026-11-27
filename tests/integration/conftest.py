"""Shared fixtures for the integration tests, which need a running Interactly service.

Run with: pytest tests/integration/ -m integration
"""

from __future__ import annotations

import os

import pytest

from interactly import AsyncWorkflowClient

#: A key acting as a developer, and one acting as a viewer, on the same team as INTERACTLY_API_KEY. A key acts
#: with the lower of the role it was made with and its creator's current role, so an admin can mint both on the
#: team's API Keys page. They exist because the main credential is a super-admin's, and a test that passes with
#: it proves nothing about what a developer or a viewer is allowed to do.
DEVELOPER_KEY_ENV = "INTERACTLY_DEVELOPER_API_KEY"
VIEWER_KEY_ENV = "INTERACTLY_VIEWER_API_KEY"


@pytest.fixture
def developer_client() -> AsyncWorkflowClient:
    """A client acting as a developer: writes allowed, credentials hidden on read. Skips when the key is unset."""
    return _client_for(DEVELOPER_KEY_ENV)


@pytest.fixture
def viewer_client() -> AsyncWorkflowClient:
    """A client acting as a viewer: reads only. Skips when the key is unset."""
    return _client_for(VIEWER_KEY_ENV)


def _client_for(env_name: str) -> AsyncWorkflowClient:
    key = os.environ.get(env_name)
    if not key:
        pytest.skip(f"{env_name} is not set")
    return AsyncWorkflowClient(api_key=key)
