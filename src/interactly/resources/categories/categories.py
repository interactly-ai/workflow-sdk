"""
CategoriesResource — read workflow categories.

Endpoints:
    GET /v1/workflow-categories    → list
"""

from __future__ import annotations

from typing import Dict, List

from interactly._resource import AsyncAPIResource, SyncAPIResource

__all__ = ["CategoriesResource", "AsyncCategoriesResource"]

_PATH = "/v1/workflow-categories"


class CategoriesResource(SyncAPIResource):
    """Synchronous interface to the Workflow Categories API."""

    def list(self) -> List[str]:
        """
        Retrieve all available workflow category names for the team.

        Returns global defaults merged with team-specific custom categories,
        deduplicated, globals first.

        Returns:
            A list of category name strings.
        """
        raw: Dict = self._client.get(_PATH, cast_to=dict)
        return raw.get("categories", [])


class AsyncCategoriesResource(AsyncAPIResource):
    """Asynchronous interface to the Workflow Categories API."""

    async def list(self) -> List[str]:
        """Retrieve all available workflow category names for the team."""
        raw: Dict = await self._client.get(_PATH, cast_to=dict)
        return raw.get("categories", [])
