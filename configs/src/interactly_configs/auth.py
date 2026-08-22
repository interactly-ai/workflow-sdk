from typing import Optional

from pydantic import BaseModel, Field


class IntegrationAuthConfig(BaseModel):
    """Configuration for integration-backed bearer-token authentication.

    Provider-agnostic: any integration that exposes an OAuth2 client-credentials
    token endpoint (Okta, Athena, ECW, ...) can be referenced here. The runtime
    only needs the integration ID – the integrations service resolves the
    provider and returns the bearer token.
    """

    integration_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of an integration to use for bearer-token authentication. "
            "When set, the runtime fetches a cached OAuth token from this integration "
            "and injects it as the Authorization header. "
            "Ignored when api_key or an Authorization default_header is already provided."
        ),
        title="Integration ID",
    )


# Backwards-compatible alias – the config used to be Okta-specific. Mirrors the same alias upstream
# keeps, so existing code importing ``OktaAuthConfig`` from this package continues to work.
OktaAuthConfig = IntegrationAuthConfig
