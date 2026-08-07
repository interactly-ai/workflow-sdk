"""Reviewer ratings on workflow-run events and turns."""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class RatingValue(str, Enum):
    """
    Quality judgement a reviewer can leave on a workflow run event or turn.

    Stored as the string, never as the numeric score: a score is derivable (see ``RATING_SCORES``)
    and keeping the name means new values can be added without re-interpreting existing records.
    """

    DOWN = "down"
    UP = "up"
    STRONG_UP = "strong_up"


#: Numeric weight per rating, for aggregation and analytics. Not persisted.
RATING_SCORES: Dict[RatingValue, int] = {
    RatingValue.DOWN: -1,
    RatingValue.UP: 1,
    RatingValue.STRONG_UP: 2,
}


class RatingConfig(BaseModel):
    """
    One reviewer's rating of one target (a run event, or a run turn).

    At most one rating per user per target — re-rating replaces the caller's record rather than
    appending, so ``createdBy`` is effectively the identity key within a target's rating list.
    """

    logical_id: Optional[str] = Field(
        default_factory=lambda: "rating_" + str(uuid4()),
        description="Unique identifier for the rating",
        title="Rating Logical ID",
    )
    value: RatingValue = Field(
        description="The rating left by the user",
        title="Rating Value",
    )
    # Created By
    createdBy: Optional[str] = Field(
        default=None,
        description="ID of the user who created this rating",
    )
    # Updated By
    updatedBy: Optional[str] = Field(
        default=None,
        description="ID of the user who last updated this rating",
    )

    createdAt: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updatedAt: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def update_timestamp(self) -> datetime:
        self.updatedAt = datetime.now(timezone.utc)
        return self.updatedAt


class RatingRequest(BaseModel):
    """Request body for setting a rating. Everything else on ``RatingConfig`` is server-assigned."""

    value: RatingValue = Field(
        description="The rating to leave on the target",
        title="Rating Value",
    )
