"""
SimulationsResource — manage workflow simulation configurations and runs.

Endpoints:
    GET    /v1/simulations/schema                              → schema
    POST   /v1/simulations                                     → create
    GET    /v1/simulations                                     → list
    GET    /v1/simulations/{id}                                → get
    PATCH  /v1/simulations/{id}                                → update
    DELETE /v1/simulations/{id}                                → delete
    POST   /v1/simulations/{id}/run                            → run
    GET    /v1/simulations/{id}/runs                           → list_runs
    GET    /v1/simulations/{id}/evaluation-summary             → evaluation_summary
    GET    /v1/simulation-runs/{run_id}                        → get_run
    POST   /v1/simulation-runs/{run_id}/stop                   → stop_run
    POST   /v1/simulation-runs/{run_id}/pause                  → pause_run
    POST   /v1/simulation-runs/{run_id}/resume                 → resume_run
    GET    /v1/simulation-runs/{run_id}/executions             → list_executions
    GET    /v1/simulation-runs/{run_id}/executions/detailed    → list_detailed_executions
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, cast

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._utils._serialise import serialise_config
from interactly.types.simulations.simulation import (
    Simulation,
    SimulationGroup,
    SimulationRun,
    SimulationRunControlResult,
    SimulationStatus,
)

__all__ = ["SimulationsResource", "AsyncSimulationsResource"]

_PATH = "/v1/simulations"
_RUNS_PATH = "/v1/simulation-runs"


class SimulationsResource(SyncAPIResource):
    """Synchronous interface to the Simulations API."""

    def schema(self) -> Dict[str, Any]:
        """
        Retrieve the JSON Schema for a simulation configuration.

        Returns:
            A dict with a ``config_schema`` key containing the JSON Schema.
        """
        return self._client.get(f"{_PATH}/schema", cast_to=dict)

    def create(self, *, config: Dict[str, Any]) -> Simulation:
        """
        Create a new simulation configuration.

        Args:
            config: A :class:`SimulationConfig`-compatible ``dict`` (or any typed
                    Pydantic model with the same fields) describing the simulation
                    (selected workflow, counter workflow, number of runs,
                    evaluation criteria, etc.).

        Returns:
            The created :class:`Simulation` wrapped in the API response.
        """
        raw = self._client.post(_PATH, body=serialise_config(config), cast_to=dict)
        return Simulation.model_validate(raw.get("simulation", raw))

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        logical_id: Optional[str] = None,
        selected_workflow_id: Optional[str] = None,
        counter_workflow_id: Optional[str] = None,
        selected_version_number: Optional[int] = None,
        counter_version_number: Optional[int] = None,
        status: Union[SimulationStatus, str, None] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> SyncPage[Simulation]:
        """
        List simulation configurations for the team, newest first. Every filter given must match.

        Args:
            page:                    Page number (1-indexed, default 1).
            size:                    Items per page (default 20).
            search:                  Text matched, ignoring case, against the description and the names of both
                                     workflows.
            logical_id:              The simulation's logical id (``simulation_config["logical_id"]``).
            selected_workflow_id:    Only simulations of this workflow under test.
            counter_workflow_id:     Only simulations whose user is played by this workflow.
            selected_version_number: Only simulations naming this version of the workflow under test.
            counter_version_number:  Only simulations naming this version of the counter workflow.
            status:                  The status the configuration records for its latest group
                                     (:attr:`Simulation.status`). A stopped or paused group is not recorded there:
                                     filter groups with :meth:`list_runs` and their ``status`` instead.
            start, end:              Only simulations created between these times. Give both or neither; the range
                                     may span 31 days at most.

        Returns:
            A :class:`SyncPage` of :class:`Simulation` objects.

        Raises:
            ValueError:      only one of ``start`` and ``end`` is given.
            BadRequestError: ``start`` and ``end`` are more than 31 days apart, or ``end`` is before ``start``.
        """
        filters: Dict[str, Any] = dict(
            search=search,
            logical_id=logical_id,
            selected_workflow_id=selected_workflow_id,
            counter_workflow_id=counter_workflow_id,
            selected_version_number=selected_version_number,
            counter_version_number=counter_version_number,
            status=status,
            start=start,
            end=end,
        )
        raw = self._client.get(_PATH, cast_to=dict, params=_list_params(page=page, size=size, **filters))
        items = [Simulation.model_validate(s) for s in raw.get("simulations", [])]
        total = raw.get("total", len(items))
        return SyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            Simulation,
            lambda p: self.list(page=p, size=size, **filters),
        )

    def get(self, simulation_id: str) -> Simulation:
        """
        Retrieve a simulation configuration by ID.

        Args:
            simulation_id: ObjectId of the simulation.

        Returns:
            The :class:`Simulation`.
        """
        raw = self._client.get(f"{_PATH}/{simulation_id}", cast_to=dict)
        return Simulation.model_validate(raw.get("simulation", raw))

    def update(self, simulation_id: str, *, updates: Dict[str, Any]) -> Simulation:
        """
        Partially update a simulation configuration.

        Only ``description`` and ``status`` are updatable via the backend.

        Args:
            simulation_id: ObjectId of the simulation.
            updates:       Dict (or typed Pydantic model) of fields to update.

        Returns:
            The updated :class:`Simulation`.
        """
        raw = self._client.patch(f"{_PATH}/{simulation_id}", body=serialise_config(updates), cast_to=dict)
        return Simulation.model_validate(raw.get("simulation", raw))

    def delete(self, simulation_id: str) -> Dict[str, Any]:
        """
        Delete a simulation configuration.

        Args:
            simulation_id: ObjectId of the simulation.

        Returns:
            A dict with a ``message`` field.
        """
        return self._client.delete(f"{_PATH}/{simulation_id}", cast_to=dict)

    def run(
        self,
        simulation_id: str,
        *,
        runner_name: Optional[str] = None,
    ) -> SimulationGroup:
        """
        Trigger a new simulation batch run.

        Args:
            simulation_id: ObjectId of the simulation configuration.
            runner_name:   Optional label for the runner instance.

        Returns:
            The created :class:`SimulationGroup` tracking the batch run.
        """
        body: Dict[str, Any] = {}
        if runner_name is not None:
            body["runner_name"] = runner_name
        raw = self._client.post(f"{_PATH}/{simulation_id}/run", body=body, cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

    def list_runs(
        self,
        simulation_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> SyncPage[SimulationGroup]:
        """
        List all run groups for a simulation configuration.

        Args:
            simulation_id: ObjectId of the simulation.
            page:          Page number (1-indexed, default 1).
            size:          Items per page (default 20).

        Returns:
            A :class:`SyncPage` of :class:`SimulationGroup` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = self._client.get(f"{_PATH}/{simulation_id}/runs", cast_to=dict, params=params)
        items = [SimulationGroup.model_validate(g) for g in raw.get("simulation_groups", [])]
        total = raw.get("total", len(items))
        return SyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            SimulationGroup,
            lambda p: self.list_runs(simulation_id, page=p, size=size),
        )

    def evaluation_summary(
        self,
        simulation_id: str,
        *,
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated evaluation results for a simulation.

        Args:
            simulation_id: ObjectId of the simulation.
            group_id:      Optional run group ID to scope the summary. Defaults
                           to the latest group.

        Returns:
            A dict with ``simulation_id``, ``group_id``,
            ``selected_workflow_summary``, and ``counter_workflow_summary``.
        """
        params: Dict[str, Any] = {}
        if group_id is not None:
            params["group_id"] = group_id
        return self._client.get(f"{_PATH}/{simulation_id}/evaluation-summary", cast_to=dict, params=params)

    def get_run(self, run_id: str) -> SimulationGroup:
        """
        Get details of a specific simulation run group.

        Args:
            run_id: ObjectId of the simulation group.

        Returns:
            The :class:`SimulationGroup`.
        """
        raw = self._client.get(f"{_RUNS_PATH}/{run_id}", cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

    def stop_run(self, run_id: str) -> SimulationGroup:
        """
        Stop a simulation run group, for good.

        The group moves to ``cancelled``: no simulation of it starts, and each one running ends ``cancelled`` before
        its next turn. Stopping a group that has already ended changes nothing. To hold a group and carry on later,
        use :meth:`pause_run`.

        Args:
            run_id: ObjectId of the simulation group to stop.

        Returns:
            The :class:`SimulationGroup`: ``cancelled``, or the status it ended with if it had already ended.
        """
        raw = self._client.post(f"{_RUNS_PATH}/{run_id}/stop", cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

    def pause_run(self, run_id: str, *, reason: Optional[str] = None) -> SimulationRunControlResult:
        """
        Pause a simulation run group until :meth:`resume_run`.

        A pending or running group moves to ``paused``; pausing a paused group changes nothing. No simulation of the
        group starts or takes a turn while it is paused, and the workflow runs of each simulation running at that
        moment are paused too. ``runs`` says what became of each: on a server whose simulation runs are not durable,
        they answer ``not_durable`` and are held by their group alone.

        Args:
            run_id: ObjectId of the simulation group (:attr:`SimulationGroup.id`).
            reason: Why, up to 1,000 characters; recorded on each workflow run paused.

        Returns:
            A :class:`SimulationRunControlResult`: the group, and what the pause did to each workflow run in flight.

        Raises:
            ConflictError:            the group has ended.
            NotFoundError:            no such group in the team.
            PermissionDeniedError:    the caller's role is below Developer.
            UnprocessableEntityError: a reason over 1,000 characters.
        """
        return self._client.post(
            f"{_RUNS_PATH}/{run_id}/pause", body=_pause_body(reason), cast_to=SimulationRunControlResult
        )

    def resume_run(self, run_id: str) -> SimulationRunControlResult:
        """
        Resume a paused simulation run group.

        The group moves back to ``running``: its simulations carry on and the rest start. The pause of each workflow
        run of its simulations in flight is lifted, however it was paused. On a group that is not paused, only those
        runs' pauses are lifted.

        Args:
            run_id: ObjectId of the simulation group (:attr:`SimulationGroup.id`).

        Returns:
            A :class:`SimulationRunControlResult`: the group, and what the resume did to each workflow run in flight.

        Raises:
            ConflictError:         the group has ended.
            NotFoundError:         no such group in the team.
            PermissionDeniedError: the caller's role is below Developer.
        """
        return self._client.post(f"{_RUNS_PATH}/{run_id}/resume", cast_to=SimulationRunControlResult)

    def list_executions(
        self,
        run_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> SyncPage[SimulationRun]:
        """
        List individual executions within a simulation run group.

        Args:
            run_id: ObjectId of the simulation group.
            page:   Page number (1-indexed, default 1).
            size:   Items per page (default 20).

        Returns:
            A :class:`SyncPage` of :class:`SimulationRun` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = self._client.get(f"{_RUNS_PATH}/{run_id}/executions", cast_to=dict, params=params)
        items = [SimulationRun.model_validate(r) for r in raw.get("individual_runs", [])]
        total = raw.get("total", len(items))
        return SyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            SimulationRun,
            lambda p: self.list_executions(run_id, page=p, size=size),
        )

    def list_detailed_executions(
        self,
        run_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        List individual executions with hydrated workflow run details.

        Returns enriched data per run including workflow names, statuses,
        evaluation run IDs, and scores.

        Args:
            run_id: ObjectId of the simulation group.
            page:   Page number (1-indexed, default 1).
            size:   Items per page (default 20).

        Returns:
            A list of detailed execution dicts (sorted ascending by run index).
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = self._client.get(f"{_RUNS_PATH}/{run_id}/executions/detailed", cast_to=dict, params=params)
        return cast(List[Dict[str, Any]], raw.get("individual_runs", []))


class AsyncSimulationsResource(AsyncAPIResource):
    """Asynchronous interface to the Simulations API."""

    async def schema(self) -> Dict[str, Any]:
        """Retrieve the JSON Schema for a simulation configuration."""
        return await self._client.get(f"{_PATH}/schema", cast_to=dict)

    async def create(self, *, config: Dict[str, Any]) -> Simulation:
        """Create a new simulation configuration (dict or typed Pydantic model)."""
        raw = await self._client.post(_PATH, body=serialise_config(config), cast_to=dict)
        return Simulation.model_validate(raw.get("simulation", raw))

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        logical_id: Optional[str] = None,
        selected_workflow_id: Optional[str] = None,
        counter_workflow_id: Optional[str] = None,
        selected_version_number: Optional[int] = None,
        counter_version_number: Optional[int] = None,
        status: Union[SimulationStatus, str, None] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> AsyncPage[Simulation]:
        """List simulation configurations for the team, newest first; the filters are
        :meth:`SimulationsResource.list`'s."""
        filters: Dict[str, Any] = dict(
            search=search,
            logical_id=logical_id,
            selected_workflow_id=selected_workflow_id,
            counter_workflow_id=counter_workflow_id,
            selected_version_number=selected_version_number,
            counter_version_number=counter_version_number,
            status=status,
            start=start,
            end=end,
        )
        raw = await self._client.get(_PATH, cast_to=dict, params=_list_params(page=page, size=size, **filters))
        items = [Simulation.model_validate(s) for s in raw.get("simulations", [])]
        total = raw.get("total", len(items))
        return AsyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            Simulation,
            lambda p: self.list(page=p, size=size, **filters),
        )

    async def get(self, simulation_id: str) -> Simulation:
        """Retrieve a simulation configuration by ID."""
        raw = await self._client.get(f"{_PATH}/{simulation_id}", cast_to=dict)
        return Simulation.model_validate(raw.get("simulation", raw))

    async def update(self, simulation_id: str, *, updates: Dict[str, Any]) -> Simulation:
        """Partially update a simulation configuration (dict or typed Pydantic model)."""
        raw = await self._client.patch(f"{_PATH}/{simulation_id}", body=serialise_config(updates), cast_to=dict)
        return Simulation.model_validate(raw.get("simulation", raw))

    async def delete(self, simulation_id: str) -> Dict[str, Any]:
        """Delete a simulation configuration."""
        return await self._client.delete(f"{_PATH}/{simulation_id}", cast_to=dict)

    async def run(
        self,
        simulation_id: str,
        *,
        runner_name: Optional[str] = None,
    ) -> SimulationGroup:
        """Trigger a new simulation batch run."""
        body: Dict[str, Any] = {}
        if runner_name is not None:
            body["runner_name"] = runner_name
        raw = await self._client.post(f"{_PATH}/{simulation_id}/run", body=body, cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

    async def list_runs(
        self,
        simulation_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> AsyncPage[SimulationGroup]:
        """List all run groups for a simulation configuration."""
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = await self._client.get(f"{_PATH}/{simulation_id}/runs", cast_to=dict, params=params)
        items = [SimulationGroup.model_validate(g) for g in raw.get("simulation_groups", [])]
        total = raw.get("total", len(items))
        return AsyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            SimulationGroup,
            lambda p: self.list_runs(simulation_id, page=p, size=size),
        )

    async def evaluation_summary(
        self,
        simulation_id: str,
        *,
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get aggregated evaluation results for a simulation."""
        params: Dict[str, Any] = {}
        if group_id is not None:
            params["group_id"] = group_id
        return await self._client.get(
            f"{_PATH}/{simulation_id}/evaluation-summary", cast_to=dict, params=params
        )

    async def get_run(self, run_id: str) -> SimulationGroup:
        """Get details of a specific simulation run group."""
        raw = await self._client.get(f"{_RUNS_PATH}/{run_id}", cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

    async def stop_run(self, run_id: str) -> SimulationGroup:
        """Stop a simulation run group, for good; see :meth:`SimulationsResource.stop_run`."""
        raw = await self._client.post(f"{_RUNS_PATH}/{run_id}/stop", cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

    async def pause_run(self, run_id: str, *, reason: Optional[str] = None) -> SimulationRunControlResult:
        """Pause a simulation run group until :meth:`resume_run`; see :meth:`SimulationsResource.pause_run`."""
        return await self._client.post(
            f"{_RUNS_PATH}/{run_id}/pause", body=_pause_body(reason), cast_to=SimulationRunControlResult
        )

    async def resume_run(self, run_id: str) -> SimulationRunControlResult:
        """Resume a paused simulation run group; see :meth:`SimulationsResource.resume_run`."""
        return await self._client.post(f"{_RUNS_PATH}/{run_id}/resume", cast_to=SimulationRunControlResult)

    async def list_executions(
        self,
        run_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> AsyncPage[SimulationRun]:
        """List individual executions within a simulation run group."""
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = await self._client.get(f"{_RUNS_PATH}/{run_id}/executions", cast_to=dict, params=params)
        items = [SimulationRun.model_validate(r) for r in raw.get("individual_runs", [])]
        total = raw.get("total", len(items))
        return AsyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            SimulationRun,
            lambda p: self.list_executions(run_id, page=p, size=size),
        )

    async def list_detailed_executions(
        self,
        run_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> List[Dict[str, Any]]:
        """List individual executions with hydrated workflow run details."""
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = await self._client.get(
            f"{_RUNS_PATH}/{run_id}/executions/detailed", cast_to=dict, params=params
        )
        return cast(List[Dict[str, Any]], raw.get("individual_runs", []))


def _list_params(**params: Any) -> Dict[str, Any]:
    """A simulations page's query: the parameters given, with enums and times as the server reads them."""
    if (params.get("start") is None) != (params.get("end") is None):
        # The server filters by creation time only when it has both, and would ignore one alone.
        raise ValueError("Pass start and end together: simulations are filtered by creation time only with both.")
    query: Dict[str, Any] = {}
    for name, value in params.items():
        if value is None:
            continue
        if isinstance(value, Enum):
            value = value.value
        elif isinstance(value, datetime):
            value = value.isoformat()
        query[name] = value
    return query


def _pause_body(reason: Optional[str]) -> Dict[str, Any]:
    """A pause's body: the reason when there is one, otherwise none at all."""
    return {} if reason is None else {"reason": reason}
