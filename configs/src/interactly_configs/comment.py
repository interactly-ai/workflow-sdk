from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

class CommentConfig(BaseModel):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "comment_" + str(uuid4()),
        description="Unique identifier for the comment",
        title="Comment Logical ID",
    )
    content: Optional[str] = Field(
        default=None,
        description="Content of the comment",
        title="Comment Content",
    )
    # Created By
    createdBy: Optional[str] = Field(
        default=None,
        description="ID of the user who created this edge",
    )
    # Updated By
    updatedBy: Optional[str] = Field(
        default=None,
        description="ID of the user who last updated this edge",
    )

    createdAt: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updatedAt: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def update_timestamp(self):
        self.updatedAt = datetime.now(timezone.utc)
        return self.updatedAt
