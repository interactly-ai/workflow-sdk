"""The route-coverage guard against a running server: every route the SDK calls is one the server serves.

`route_coverage` compares the SDK's requests with upstream *source*. A deployment can lag its source, so a method
the SDK learned for a route merged yesterday can still 404 on the server it is pointed at. This reads that
server's own OpenAPI document and checks the SDK's requests against it. WebSocket routes are not in OpenAPI and
are not checked here.

Requires credentials, so it is marked ``integration`` and skipped without them::

    pytest tests/integration/ -m integration
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]


@pytest.fixture(scope="module")
def served() -> Set[Tuple[str, str]]:
    """The (method, path) pairs the server's OpenAPI document lists, paths normalised as `route_coverage` does."""
    import route_coverage
    import schema_sync

    client = schema_sync.build_client()
    if client is None:
        pytest.skip("INTERACTLY_BASE_URL / INTERACTLY_API_KEY not set")
    with client:
        spec = schema_sync.get_json(client, "/openapi.json")
        if not spec:
            pytest.skip(f"server at {client.base_url} did not serve an OpenAPI document")
        # The service is mounted under a root path (`/workflows`) that its OpenAPI paths include.
        root_path = urlparse(str(client.base_url)).path.rstrip("/")

    pairs: Set[Tuple[str, str]] = set()
    for path, operations in (spec.get("paths") or {}).items():
        local = path[len(root_path) :] if root_path and path.startswith(root_path + "/") else path
        for method in operations:
            if method in route_coverage.VERBS:
                pairs.add((method.upper(), route_coverage.normalise_path(local)))
    return pairs


class TestLiveRouteCoverage:
    def test_every_route_the_sdk_calls_is_served(self, served):
        import route_coverage

        calls, _ = route_coverage.extract_sdk_calls(route_coverage.find_sdk_resources())
        # A call whose path renders more than one way is served when any of its renderings is.
        by_call: Dict[str, List[route_coverage.SdkCall]] = defaultdict(list)
        for call in calls:
            if call.method != "WS":
                by_call[call.call_id].append(call)
        unserved = sorted(
            {
                (group[0].method, group[0].path, group[0].location)
                for group in by_call.values()
                if not any(c.key in served for c in group)
            }
        )
        assert not unserved, (
            f"{len(unserved)} SDK request(s) go to routes this server does not serve: {unserved}. Either the server "
            "is behind the source the SDK follows, or the SDK calls a route that is gone."
        )

    def test_the_comparison_had_real_input(self, served):
        assert len(served) > 100, f"only {len(served)} routes read from the server's OpenAPI document"
