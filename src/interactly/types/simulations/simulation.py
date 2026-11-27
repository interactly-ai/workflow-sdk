"""
Response models for the Simulations API.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field, model_validator

from interactly._models import BaseAPIModel

__all__ = [
    "SimulationStatus",
    "Simulation",
    "SimulationGroup",
    "SimulationRun",
    "SimulationRunControlOutcome",
    "SimulationRunControlResult",
]


class SimulationStatus(str, Enum):
    """Execution status for a simulation or simulation run group."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    #: A group a person paused: none of its simulations starts or takes a turn until it is resumed. Only a group takes
    #: this status.
    PAUSED = "paused"


class Simulation(BaseAPIModel):
    """A simulation configuration (test harness for a workflow)."""

    id: Optional[str] = None
    simulation_config: Optional[Dict[str, Any]] = None
    #: The status the configuration records for its latest run group: ``pending`` until a group starts, ``running``
    #: from then on, and the group's final status once it completes or fails. A group that was stopped leaves it
    #: ``running``, and a paused group is not recorded here: read the group (``get_run``) for those.
    status: Optional[str] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        data = _map_id(data, "simulation")
        # The server keeps the status inside the configuration, not beside it.
        if isinstance(data, dict) and data.get("status") is None and isinstance(data.get("simulation_config"), dict):
            data = {**data, "status": data["simulation_config"].get("status")}
        return data

    @property
    def name(self) -> Optional[str]:
        """The simulation's name, read from its ``simulation_config``."""
        return self._config_attr("name")

    @property
    def description(self) -> Optional[str]:
        """The simulation's description, read from its ``simulation_config``."""
        return self._config_attr("description")

    def _config_attr(self, key: str) -> Optional[Any]:
        cfg = self.simulation_config
        if isinstance(cfg, dict):
            return cfg.get(key)
        return getattr(cfg, key, None) if cfg is not None else None


class SimulationGroup(BaseAPIModel):
    """A batch run group produced by triggering a simulation."""

    id: Optional[str] = None
    simulation_config_id: Optional[str] = None
    status: Optional[str] = None
    total_runs: Optional[int] = None
    completed_runs: Optional[int] = None
    failed_runs: Optional[int] = None
    team_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _map_id(data, "simulation_group", "group")


class SimulationRun(BaseAPIModel):
    """An individual execution within a simulation group."""

    id: Optional[str] = None
    simulation_group_id: Optional[str] = None
    simulation_config_id: Optional[str] = None
    selected_workflow_run_id: Optional[str] = None
    counter_workflow_run_id: Optional[str] = None
    status: Optional[str] = None
    #: What the simulation produced once it ended, as the server stores it.
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    team_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _map_id(data, "simulation_run", "run")


class SimulationRunControlOutcome(BaseAPIModel):
    """What a group's pause or resume did to one workflow run of one of its simulations in flight."""

    #: The simulation (``SimulationRun.id``) the workflow run belongs to.
    individual_run_id: str
    workflow_run_id: str
    #: ``selected`` (the workflow under test) or ``counter`` (the workflow playing its user).
    role: str
    #: ``applied``; ``already_requested`` or ``not_paused`` when there was nothing to change; ``not_durable`` for a run
    #: held by its group alone, on a server whose simulation runs are not durable; ``run_ended``, ``not_found`` or
    #: ``conflict``.
    outcome: str
    #: The workflow run's status after the request.
    status: Optional[str] = None


class SimulationRunControlResult(BaseAPIModel):
    """A simulation group after a pause or resume, with what that did to each workflow run of its simulations in
    flight."""

    simulation_group: SimulationGroup
    #: Empty when no simulation of the group was running, such as a group paused before its first one started.
    runs: List[SimulationRunControlOutcome] = Field(default_factory=list)


def _map_id(data: Any, *envelope_keys: str) -> Any:
    """Unwrap a single-object envelope and map the server's ``_id`` onto ``id``."""
    if not isinstance(data, dict):
        return data
    for key in envelope_keys:
        inner = data.get(key)
        if isinstance(inner, dict) and "id" not in data and "_id" not in data:
            data = inner
            break
    if "_id" in data and "id" not in data:
        data["id"] = str(data["_id"])
    return data
