from typing import Optional

from pydantic import BaseModel, Field


class AthenaBaseRunInput(BaseModel):
    override_api_key: Optional[str] = Field(
        default=None,
        description="Override API key for the node",
        title="Override API Key",
    )
