"""Starting a workflow as a durable background run, on the wire.

The answers replayed are real, captured from a workflow-service through its gateway (``fixtures/background_run.json``)
with their ids replaced. The 404 body is the gateway's own: it does not pass the service's message on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, BackgroundRunStarted, NotFoundError, WorkflowClient

BASE = "http://localhost:8611"
WORKFLOW = "665f1c0a2b3c4d5e6f710099"
URL = f"{BASE}/v1/workflows/{WORKFLOW}/background-runs"
ANSWERS: Dict[str, Dict[str, Any]] = json.loads((Path(__file__).parent / "fixtures" / "background_run.json").read_text())


def _replay(calls: List[httpx.Request], name: str):
    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(ANSWERS[name]["status"], json=ANSWERS[name]["body"])

    return _handler


def _client() -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


class TestStartBackgroundRun:
    @respx.mock
    def test_it_sends_what_was_given_and_names_the_run_started(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(URL).mock(side_effect=_replay(calls, "started"))

        # Act
        started = _client().workflows.start_background_run(
            WORKFLOW, version_number=2, dynamic_variables={"patient_name": "Ada"}, run_by="nightly job"
        )

        # Assert
        assert json.loads(calls[0].content) == {
            "version_number": 2,
            "dynamic_variables": {"patient_name": "Ada"},
            "run_by": "nightly job",
        }
        assert isinstance(started, BackgroundRunStarted)
        assert (started.workflow_run_id, started.status) == ("665f1c0a2b3c4d5e6f710000", "started")

    @respx.mock
    def test_with_nothing_given_it_sends_no_body_and_the_server_runs_the_active_version(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(URL).mock(side_effect=_replay(calls, "started"))

        # Act
        _client().workflows.start_background_run(WORKFLOW)

        # Assert
        assert calls[0].content == b""

    @respx.mock
    def test_version_zero_is_sent(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(URL).mock(side_effect=_replay(calls, "started"))

        # Act
        _client().workflows.start_background_run(WORKFLOW, version_number=0)

        # Assert
        assert json.loads(calls[0].content) == {"version_number": 0}

    @pytest.mark.parametrize("answer", ["unknown_workflow", "unknown_version"])
    @respx.mock
    def test_an_unknown_workflow_or_version_raises_not_found(self, answer):
        # Arrange
        respx.post(URL).mock(side_effect=_replay([], answer))

        # Act / Assert
        with pytest.raises(NotFoundError):
            _client().workflows.start_background_run(WORKFLOW, version_number=99)

    @respx.mock
    async def test_the_async_client_starts_one_too(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(URL).mock(side_effect=_replay(calls, "started"))

        # Act
        async with AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0) as client:
            started = await client.workflows.start_background_run(WORKFLOW, run_by="Example 19")

        # Assert
        assert json.loads(calls[0].content) == {"run_by": "Example 19"}
        assert started.status == "started"
