"""Base entity configuration — shared by nodes and edges.

Pure-Pydantic, client-safe base model: identifiers are plain strings and no
dashboard-internal UI annotations are attached.
"""

from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class BaseEntityConfig(BaseModel):
    """Base configuration shared by all nodes and edges."""

    logical_id: Optional[str] = Field(
        default_factory=lambda: "entity_" + str(uuid4()),
        description="Unique identifier for the entity",
        title="Entity Logical ID",
    )
    name: Optional[str] = Field(
        default=None,
        description="Name of the entity",
        title="Entity Name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the entity",
        title="Entity Description",
    )
    workflow_id: Optional[str] = Field(
        default=None,
        description="The DB Object ID of the workflow this entity belongs to",
        title="Workflow DB Object ID",
    )
    version_number: Optional[int] = Field(
        default=0,
        description=(
            "Version number of the workflow this entity belongs to. "
            "0 is the initial version (default)."
        ),
        title="Workflow Version Number",
    )
    disabled: bool = Field(
        default=False,
        description=(
            "If true, this entity will be disabled and will not execute its function. "
            "Useful for testing workflows without actually executing this specific entity."
        ),
        title="Disabled",
    )
    miscellaneous: dict = Field(
        default_factory=dict,
        description="Miscellaneous config data that can be used by the entity",
        title="Miscellaneous Config",
    )
