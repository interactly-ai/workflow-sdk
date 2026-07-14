"""
SchedulesResource — manage scheduled workflow runs.

Endpoints:
    POST   /v1/workflows/{workflow_id}/schedules     → create
    GET    /v1/workflows/{workflow_id}/schedules     → list (per workflow)
    GET    /v1/workflow-schedules                    → list_all (team-wide)
    GET    /v1/workflow-schedules/{id}               → get
    PATCH  /v1/workflow-schedules/{id}               → update
    DELETE /v1/workflow-schedules/{id}               → cancel
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import RunInputOrDict
from interactly.types.schedules.schedule import Schedule, ScheduleStatus

__all__ = ["SchedulesResource", "AsyncSchedulesResource"]

_SCHEDULES_PATH = "/v1/workflow-schedules"


class SchedulesResource(SyncAPIResource):
    """Synchronous interface to the Workflow Schedules API."""

    def create(
        self,
        workflow_id: str,
        *,
        scheduled_time: datetime,
        run_input: Optional[RunInputOrDict] = None,
        version: Optional[int] = None,
        scheduled_by_name: Optional[str] = None,
    ) -> Schedule:
        """
        Schedule a workflow to run at a future UTC time.

        Args:
            workflow_id:       The workflow to schedule.
            scheduled_time:    Future UTC datetime for execution.
            run_input:         Optional workflow run input payload.
            version:           Workflow version to use (defaults to active version).
            scheduled_by_name: Display name of the scheduling user (for audit UI).

        Returns:
            The created :class:`Schedule`.
        """
        body: Dict[str, Any] = {
            "scheduled_time": scheduled_time.isoformat(),
        }
        if run_input is not None:
            body["run_input"] = serialise_config(run_input)
        if version is not None:
            body["version"] = version
        if scheduled_by_name is not None:
            body["scheduled_by_name"] = scheduled_by_name
        return self._client.post(f"/v1/workflows/{workflow_id}/schedules", body=body, cast_to=Schedule)

    def list(
        self,
        workflow_id: str,
        *,
        status: Optional[ScheduleStatus] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Schedule]:
        """
        List scheduled runs for a specific workflow.

        Returns a full ``List[Schedule]`` (not a paginated ``SyncPage``) because
        the underlying endpoint is not paginated — use ``skip``/``limit`` for
        offset-based windowing.

        Args:
            workflow_id: The workflow whose schedules to list.
            status:      Filter by schedule status.
            skip:        Number of records to skip (offset pagination).
            limit:       Maximum records to return (1–100, default 50).

        Returns:
            A list of :class:`Schedule` objects.
        """
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if status is not None:
            params["status"] = status.value if isinstance(status, ScheduleStatus) else status
        raw = self._client.get(f"/v1/workflows/{workflow_id}/schedules", cast_to=list, params=params)
        return [Schedule.model_validate(item) for item in (raw or [])]

    def list_all(
        self,
        *,
        status: Optional[ScheduleStatus] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Schedule]:
        """
        List all scheduled runs across the entire team.

        Args:
            status: Filter by schedule status.
            skip:   Offset for pagination.
            limit:  Maximum records to return (1–100, default 50).

        Returns:
            A list of :class:`Schedule` objects.
        """
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if status is not None:
            params["status"] = status.value if isinstance(status, ScheduleStatus) else status
        raw = self._client.get(_SCHEDULES_PATH, cast_to=list, params=params)
        return [Schedule.model_validate(item) for item in (raw or [])]

    def get(self, schedule_id: str) -> Schedule:
        """
        Retrieve a single scheduled run by ID.

        Args:
            schedule_id: ObjectId of the schedule.

        Returns:
            The :class:`Schedule`.

        Raises:
            NotFoundError: If no schedule with the given ID exists.
        """
        return self._client.get(f"{_SCHEDULES_PATH}/{schedule_id}", cast_to=Schedule)

    def update(
        self,
        schedule_id: str,
        *,
        scheduled_time: NotGivenOr[Optional[datetime]] = NOT_GIVEN,
        run_input: NotGivenOr[Optional[RunInputOrDict]] = NOT_GIVEN,
        version: NotGivenOr[Optional[int]] = NOT_GIVEN,
    ) -> Schedule:
        """
        Modify a pending scheduled run.

        Only ``PENDING`` schedules can be modified. Changing ``scheduled_time``
        re-creates the underlying AWS EventBridge schedule.

        Args:
            schedule_id:    The schedule to update.
            scheduled_time: New future UTC datetime.
            run_input:      New workflow run input payload.
            version:        New workflow version to use.

        Returns:
            The updated :class:`Schedule`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(scheduled_time) and scheduled_time is not None:
            body["scheduled_time"] = scheduled_time.isoformat()
        elif is_given(scheduled_time):
            body["scheduled_time"] = scheduled_time
        if is_given(run_input):
            body["run_input"] = serialise_config(run_input) if run_input is not None else run_input
        if is_given(version):
            body["version"] = version
        return self._client.patch(f"{_SCHEDULES_PATH}/{schedule_id}", body=body, cast_to=Schedule)

    def cancel(self, schedule_id: str) -> None:
        """
        Cancel a pending scheduled run.

        Args:
            schedule_id: ObjectId of the schedule to cancel.
        """
        self._client.delete(f"{_SCHEDULES_PATH}/{schedule_id}", cast_to=type(None))


