from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from interactly_configs.acls import AccessControlLevelConfig

class WorkflowTemplateConfig(AccessControlLevelConfig):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "workflow_template_" + str(uuid4()),
        description="Unique identifier for the workflow template",
        title="Workflow Template Logical ID",
    )
    workflow_id: Optional[str] = Field(
        default=None,
        description="The ID of the workflow this template belongs to",
        title="Workflow ID",
    )
