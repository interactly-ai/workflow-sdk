
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


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


#: Longest comment the API accepts.
#:
#: Comments are embedded in the workflow run document, which already carries every event of every
#: turn and is the thing under MongoDB's 16MB pressure. 5000 characters is roughly ten dense
#: paragraphs — far above any real review note — and ~20KB at worst in UTF-8, so a run would need
#: hundreds of maximum-length comments to threaten the document.
MAX_COMMENT_LENGTH = 5000


class CommentRequest(BaseModel):
    """
    Request body for leaving a comment. Everything else on ``CommentConfig`` is server-assigned.

    Separate from ``CommentConfig`` on purpose. That model is also the *stored* shape and is used to
    read records written before any of these rules existed, so constraining it would make legacy
    documents — including comments stored with null content — unreadable, and would fail the run
    fetch for every run holding one. Rules belong at the boundary, where new input arrives.

    Mirrors the ``RatingConfig`` / ``RatingRequest`` split in ``rating.py``.
    """

    content: str = Field(
        ...,
        max_length=MAX_COMMENT_LENGTH,
        description="Content of the comment",
        title="Comment Content",
    )

    @field_validator("content")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        # Stored trimmed, so "ok" and "ok   " are the same comment, and a whitespace-only body is
        # refused rather than stored as a comment nobody can see.
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Comment content cannot be blank.")
        return trimmed
