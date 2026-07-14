from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

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
