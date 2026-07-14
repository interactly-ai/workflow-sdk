"""LLM group configuration — multiple LLMs with fallback/parallel strategies."""

import random
from enum import Enum
from typing import Annotated, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from interactly_configs.llm import LLMConfig


class OperationMode(str, Enum):
    # All LLMs queried in parallel immediately; wait until min patience time or all respond.
    PARALLEL_SELECT_ONE = "parallel_select_one"

    # First LLM queried initially; if it doesn't respond within min patience time,
    # the rest are kicked off in parallel.
    SEQUENTIAL_WITH_PROACTIVE = "sequential_with_proactive"


class SelectionMode(str, Enum):
    RANDOM = "random"
    SEQUENCE = "sequence"

    def select(self, items: List[str], prev_index: int = -1) -> Optional[str]:
        """Select an item from the list based on the selection mode."""
        if not items:
            return None

        if self == SelectionMode.RANDOM:
            return random.choice(items)
        elif self == SelectionMode.SEQUENCE:
            next_index = min(prev_index + 1, len(items) - 1)
            return items[next_index]
        else:
            raise ValueError(f"Unknown selection mode: {self}")


class LLMGroupConfig(BaseModel):
    type: Literal["llm_group"] = Field(
        default="llm_group",
        description="Discriminator field — must always be 'llm_group'.",
    )
    logical_id: Optional[str] = Field(
        default_factory=lambda: "llm_group_" + str(uuid4()),
        description="Unique identifier for the LLM Group",
        title="LLM Group Logical ID",
    )
    llms: List[LLMConfig] = Field(
        default_factory=list,
        description="List of LLM configurations, in preferred order of use.",
        title="LLM Group",
    )
    operation_mode: Optional[OperationMode] = Field(
        default=OperationMode.SEQUENTIAL_WITH_PROACTIVE,
        description="Operation mode for the LLM group",
        title="Operation Mode",
    )
    min_patience_time_ms: Optional[int] = Field(
        default=1500,
        description=(
            "Grace period in milliseconds until which we will unconditionally wait, "
            "unless all LLMs have responded."
        ),
        title="Minimum Patience Time",
    )
    max_patience_time_ms: Optional[int] = Field(
        default=None,
        description=(
            "Threshold milliseconds after which we will stop waiting. "
            "If no LLM has responded by this time, we will return None."
        ),
        title="Maximum Patience Time",
    )

    model_config = ConfigDict(title="Group of LLMs")


class LLMGroupWithBackchannelConfig(BaseModel):
    type: Literal["llm_group_with_backchannel"] = Field(
        default="llm_group_with_backchannel",
        description="Discriminator field — must always be 'llm_group_with_backchannel'.",
    )
    id: Optional[str] = Field(
        default_factory=lambda: "llm_group_with_backchannel_" + str(uuid4()),
        description="Unique identifier for the LLM Group",
        title="LLM Group With Backchannel ID",
    )
    main_llm_config: Optional[LLMGroupConfig] = Field(
        default=None,
        description="Configuration for the main LLM",
        title="Main LLM Configuration",
    )
    non_backchannel_response_prefix: Optional[str] = Field(
        default=None,
        description=(
            "If backchannel response is being sent, only the LLM output "
            "following this prefix will follow the backchannel response."
        ),
        title="Non Backchannel Response Prefix",
    )
    backchannel_llm_config: Optional[LLMGroupConfig] = Field(
        default=None,
        description="Configuration for the back channel LLM",
        title="Backchannel LLM Configuration",
    )
    backchannel_static_responses: List[str] = Field(
        default_factory=list,
        description="List of static responses from which one will be selected as a backchannel response.",
        title="Backchannel Static Responses",
    )
    backchannel_static_responses_selection_mode: Optional[SelectionMode] = Field(
        default=SelectionMode.RANDOM,
        description="Selection mode for backchannel static responses",
        title="Backchannel Static Responses Selection Mode",
    )
    backchannel_min_patience_time_ms: Optional[int] = Field(
        default=2000,
        description=(
            "Grace period in milliseconds until which we will unconditionally wait "
            "for the main LLM to respond."
        ),
        title="Backchannel Minimum Patience Time",
    )

    model_config = ConfigDict(title="Group of regular and backchanneling LLMs")


LLMOrGroupConfig = Annotated[
    Union[LLMConfig, LLMGroupConfig, LLMGroupWithBackchannelConfig],
    Field(discriminator="type"),
]
