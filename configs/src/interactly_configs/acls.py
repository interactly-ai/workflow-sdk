"""Access-control and UI field-type enums mirrored from ``common/models/acls.py``.

The dashboard-only ``json_schema_extra`` annotation *keys* that upstream defines here are
deliberately not mirrored — the config models in this package drop those annotations entirely (see
the package README). The enums below are mirrored because they are referenced by value in config
payloads, not only in presentation metadata.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class UILoginRole(str, Enum):
    """
    Enum representing different roles in the ACLs.
    """

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    DEVELOPER = "developer"
    USER = "user"


class UISpecialFieldTypes(str, Enum):
    """
    Enum representing special field types for ACLs.
    """

    DATETIME_ISO8601 = "datetime_iso8601"
    DATE_PICKER = "date_picker"
    TIME_PICKER = "time_picker"
    DATE_RANGES_PICKER = "date_ranges_picker"
    TEXTAREA = "textarea"
    PASSWORD = "password"
    NUMBER_WITH_SLIDER = "number_with_slider"
    JSON_EDITOR = "json_editor"
    COLOR_SECTION = "color_section"
    ASSISTANT_SELECTION_WITH_ID = "assistant_selection_with_assistant_id"
    ASSISTANT_SELECTION_WITH_PHONE = "assistant_selection_with_assistant_phone"
    EXTERNAL_URL_LINK = "external_url_link"
    TIMEZONE = "timezone"
    KNOWLEDGE_BASE_SELECTION = "knowledge_base_selection"
    LLM_CONFIG_SELECTION = "llm_config_selection"
    INBUILT_TOOL_SELECTION = "inbuilt_tool_selection"
    INLINE_PYTHON_TOOL_SELECTION = "inline_python_tool_selection"
    EXTERNAL_API_TOOL_SELECTION = "external_api_tool_selection"
    KB_TOOL_SELECTION = "kb_tool_selection"
    INTEGRATIONS_SELECTION = "integrations_selection"
    PHONE_NUMBERS_SELECTION = "phone_numbers_selection"
    PROMPTS_SELECTION = "prompts_selection"
    PRACTITIONERS_SELECTION = "practitioners_selection"
    VISITING_REASONS_SELECTION = "visiting_reasons_selection"
    INTEGRATIONS_USE_CASES_SELECTION = "integrations_use_cases_selection"
    INTEGRATIONS_LOCATIONS_SELECTION = "integrations_locations_selection"
    INTEGRATIONS_APPOINTMENT_TYPES_SELECTION = "integrations_appointment_types_selection"
    INTEGRATIONS_PATIENTS_SELECTION = "integrations_patients_selection"
    INTEGRATIONS_APPOINTMENTS_SELECTION = "integrations_appointments_selection"
    INTEGRATIONS_VISIT_STATUS_SELECTION = "integrations_visit_status_selection"
    WORKFLOW_SELECTION_WITH_ID = "workflow_selection_with_workflow_id"
    WORKFLOW_SELECTION_WITH_VERSION_NUMBER = "workflow_selection_with_version_number"
    SINGLE_FIELD_OBJECT = "single_field_object"
    # A tool's variable_arguments / result_variable_mappings. Both are arrays of objects, which the
    # generic renderer already handles — as one collapsed "Item N" accordion per row, with no summary and
    # no cross-row validation. These two ask the dashboard for a row-per-binding table instead: the
    # fields interact (variable_path is meaningless when source is literal), duplicate argument names
    # silently shadow one another, and the whole point of the feature is that a misconfigured binding
    # fails quietly.
    VARIABLE_ARGUMENTS_EDITOR = "variable_arguments_editor"
    RESULT_VARIABLE_MAPPINGS_EDITOR = "result_variable_mappings_editor"


class AccessControlLevel(str, Enum):
    """
    Enum representing different access control levels.
    """
    PERSONAL = "personal"
    TEAM = "team"
    SYSTEM = "system"

class AccessControlLevelConfig(BaseModel):
    """
    Access control configuration for an entity.
    """
    access_level: Optional[AccessControlLevel] = Field(
        default=AccessControlLevel.PERSONAL,
        description="Access level for the entity",
        title="Access Level",
    )
    access_list: Optional[List[str]] = Field(
        default=None,
        description="List of user IDs or team IDs that have access to this entity",
        title="Access List",
    )