class AsyncSchedulesResource(AsyncAPIResource):
    """Asynchronous interface to the Workflow Schedules API."""

    async def create(
        self,
        workflow_id: str,
        *,
        scheduled_time: datetime,
        run_input: Optional[RunInputOrDict] = None,
        version: Optional[int] = None,
        scheduled_by_name: Optional[str] = None,
    ) -> Schedule:
        """Schedule a workflow to run at a future UTC time."""
        body: Dict[str, Any] = {"scheduled_time": scheduled_time.isoformat()}
        if run_input is not None:
            body["run_input"] = serialise_config(run_input)
        if version is not None:
            body["version"] = version
        if scheduled_by_name is not None:
            body["scheduled_by_name"] = scheduled_by_name
        return await self._client.post(f"/v1/workflows/{workflow_id}/schedules", body=body, cast_to=Schedule)

    async def list(
        self,
        workflow_id: str,
        *,
        status: Optional[ScheduleStatus] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Schedule]:
        """List scheduled runs for a specific workflow.

        Returns a full ``List[Schedule]`` (not a paginated ``AsyncPage``)
        because the underlying endpoint is not paginated.
        """
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if status is not None:
            params["status"] = status.value if isinstance(status, ScheduleStatus) else status
        raw = await self._client.get(f"/v1/workflows/{workflow_id}/schedules", cast_to=list, params=params)
        return [Schedule.model_validate(item) for item in (raw or [])]

    async def list_all(
        self,
        *,
        status: Optional[ScheduleStatus] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Schedule]:
        """List all scheduled runs across the entire team."""
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if status is not None:
            params["status"] = status.value if isinstance(status, ScheduleStatus) else status
        raw = await self._client.get(_SCHEDULES_PATH, cast_to=list, params=params)
        return [Schedule.model_validate(item) for item in (raw or [])]

    async def get(self, schedule_id: str) -> Schedule:
        """Retrieve a single scheduled run by ID."""
        return await self._client.get(f"{_SCHEDULES_PATH}/{schedule_id}", cast_to=Schedule)

    async def update(
        self,
        schedule_id: str,
        *,
        scheduled_time: NotGivenOr[Optional[datetime]] = NOT_GIVEN,
        run_input: NotGivenOr[Optional[RunInputOrDict]] = NOT_GIVEN,
        version: NotGivenOr[Optional[int]] = NOT_GIVEN,
    ) -> Schedule:
        """Modify a pending scheduled run."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(scheduled_time) and scheduled_time is not None:
            body["scheduled_time"] = scheduled_time.isoformat()
        elif is_given(scheduled_time):
            body["scheduled_time"] = scheduled_time
        if is_given(run_input):
            body["run_input"] = serialise_config(run_input) if run_input is not None else run_input
        if is_given(version):
            body["version"] = version

        return await self._client.patch(f"{_SCHEDULES_PATH}/{schedule_id}", body=body, cast_to=Schedule)

    async def cancel(self, schedule_id: str) -> None:
        """Cancel a pending scheduled run."""
        await self._client.delete(f"{_SCHEDULES_PATH}/{schedule_id}", cast_to=type(None))
