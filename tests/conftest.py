"""
Shared test fixtures used across all unit tests.
"""

from __future__ import annotations

import pytest
import respx
import httpx

from interactly import WorkflowClient, AsyncWorkflowClient


TEST_API_KEY = "test-api-key"
TEST_TEAM_ID = "test-team-id"
TEST_USER_ID = "test-user-id"
TEST_BASE_URL = "http://localhost:8611"


@pytest.fixture
def sync_client() -> WorkflowClient:
    """Return a WorkflowClient configured for testing (no real network calls)."""
    return WorkflowClient(
        api_key=TEST_API_KEY,
        team_id=TEST_TEAM_ID,
        user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL,
        max_retries=0,  # Disable retries for test speed.
    )


@pytest.fixture
def async_client() -> AsyncWorkflowClient:
    """Return an AsyncWorkflowClient configured for testing."""
    return AsyncWorkflowClient(
        api_key=TEST_API_KEY,
        team_id=TEST_TEAM_ID,
        user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL,
        max_retries=0,
    )


@pytest.fixture
def mock_router() -> respx.MockRouter:
    """
    Activate respx for the duration of a test and yield the router.
    All unmocked calls will raise an error, preventing accidental network I/O.
    """
    with respx.mock(assert_all_mocked=True) as router:
        yield router


# --------------------------------------------------------------------------- #
# Common response fixtures                                                      #
# --------------------------------------------------------------------------- #

WORKFLOW_RESPONSE = {
    "id": "wf-123",
    "name": "Test Workflow",
    "description": "A workflow for testing",
    "status": "active",
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "active_version_number": 1,
    "max_concurrent_runs": 5,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-02T00:00:00Z",
}

WORKFLOW_LIST_RESPONSE = {
    "items": [WORKFLOW_RESPONSE],
    "total": 1,
    "page": 1,
    "size": 20,
    "pages": 1,
}

RUN_RESPONSE = {
    "id": "run-456",
    "workflow_id": "wf-123",
    "status": "completed",
    "run_by": "api",
    "version_number": 1,
    "team_id": TEST_TEAM_ID,
    "created_at": "2024-01-01T12:00:00Z",
}

RUN_LIST_RESPONSE = {
    "items": [RUN_RESPONSE],
    "total": 1,
    "page": 1,
    "size": 20,
    "pages": 1,
}

VERSION_RESPONSE = {
    "version_number": 1,
    "version_name": "v1",
    "is_active": True,
    "created_at": "2024-01-01T00:00:00Z",
}
