from typing import Any, List, Literal, Optional

from pydantic import Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
)


class FieldExtractorNodeConfig(BaseNodeConfig):
    type: Literal["field_extractor"] = Field(
        default="field_extractor",
        description="Type of the node. Must be 'field_extractor'",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.DATA_TRANSFORMATION.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.EXTRACTION.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    input_runtime_variable_name: Optional[str] = Field(
        default=None,
        description="Name of the runtime variable that holds the input JSON to be filtered",
        title="Input Variable Name",
    )
    keys_to_retain: List[str] = Field(
        default_factory=list,
        description=(
            "Static list of key paths to retain in the output. "
            "Supports dot notation for nested keys (e.g. 'address.city'), "
            "bracket notation for arrays (e.g. 'orders[].id' for all elements, "
            "'orders[1].id' for a specific index). "
            "Ignored if keys_to_retain_runtime_variable_name is set."
        ),
        title="Keys to Retain",
    )
    keys_to_retain_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the runtime variable holding the list of key paths to retain. "
            "When set, this takes priority over the static keys_to_retain list."
        ),
        title="Keys to Retain Variable Name",
    )
    output_runtime_variable_name: Optional[str] = Field(
        default="field_extractor_result",
        description="Name of the runtime variable where the extracted result will be stored",
        title="Output Variable Name",
    )


class FieldExtractorNodeRunInput(BaseNodeRunInput):
    type: Literal["field_extractor"] = Field(
        default="field_extractor",
        description="Discriminator field which must always be 'field_extractor'",
    )


class FieldExtractorNodeRunOutput(BaseNodeRunOutput):
    type: Literal["field_extractor"] = Field(
        default="field_extractor",
        description="Discriminator field which must always be 'field_extractor'",
    )
    success: bool = Field(
        default=False,
        description="Indicates whether the extraction was successful",
    )
    extracted_result: Optional[Any] = Field(
        default=None,
        description="The extracted/filtered JSON result",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the extraction failed",
    )
