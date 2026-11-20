from typing import Any, Dict, Literal, Optional

from pydantic import Field, field_validator

from interactly_configs.nodes.control.base import (
    BaseControlNodeConfig,
    BaseControlNodeRunOutput,
    is_template,
)
from interactly_configs.nodes.node import BaseNodeRunInput
from interactly_configs.pauses import MAX_WAITING_SECONDS, SIGNAL_KEY_RULE, PausableNodeConfig, is_signal_key


class WaitForSignalNodeConfig(PausableNodeConfig, BaseControlNodeConfig):
    """
    Waits until another system posts a signal to the run under this node's key, or until its timeout passes.
    """

    type: Literal["wait_for_signal"] = Field(
        default="wait_for_signal", description="Type of the node. Must be 'wait_for_signal'"
    )
    signal_key: Optional[str] = Field(
        default=None,
        description=(
            f"The key the signal is posted under, POST /v1/workflow-runs/<run id>/signals/<key>: {SIGNAL_KEY_RULE}. "
            "May use {{dynamic}} and [[runtime]] variables, filled in when the node runs, such as "
            "'order-[[order_id]]'. A run waits on a key at one node at a time."
        ),
        title="Signal Key",
    )
    payload_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "A JSON Schema the signal's body must satisfy. A post whose body fails it is refused, and the run goes on "
            "waiting. At most 16 KiB; 'pattern' and 'patternProperties' are not allowed, and a '$ref' may only name "
            "a part of this schema."
        ),
        title="Payload Schema",
    )
    timeout_seconds: int = Field(
        default=MAX_WAITING_SECONDS,
        ge=1,
        le=MAX_WAITING_SECONDS,
        description=(
            "How long to wait for the signal, in seconds: from 1 second to 30 days, which is the default. A signal "
            "that has not come by then is a failure the workflow can route on."
        ),
        title="Timeout (seconds)",
    )
    output_runtime_variable_name: Optional[str] = Field(
        default="signal_result",
        description=(
            "Base name for the variables this node writes: '<name>' (the signal's body), '<name>_timed_out', "
            "'<name>_success', and '<name>_error' when no signal came or the node could not wait."
        ),
        title="Output Variable Name",
    )

    @field_validator("signal_key")
    @classmethod
    def _a_fixed_key_follows_the_signal_key_rule(cls, value: Optional[str]) -> Optional[str]:
        # A template can only be checked once its variables are filled in, so only a fixed key is checked here.
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not is_template(value) and not is_signal_key(value):
            raise ValueError(f"'signal_key' must be {SIGNAL_KEY_RULE}; got {value!r}")
        return value

    @field_validator("payload_schema")
    @classmethod
    def _an_empty_schema_is_none(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return value or None


class WaitForSignalNodeRunInput(BaseNodeRunInput):
    type: Literal["wait_for_signal"] = Field(
        default="wait_for_signal", description="Discriminator field which must always be 'wait_for_signal'"
    )


class WaitForSignalNodeRunOutput(BaseControlNodeRunOutput):
    type: Literal["wait_for_signal"] = Field(
        default="wait_for_signal", description="Discriminator field which must always be 'wait_for_signal'"
    )
