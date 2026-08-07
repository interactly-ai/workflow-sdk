from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SuperNodeFieldMappingTargetType(str, Enum):
    NODE_CONFIG_FIELD = "node_config_field"
    DYNAMIC_VARIABLE = "dynamic_variable"
    EDGE_CONFIG_FIELD = "edge_config_field"
    WORKFLOW_CONFIG_FIELD = "workflow_config_field"
    RUNTIME_VARIABLE = "runtime_variable"

class SuperNodeInputFieldValueType(str, Enum):
    """Declared shape of a super node input field's leaf value.

    Used at parent-workflow publish time to validate ``SuperNodeConfig.field_values``
    against the interface declared by the sub-workflow.
    """

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    ENUM = "enum"
    ANY = "any"

class SuperNodeFieldMapping(BaseModel):
    """Defines where a super node input field value should be injected."""

    target_type: SuperNodeFieldMappingTargetType = Field(
        description=(
            "Where to inject the field value: into a node's config field ('node_config_field'), "
            "an edge's config field ('edge_config_field'), the sub-workflow's WorkflowConfig "
            "('workflow_config_field'), a dynamic variable ('dynamic_variable'), "
            "or a runtime variable ('runtime_variable')."
        ),
        title="Target Type",
    )
    # For NODE_CONFIG_FIELD and EDGE_CONFIG_FIELD (consolidated):
    target_node_or_edge_logical_id: Optional[str] = Field(
        default=None,
        description=(
            "Logical ID of the node or edge in the sub-workflow whose config field should be set. "
            "Required when target_type is 'node_config_field' or 'edge_config_field'."
        ),
        title="Target Node or Edge Logical ID",
    )
    target_field_path: Optional[str] = Field(
        default=None,
        description=(
            "Dot-separated path to the target field. "
            "For 'node_config_field': path within the target node's config, e.g. 'main_response_config.prompt'. "
            "For 'edge_config_field': path within the target edge's config, e.g. 'condition.condition_string'. "
            "For 'workflow_config_field': path within the sub-workflow's WorkflowConfig, e.g. 'default_prompt_prefix'. "
            "Required when target_type is 'node_config_field', 'edge_config_field', or 'workflow_config_field'."
        ),
        title="Target Field Path",
    )
    # For DYNAMIC_VARIABLE and RUNTIME_VARIABLE:
    target_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the variable to set. "
            "For 'dynamic_variable': sets a {{var}} dynamic variable, e.g. 'patient_name'. "
            "For 'runtime_variable': injects into the sub-workflow's runtime_variables dict. "
            "Required when target_type is 'dynamic_variable' or 'runtime_variable'."
        ),
        title="Target Variable Name",
    )

class SuperNodeInputField(BaseModel):
    """Defines one configuration field that callers must provide when instantiating this super node."""

    name: str = Field(
        description="Unique key for this field within the super node interface. Callers set field_values[name] = value.",
        title="Field Name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of what this field controls",
        title="Description",
    )
    required: bool = Field(
        default=True,
        description="Whether this field must be provided by callers. If False and not provided, default_value is used.",
        title="Required",
    )
    default_value: Optional[Any] = Field(
        default=None,
        description="Default value used when required=False and the caller does not provide a value",
        title="Default Value",
    )
    json_schema: Optional[dict] = Field(
        default=None,
        description="JSON Schema for this field, used by the UI to render and validate the config form",
        title="JSON Schema",
    )
    mappings: List[SuperNodeFieldMapping] = Field(
        default_factory=list,
        description="Where and how to inject the provided value into the sub-workflow (node/edge config fields or dynamic variables)",
        title="Mappings",
    )
    value_type: SuperNodeInputFieldValueType = Field(
        default=SuperNodeInputFieldValueType.ANY,
        description=(
            "Declared shape of the leaf value. Used at publish time to reject malformed "
            "field_values. Default 'any' preserves legacy behaviour (no shape check)."
        ),
        title="Value Type",
    )
    enum_values: Optional[List[Any]] = Field(
        default=None,
        description="Required when value_type='enum'. Caller's value must be in this list.",
        title="Enum Values",
    )
    min_value: Optional[float] = Field(
        default=None,
        description="Inclusive lower bound for integer/number value types.",
        title="Min Value",
    )
    max_value: Optional[float] = Field(
        default=None,
        description="Inclusive upper bound for integer/number value types.",
        title="Max Value",
    )
    min_length: Optional[int] = Field(
        default=None,
        description="Inclusive lower length for string/array value types.",
        title="Min Length",
    )
    max_length: Optional[int] = Field(
        default=None,
        description="Inclusive upper length for string/array value types.",
        title="Max Length",
    )

class SuperNodeInterface(BaseModel):
    """
    The interface definition of a super node.

    Describes what configuration fields callers must provide when instantiating this super node,
    and how those field values map into the encapsulated sub-workflow's nodes, edges, and dynamic variables.
    """

    input_fields: List[SuperNodeInputField] = Field(
        default_factory=list,
        description="List of input fields exposed by this super node to calling workflows",
        title="Input Fields",
    )
