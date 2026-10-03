"""The live schema guard, promoted from a make target to a test.

`config_parity` compares the SDK's vendored models against upstream *source*. This compares them
against what a **running server** actually publishes, which catches a different class of drift: a
field added to the deployed service without a corresponding source change reaching the checkout, or a
mirror that matches stale upstream perfectly.

Requires credentials, so it is marked ``integration`` and skipped without them::

    pytest tests/integration/ -m integration
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]


@pytest.fixture(scope="module")
def report():
    import schema_sync

    client = schema_sync.build_client()
    if client is None:
        pytest.skip("INTERACTLY_BASE_URL / INTERACTLY_API_KEY not set")

    with client:
        if schema_sync.get_json(client, "/v1/nodes/types") is None:
            pytest.skip(f"server at {client.base_url} unreachable or rejected the credential")
        yield schema_sync.run(client)


class TestLiveSchemaSync:
    def test_no_findings_against_the_live_server(self, report):
        if report.findings:
            shown = "\n".join(f"  {f}" for f in report.findings[:15])
            more = f"\n  … and {len(report.findings) - 15} more" if len(report.findings) > 15 else ""
            pytest.fail(
                f"{len(report.findings)} schema difference(s) vs. the live server:\n{shown}{more}\n\n"
                "Run `make schema-check` for the full report."
            )

    def test_every_endpoint_maps_to_a_local_model(self, report):
        """An unmapped endpoint is drift too — the quiet kind.

        A server that grows a config type the mirror lacks shows up here rather than being silently
        skipped, which is the failure mode this harness was built to close.
        """
        assert not report.unmapped, (
            f"{len(report.unmapped)} endpoint(s) have no local model: {report.unmapped}"
        )

    def test_the_comparison_had_real_input(self, report):
        """Zero endpoints compared would also report zero findings.

        ``compared`` is the list of (endpoint, model) pairs the run actually reached.
        """
        assert len(report.compared) > 10, (
            f"only {len(report.compared)} schema(s) compared — the harness is not reaching the server"
        )

    def test_nested_models_were_compared(self, report):
        """Root-only comparison is how four LLM configs stayed invisible; prove the `$defs` walk ran."""
        assert len(report.nested_compared) > 30, (
            f"only {len(report.nested_compared)} nested model(s) compared — the `$defs` walk is not running"
        )
        assert "GoogleLLMConfig" in report.nested_compared, (
            "GoogleLLMConfig is embedded in every LLM node schema and was not compared"
        )

    def test_every_allow_list_entry_suppressed_something(self, report):
        """An allow-list entry whose reason has expired keeps the count low for nothing.

        Checked here rather than offline because both lists describe what the *server* publishes.
        """
        import schema_sync

        expected = {f"KNOWN_SERIALIZER_DROPPED_DEFAULTS:{name}" for name in schema_sync.KNOWN_SERIALIZER_DROPPED_DEFAULTS}
        expected |= {f"KNOWN_SERVER_ONLY_DEFS:{name}" for name in schema_sync.KNOWN_SERVER_ONLY_DEFS}
        unused = sorted(expected - report.allowances_used)
        assert not unused, f"allow-list entries that suppressed nothing against this server: {unused}"
