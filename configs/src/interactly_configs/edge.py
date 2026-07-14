"""Edge configuration models."""

from enum import Enum
from typing import Annotated, Literal, Optional, Type, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from interactly_configs.base import BaseEntityConfig
from interactly_configs.condition import ConditionConfig


class EdgeType(str, Enum):
    DIRECT = "direct"
    CONDITIONAL = "conditional"
    COMPANION = "companion"

    @classmethod
    def get_type_to_config_map(cls) -> dict["EdgeType", Type["BaseEdgeConfig"]]:
        """Returns a mapping of edge types to their respective configuration classes."""
        return {
            cls.DIRECT: DirectEdgeConfig,
            cls.CONDITIONAL: ConditionalEdgeConfig,
            cls.COMPANION: CompanionEdgeConfig,
        }

    @classmethod
    def get_type_to_run_input_map(cls) -> dict["EdgeType", Type["BaseEdgeRunInput"]]:
        """Returns a mapping of edge types to their respective run-input classes."""
        return {
            cls.DIRECT: BaseEdgeRunInput,
            cls.CONDITIONAL: BaseEdgeRunInput,
            cls.COMPANION: BaseEdgeRunInput,
        }


class BaseEdgeConfig(BaseEntityConfig):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "edge_" + str(uuid4()),
        description="Unique identifier for the edge",
        title="Edge Logical ID",
    )
    name: Optional[str] = Field(default=None, description="Name of the edge", title="Edge Name")
    description: Optional[str] = Field(default=None, description="Description of the edge", title="Edge Description")
    source_node_logical_id: Optional[str] = Field(
        default=None,
        description="Logical ID of the source node for this edge",
        title="Source Node Logical ID",
    )
    destination_node_logical_id: Optional[str] = Field(
        default=None,
        description="Logical ID of the target node for this edge",
        title="Destination Node Logical ID",
    )


class DirectEdgeConfig(BaseEdgeConfig):
    type: Literal["direct"] = Field(
        default=EdgeType.DIRECT.value,
        description="Type of the edge. Always 'direct' for this config.",
        title="Edge Type",
    )

    model_config = ConfigDict(title="Direct Edge")


class ConditionalEdgeConfig(BaseEdgeConfig):
    type: Literal["conditional"] = Field(
        default=EdgeType.CONDITIONAL.value,
        description="Type of the edge. Always 'conditional' for this config.",
        title="Edge Type",
    )
    condition: Optional[ConditionConfig] = Field(
        default=None,
        description="Condition that determines whether this edge is taken",
        title="Edge Condition",
    )

    model_config = ConfigDict(title="Conditional Edge")


class CompanionEdgeConfig(BaseEdgeConfig):
    type: Literal["companion"] = Field(
        default=EdgeType.COMPANION.value,
        description="Type of the edge. Always 'companion' for this config.",
        title="Edge Type",
    )

    model_config = ConfigDict(title="Companion Edge")


EdgeConfig = Annotated[
    Union[DirectEdgeConfig, ConditionalEdgeConfig, CompanionEdgeConfig],
    Field(discriminator="type"),
]


class BaseEdgeRunInput(BaseModel):
    miscellaneous: dict = Field(
        default_factory=dict,
        description="Miscellaneous run-input data that can be used by the edge",
        title="Miscellaneous Edge Run Input",
    )
