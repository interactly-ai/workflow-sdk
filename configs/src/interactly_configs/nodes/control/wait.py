from datetime import datetime
from typing import Literal, Optional

from pydantic import Field, field_validator

from interactly_configs.nodes.control.base import (
    BaseControlNodeConfig,
    BaseControlNodeRunOutput,
    is_template,
)
from interactly_configs.nodes.node import BaseNodeRunInput
from interactly_configs.pauses import MAX_WAITING_SECONDS, PausableNodeConfig


class WaitNodeConfig(PausableNodeConfig, BaseControlNodeConfig):
    """
    Waits for a duration, or until a time, then carries on. A long wait pauses the run durably, so it survives a
    restart of the service.
    """

    type: Literal["wait"] = Field(default="wait", description="Type of the node. Must be 'wait'")
    duration_seconds: int = Field(
        default=60,
        ge=1,
        le=MAX_WAITING_SECONDS,
        description="How long to wait, in seconds: from 1 second to 30 days. Not used when 'Until' is set.",
        title="Duration (seconds)",
    )
    until: Optional[str] = Field(
        default=None,
        description=(
            "Wait until this time instead of for a duration: an ISO-8601 timestamp with its timezone offset, such as "
            "'2026-12-01T09:00:00-05:00'. May use {{dynamic}} and [[runtime]] variables, filled in when the node "
            "runs. At most 30 days ahead; a time already past carries on at once."
        ),
        title="Until",
    )
    output_runtime_variable_name: Optional[str] = Field(
        default="wait_result",
        description=(
            "Base name for the variables this node writes: '<name>' and '<name>_fired_at' (when the wait ended, "
            "ISO-8601 in UTC), '<name>_late_by_seconds' (how long after the time it ended), '<name>_success', and "
            "'<name>_error' when it could not wait."
        ),
        title="Output Variable Name",
    )

    @field_validator("until")
    @classmethod
    def _a_fixed_time_names_its_timezone(cls, value: Optional[str]) -> Optional[str]:
        # A template can only be read once its variables are filled in, so only a fixed time is checked here.
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not is_template(value) and parse_wait_until(value) is None:
            raise ValueError(
                f"'until' must be an ISO-8601 timestamp with its timezone offset, such as "
                f"'2026-12-01T09:00:00-05:00'; got {value!r}"
            )
        return value


class WaitNodeRunInput(BaseNodeRunInput):
    type: Literal["wait"] = Field(default="wait", description="Discriminator field which must always be 'wait'")


class WaitNodeRunOutput(BaseControlNodeRunOutput):
    type: Literal["wait"] = Field(default="wait", description="Discriminator field which must always be 'wait'")


def parse_wait_until(value: str) -> Optional[datetime]:
    """The time ``value`` names, or ``None`` unless it is an ISO-8601 timestamp that carries its timezone offset."""
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None
