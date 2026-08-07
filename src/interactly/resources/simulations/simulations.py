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
    GET    /v1/simulation-runs/{run_id}/executions             → list_executions
    GET    /v1/simulation-runs/{run_id}/executions/detailed    → list_detailed_executions
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._utils._serialise import serialise_config
from interactly.types.simulations.simulation import Simulation, SimulationGroup, SimulationRun

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
    ) -> SyncPage[Simulation]:
        """
        List simulation configurations for the team.

        Args:
            page:   Page number (1-indexed, default 1).
            size:   Items per page (default 20).
            search: Fuzzy text filter.

        Returns:
            A :class:`SyncPage` of :class:`Simulation` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        items = [Simulation.model_validate(s) for s in raw.get("simulations", [])]
        total = raw.get("total", len(items))
        return SyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            Simulation,
            lambda p: self.list(page=p, size=size, search=search),
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
        Cancel a simulation run group.

        The orchestrator will stop spawning new individual runs. Already-running
        runs will complete naturally.

        Args:
            run_id: ObjectId of the simulation group to stop.

        Returns:
            The updated :class:`SimulationGroup` with status ``cancelled``.
        """
        raw = self._client.post(f"{_RUNS_PATH}/{run_id}/stop", cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

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
    ) -> AsyncPage[Simulation]:
        """List simulation configurations for the team."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        items = [Simulation.model_validate(s) for s in raw.get("simulations", [])]
        total = raw.get("total", len(items))
        return AsyncPage._from_response(
            {"items": items, "total": total, "page": page, "size": size},
            Simulation,
            lambda p: self.list(page=p, size=size, search=search),
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
        """Cancel a simulation run group."""
        raw = await self._client.post(f"{_RUNS_PATH}/{run_id}/stop", cast_to=dict)
        return SimulationGroup.model_validate(raw.get("simulation_group", raw))

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
