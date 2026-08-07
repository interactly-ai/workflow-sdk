"""
Response models for the Simulations API.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["SimulationStatus", "Simulation", "SimulationGroup", "SimulationRun"]


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


class SimulationStatus(str, Enum):
    """Execution status for a simulation or simulation run group."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Simulation(BaseAPIModel):
    """A simulation configuration (test harness for a workflow)."""

    id: Optional[str] = None
    simulation_config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _map_id(data, "simulation")

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
    selected_workflow_run_id: Optional[str] = None
    counter_workflow_run_id: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    team_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _map_id(data, "simulation_run", "run")
