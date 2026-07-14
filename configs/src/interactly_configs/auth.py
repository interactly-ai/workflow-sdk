from typing import Optional

from pydantic import BaseModel, Field


class OktaAuthConfig(BaseModel):
    """Configuration for Okta-based bearer-token authentication."""

    integration_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of an Okta integration to use for bearer-token authentication. "
            "When set, the runtime fetches a cached OAuth token from this integration "
            "and injects it as the Authorization header. "
            "Ignored when api_key or an Authorization default_header is already provided."
        ),
        title="Okta Integration ID",
    )
