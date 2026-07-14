from typing import Any, Literal, Optional

from pydantic import Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
)


class DeduplicateNodeConfig(BaseNodeConfig):
    type: Literal["deduplicate"] = Field(
        default="deduplicate",
        description="Type of the node. Must be 'deduplicate'",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.DATA_TRANSFORMATION.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.DEDUPLICATION.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    input_runtime_variable_name: Optional[str] = Field(
        default=None,
        description="Name of the runtime variable that holds the list of objects to deduplicate",
        title="Input Variable Name",
    )
    dedup_key: Optional[str] = Field(
        default=None,
        description=(
            "Dot-notation key path used to identify duplicates "
            "(e.g. 'id', 'user.email'). "
            "The first object with a given key value is kept; subsequent ones are removed. "
            "Objects missing the key are always kept. "
            "Ignored if dedup_key_runtime_variable_name is set."
        ),
        title="Dedup Key",
    )
    dedup_key_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the runtime variable holding the dot-notation key path. "
            "When set, this takes priority over the static dedup_key."
        ),
        title="Dedup Key Variable Name",
    )
    output_runtime_variable_name: Optional[str] = Field(
        default="deduplicate_result",
        description="Name of the runtime variable where the deduplicated list will be stored",
        title="Output Variable Name",
    )


class DeduplicateNodeRunInput(BaseNodeRunInput):
    type: Literal["deduplicate"] = Field(
        default="deduplicate",
        description="Discriminator field which must always be 'deduplicate'",
    )


class DeduplicateNodeRunOutput(BaseNodeRunOutput):
    type: Literal["deduplicate"] = Field(
        default="deduplicate",
        description="Discriminator field which must always be 'deduplicate'",
    )
    success: bool = Field(
        default=False,
        description="Indicates whether the deduplication was successful",
    )
    deduplicated_list: Optional[Any] = Field(
        default=None,
        description="The deduplicated list result",
    )
    removed_count: int = Field(
        default=0,
        description="Number of duplicate objects removed from the list",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the deduplication failed",
    )
