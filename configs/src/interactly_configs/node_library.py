from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer

from interactly_configs.acls import AccessControlLevel

class NodeLibraryConfig(BaseModel):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "node_library_" + str(uuid4()),
        description="Unique identifier for the node library",
        title="Node Library Logical ID",
    )
    name: Optional[str] = Field(default=None, description="Name of the Node Library", title="Node Library Name")
    description: Optional[str] = Field(
        default=None,
        description="Description of the node library",
        title="Node Library Description",
    )
    nodes: Optional[list[str]] = Field(
        default_factory=list,
        description="List of node IDs that are part of this library",
        title="Nodes",
    )

    @field_serializer("nodes", when_used="json")
    def _ser_nodes(self, v: Optional[list[str]]) -> Optional[list[str]]:
        # Need this to serialize str to string for JSON output
        return [str(id) for id in v] if v else None

    access_level: Optional[AccessControlLevel] = Field(
        default=AccessControlLevel.PERSONAL,
        description="Access level for the node library",
        title="Access Level",
    )
    access_list: Optional[list[str]] = Field(
        default=None,
        description="List of user IDs or team IDs that have access to this node library",
        title="Access List",
    )

    @field_serializer("access_list", when_used="json")
    def _ser_access_list(self, v: Optional[list[str]]) -> Optional[list[str]]:
        # Need this to serialize str to string for JSON output
        return [str(id) for id in v] if v else None
