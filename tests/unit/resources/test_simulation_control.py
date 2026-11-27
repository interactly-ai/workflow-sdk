"""Simulation groups on the wire: pausing, resuming and stopping a group, and the filters of the simulations list.

Every pause, resume and stop answer replayed here was captured from a workflow-service (``fixtures/simulation_control
.json``), with its ids replaced: a mock encoding a shape the server never produces keeps a broken method green. That
server's simulation runs were not durable, so each run in flight answers ``not_durable``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
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
    Simulation,
    SimulationGroup,
    SimulationRunControlResult,
    SimulationStatus,
    UnprocessableEntityError,
    WorkflowClient,
)

BASE = "http://localhost:8611"
GROUP = "665f1c0a2b3c4d5e6f710000"
ANSWERS: Dict[str, Dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "simulation_control.json").read_text()
)
_EMPTY_LIST = {"simulations": [], "total": 0}


def _client(max_retries: int = 0) -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=max_retries)


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


class TestPauseAndResume:
    @respx.mock
    def test_pause_sends_the_reason_and_returns_the_paused_group(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/pause").mock(side_effect=_replay(calls, "pause"))

        # Act
        result = _client().simulations.pause_run(GROUP, reason="sdk capture")

        # Assert
        assert _body(calls[0]) == {"reason": "sdk capture"}
        assert isinstance(result, SimulationRunControlResult)
        assert (result.simulation_group.id, result.simulation_group.status) == (GROUP, SimulationStatus.PAUSED)
        # Paused before any simulation was running: no workflow run to act on.
        assert result.runs == []

    @respx.mock
    def test_a_pause_without_a_reason_sends_no_body_and_says_what_became_of_each_run_in_flight(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/pause").mock(side_effect=_replay(calls, "pause_again"))

        # Act
        result = _client().simulations.pause_run(GROUP)

        # Assert
        assert _body(calls[0]) is None
        assert [(r.role, r.outcome, r.status) for r in result.runs] == [
            ("selected", "not_durable", "running"),
            ("counter", "not_durable", "running"),
        ]
        assert len({r.individual_run_id for r in result.runs}) == 1
        assert len({r.workflow_run_id for r in result.runs}) == 2

    @respx.mock
    def test_resume_sends_no_body_and_returns_the_running_group(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/resume").mock(side_effect=_replay(calls, "resume"))

        # Act
        result = _client().simulations.resume_run(GROUP)

        # Assert
        assert _body(calls[0]) is None
        assert result.simulation_group.status == SimulationStatus.RUNNING
        assert {r.role for r in result.runs} == {"selected", "counter"}

    @pytest.mark.parametrize(
        "method, answer, error, message",
        [
            ("pause_run", "pause_ended", ConflictError, r"already ended \(cancelled\)"),
            ("resume_run", "resume_ended", ConflictError, r"already ended \(cancelled\)"),
            ("pause_run", "pause_unknown", NotFoundError, "Simulation run not found"),
            ("pause_run", "pause_viewer", PermissionDeniedError, "Developer access or above"),
        ],
    )
    @respx.mock
    def test_a_refusal_raises_with_the_servers_message(self, method, answer, error, message):
        # Arrange
        action = method.removesuffix("_run")
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/{action}").mock(side_effect=_replay([], answer))

        # Act / Assert
        with pytest.raises(error, match=message):
            getattr(_client().simulations, method)(GROUP)

    @respx.mock
    def test_a_reason_over_a_thousand_characters_is_refused(self):
        # Arrange
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/pause").mock(side_effect=_replay([], "pause_reason_too_long"))

        # Act / Assert
        with pytest.raises(UnprocessableEntityError):
            _client().simulations.pause_run(GROUP, reason="x" * 1001)

    @respx.mock
    def test_a_pause_of_an_ended_group_is_not_retried(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/pause").mock(side_effect=_replay(calls, "pause_ended"))

        # Act
        with pytest.raises(ConflictError):
            _client(max_retries=2).simulations.pause_run(GROUP)

        # Assert
        assert len(calls) == 1

    @respx.mock
    async def test_the_async_client_pauses_and_resumes(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/pause").mock(side_effect=_replay(calls, "pause"))
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/resume").mock(side_effect=_replay(calls, "resume"))
        client = _aclient()

        # Act
        paused = await client.simulations.pause_run(GROUP, reason="r")
        resumed = await client.simulations.resume_run(GROUP)

        # Assert
        assert [_body(c) for c in calls] == [{"reason": "r"}, None]
        assert (paused.simulation_group.status, resumed.simulation_group.status) == ("paused", "running")


class TestStop:
    @respx.mock
    def test_stop_cancels_the_group(self):
        # Arrange
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/stop").mock(side_effect=_replay([], "stop"))

        # Act
        group = _client().simulations.stop_run(GROUP)

        # Assert
        assert isinstance(group, SimulationGroup)
        assert group.status == SimulationStatus.CANCELLED

    @respx.mock
    def test_stopping_a_group_that_ended_returns_it_as_it_is(self):
        # Arrange
        respx.post(f"{BASE}/v1/simulation-runs/{GROUP}/stop").mock(side_effect=_replay([], "stop_ended"))

        # Act
        group = _client().simulations.stop_run(GROUP)

        # Assert
        assert (group.id, group.status) == (GROUP, SimulationStatus.CANCELLED)


class TestListFilters:
    @respx.mock
    def test_each_filter_is_sent_as_the_server_reads_it(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/simulations").mock(
            side_effect=lambda r: calls.append(r) or httpx.Response(200, json=_EMPTY_LIST)
        )
        start = datetime(2026, 11, 1, tzinfo=timezone.utc)
        end = datetime(2026, 11, 20, tzinfo=timezone.utc)

        # Act
        _client().simulations.list(
            search="intake",
            logical_id="simulation_abc",
            selected_workflow_id="wf-selected",
            counter_workflow_id="wf-counter",
            selected_version_number=0,
            counter_version_number=2,
            status=SimulationStatus.RUNNING,
            start=start,
            end=end,
        )

        # Assert
        assert dict(calls[0].url.params) == {
            "page": "1",
            "size": "20",
            "search": "intake",
            "logical_id": "simulation_abc",
            "selected_workflow_id": "wf-selected",
            "counter_workflow_id": "wf-counter",
            "selected_version_number": "0",
            "counter_version_number": "2",
            "status": "running",
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    @respx.mock
    def test_filters_not_given_are_not_sent(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/simulations").mock(
            side_effect=lambda r: calls.append(r) or httpx.Response(200, json=_EMPTY_LIST)
        )

        # Act
        _client().simulations.list(status="completed")

        # Assert
        assert dict(calls[0].url.params) == {"page": "1", "size": "20", "status": "completed"}

    @respx.mock
    def test_the_next_page_keeps_every_filter(self):
        # Arrange
        calls: List[httpx.Request] = []
        one = {"simulations": [{"_id": "sim-1", "simulation_config": {"status": "completed"}}], "total": 2}
        respx.get(f"{BASE}/v1/simulations").mock(side_effect=lambda r: calls.append(r) or httpx.Response(200, json=one))

        # Act
        _client().simulations.list(size=1, selected_workflow_id="wf-selected", counter_version_number=0).next_page()

        # Assert
        second = dict(calls[1].url.params)
        assert (second["page"], second["selected_workflow_id"], second["counter_version_number"]) == (
            "2",
            "wf-selected",
            "0",
        )

    @pytest.mark.parametrize("given", ["start", "end"])
    @respx.mock
    def test_one_end_of_the_date_range_alone_is_refused_before_any_request(self, given):
        # Arrange
        route = respx.get(f"{BASE}/v1/simulations").mock(return_value=httpx.Response(200, json=_EMPTY_LIST))

        # Act / Assert
        with pytest.raises(ValueError, match="start and end together"):
            _client().simulations.list(**{given: datetime(2026, 11, 1, tzinfo=timezone.utc)})
        assert not route.called

    @respx.mock
    def test_a_range_over_31_days_raises_bad_request(self):
        # Arrange
        respx.get(f"{BASE}/v1/simulations").mock(side_effect=_replay([], "list_range_too_long"))

        # Act / Assert
        with pytest.raises(BadRequestError, match="less than or equal to 31 days"):
            _client().simulations.list(
                start=datetime(2026, 10, 1, tzinfo=timezone.utc), end=datetime(2026, 11, 10, tzinfo=timezone.utc)
            )

    @respx.mock
    async def test_the_async_client_sends_the_filters_too(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/simulations").mock(
            side_effect=lambda r: calls.append(r) or httpx.Response(200, json=_EMPTY_LIST)
        )

        # Act
        await _aclient().simulations.list(logical_id="simulation_abc", status=SimulationStatus.FAILED)

        # Assert
        assert dict(calls[0].url.params) == {
            "page": "1",
            "size": "20",
            "logical_id": "simulation_abc",
            "status": "failed",
        }


class TestStatuses:
    def test_a_simulation_reads_its_status_from_its_configuration(self):
        # The keys a simulation has on the server: its status sits inside the configuration.
        raw = {
            "_id": "665f1c0a2b3c4d5e6f710001",
            "simulation_config": {"name": "Intake", "status": "completed", "logical_id": "simulation_abc"},
            "team_id": "665f1c0a2b3c4d5e6f71000a",
            "created_by": "665f1c0a2b3c4d5e6f71000b",
            "updated_by": "665f1c0a2b3c4d5e6f71000b",
            "created_at": "2026-11-27T05:24:17.913Z",
            "updated_at": "2026-11-27T05:24:18.172Z",
        }

        simulation = Simulation.model_validate(raw)

        assert (simulation.id, simulation.status, simulation.name) == (raw["_id"], "completed", "Intake")

    def test_a_status_beside_the_configuration_is_kept(self):
        simulation = Simulation.model_validate(
            {"id": "sim-1", "status": "pending", "simulation_config": {"status": "x"}}
        )

        assert simulation.status == "pending"

    def test_paused_is_a_group_status(self):
        group = SimulationGroup.model_validate(ANSWERS["pause"]["body"]["simulation_group"])

        assert group.status == SimulationStatus.PAUSED == "paused"
