from typing import Optional

from pydantic import BaseModel, Field

class AthenaBaseRunOutput(BaseModel):
    success: bool = Field(
        default=False,
        description="Indicates whether the Athena node was successful",
        title="Athena Node Successful",
    )
    status_code: Optional[int] = Field(
        default=None,
        description="Status code returned by the Athena node",
        title="Status Code",
    )
    response: Optional[dict] = Field(
        default=None,
        description="Response data from the Athena node",
        title="Response",
    )
