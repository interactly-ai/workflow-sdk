"""
TypedDicts for schedule request parameters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from typing_extensions import NotRequired, Required, TypedDict

from interactly.types._config_types import RunInputOrDict
from interactly.types.schedules.schedule import ScheduleStatus

__all__ = ["ScheduleCreateParams", "ScheduleUpdateParams", "ScheduleListParams"]


class ScheduleCreateParams(TypedDict, total=False):
    scheduled_time: Required[datetime]
    run_input: NotRequired[Optional[RunInputOrDict]]
    version: NotRequired[Optional[int]]
    scheduled_by_name: NotRequired[Optional[str]]


class ScheduleUpdateParams(TypedDict, total=False):
    scheduled_time: NotRequired[Optional[datetime]]
    run_input: NotRequired[Optional[RunInputOrDict]]
    version: NotRequired[Optional[int]]


class ScheduleListParams(TypedDict, total=False):
    status: Optional[ScheduleStatus]
    skip: int
    limit: int
