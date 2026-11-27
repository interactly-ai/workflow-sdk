"""The drift harnesses, promoted from "a make target someone remembers to run" to real tests.

This is the durable fix for the problem that started this whole effort: **the SDK drifted from the
workflow service for three weeks and nobody noticed.** Three tools were built to detect that, and they
worked — but only when invoked by hand. A guard nobody runs is not a guard.

Each test degrades to a skip rather than a failure when its input is unavailable, so the suite stays
green offline, in CI without the monorepo, and without credentials:

* **parity** needs the `interactly-ai` checkout — skipped when absent.
* **references** needs the packages importable — skipped when not.
* **schema** needs a live server — it lives in ``tests/integration`` and is marked ``integration``.

The report files under ``docs/_sync/`` are still the place to *read* the detail; these tests exist to
make the count failing loudly the default.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


# --------------------------------------------------------------------------------------------- #
# Source parity: the vendored mirror vs. upstream `agentic_workflow_framework`                    #
# --------------------------------------------------------------------------------------------- #


class TestConfigParity:
    """`configs/src/interactly_configs` must stay a faithful mirror of upstream.

    Duplication is the deliberate design here — the mirror exists so the SDK can be installed without
    the monorepo — which means the only thing standing between it and silent divergence is this
    comparison.
    """

    @staticmethod
    def _report():
        import config_parity as cp

        root = cp.find_interactly_ai_root()
        if root is None:
            pytest.skip("interactly-ai checkout not found (set INTERACTLY_AI_ROOT to point at it)")

        if not cp.upstream_paths(root):
            pytest.skip(f"no upstream config sources under {root}")
        return cp.build_report(root)

    #: Differences that are known and attributed. **Zero**, measured 2026-11-26 against upstream ``main`` at
    #: a87b31348. Keep it at zero by mirroring an upstream change in the same pull request that notices it.
    #:
    #: Held as a **ratchet rather than an ignore**: the guard fails if the total moves in either
    #: direction. Up is new drift; down is a closed gap whose number nobody lowered.
    #:
    #: If drift has to be carried for a while, raise this with an attributed breakdown beside it rather
    #: than allow-listing the gaps: the allow-lists are for divergences that are *deliberate*, and an
    #: unfollowed upstream change is not. And do not leave the guard red instead: it once sat red at 40
    #: for weeks, and a red guard cannot tell you that a 41st difference just appeared.
    KNOWN_UPSTREAM_DEBT = 0

    #: Class docstrings that differ between upstream and the mirror, counted apart from the total above
    #: because prose and contract read badly in one number. Measured 2026-11-26: **78** — 38 classes
    #: documented upstream and not in the mirror (mostly event classes), 6 documented only in the mirror,
    #: 34 documented differently on each side. A ratchet for the same reason as the one above: before it
    #: existed, upstream rewrote six ECS node docstrings and nothing said so.
    KNOWN_DOCSTRING_DRIFT = 78

    def test_no_new_drift_against_upstream(self):
        report = self._report()
        if report.total < self.KNOWN_UPSTREAM_DEBT:
            pytest.fail(
                f"Parity improved to {report.total} difference(s), below the recorded debt of "
                f"{self.KNOWN_UPSTREAM_DEBT}. Lower KNOWN_UPSTREAM_DEBT and update its breakdown, so the "
                f"guard keeps measuring something."
            )
        if report.total > self.KNOWN_UPSTREAM_DEBT:
            # Name the categories rather than dumping the whole diff: the markdown report is the place
            # for that, and a 100-line assertion message helps nobody.
            summary = "\n".join(
                f"  {label}: {len(items)}"
                for label, items in [*report.counted_categories(), ("placement", report.placement)]
                if items
            )
            pytest.fail(
                f"interactly_configs has drifted from upstream: {report.total} difference(s), above the "
                f"recorded debt of {self.KNOWN_UPSTREAM_DEBT}.\n{summary}\n\n"
                f"Run `make parity-check` for the full report."
            )

    def test_docstring_drift_has_not_moved(self):
        report = self._report()
        drift = len(report.docstring_mismatches)
        assert drift == self.KNOWN_DOCSTRING_DRIFT, (
            f"{drift} class docstring(s) now differ from upstream; the recorded count is "
            f"{self.KNOWN_DOCSTRING_DRIFT}. If the mirror caught up, lower KNOWN_DOCSTRING_DRIFT. If upstream "
            "changed a docstring, copy it into the mirror. `make parity-check` lists every one."
        )

    def test_the_harness_actually_compared_something(self):
        """A harness that silently finds nothing to compare reports zero differences too.

        Three of four quality gates were once found in exactly that state — passing because they were
        checking nothing. This asserts each comparison had real input.
        """
        import config_parity as cp

        root = cp.find_interactly_ai_root()
        if root is None:
            pytest.skip("interactly-ai checkout not found")

        upstream_roots = cp.upstream_paths(root)
        mirror_roots = [cp.find_mirror_configs()]
        upstream = cp.extract_tree(upstream_roots)
        mirror = cp.extract_tree(mirror_roots)

        assert len(upstream) > 50, f"only {len(upstream)} upstream classes parsed — harness is broken"
        assert len(mirror) > 50, f"only {len(mirror)} mirror classes parsed — harness is broken"
        assert len(upstream_roots) == len(cp.UPSTREAM_SOURCES), (
            f"only {len(upstream_roots)} of {len(cp.UPSTREAM_SOURCES)} upstream sources exist — a moved "
            "file would silently drop out of the comparison"
        )

        upstream_unions = cp.extract_unions(upstream_roots)
        mirror_unions = cp.extract_unions(mirror_roots)
        for name in ("LLMConfigUnion", "ToolConfig", "NodeConfig", "EdgeConfig", "Event"):
            assert name in upstream_unions, f"union `{name}` not found upstream — union extraction is broken"
            assert name in mirror_unions, f"union `{name}` not found in the mirror — union extraction is broken"

        nonmember_exprs = sum(len(info.nonmember_exprs) for info in upstream.values())
        assert nonmember_exprs >= len(cp.KNOWN_HOISTED_NONMEMBERS), (
            "fewer upstream nonmember expressions captured than hoisted entries — value comparison is "
            "checking nothing"
        )


# --------------------------------------------------------------------------------------------- #
# Route coverage: the SDK's requests vs. upstream's routes                                        #
# --------------------------------------------------------------------------------------------- #


class TestRouteCoverage:
    """Every public route reachable, with every query field it reads, and no request to a route that is gone.

    The config models had two harnesses; the client's own requests had none, so every route and filter the server
    gained was found by hand, a sync late.
    """

    #: Findings known and attributed, measured against upstream ``main`` at a87b31348: **87**.
    #:
    #: * 11 public routes no SDK method calls: the four evaluation-workflow routes; LLM-config export, import and
    #:   usage; simulation-group pause and resume; workflow and tool usage.
    #: * 73 query fields no SDK method can send: the date window (``start``/``end``, 30) and ``search`` (6) that
    #:   every paginated list reads; ``version_number`` on node, edge and super-node routes (14); ``logical_id``
    #:   on six lists; ``workflow_type`` (3); the workflow, simulation, template and tool list filters;
    #:   ``find_active_version``; ``backend``; ``dry_run``.
    #: * 3 query keys the SDK sends that the server does not read, so the filter silently does nothing:
    #:   ``workflow_id`` on the tool list; ``category`` and ``created_by_me`` on the active-versions list.
    #:
    #: A ratchet, like parity's: up is a new gap, down is a closed one whose number nobody lowered.
    KNOWN_ROUTE_DEBT = 87

    @staticmethod
    def _report():
        import config_parity as cp
        import route_coverage as rc

        root = cp.find_interactly_ai_root()
        if root is None:
            pytest.skip("interactly-ai checkout not found (set INTERACTLY_AI_ROOT to point at it)")
        return rc, rc.build_report(root)

    def test_no_new_gaps_against_upstream(self):
        _, report = self._report()
        if report.total != self.KNOWN_ROUTE_DEBT:
            summary = "\n".join(f"  {label}: {len(items)}" for label, items in report.counted_categories() if items)
            pytest.fail(
                f"Route coverage reads {report.total} finding(s); the recorded debt is {self.KNOWN_ROUTE_DEBT}.\n"
                f"{summary}\n\nRun `make route-check` for the full report. If a gap closed, lower KNOWN_ROUTE_DEBT "
                "and its breakdown; if one opened, follow the server's change."
            )

    def test_the_harness_actually_compared_something(self):
        rc, report = self._report()
        public = [r for r in report.upstream_routes if r.public]
        assert len(public) > 150, f"only {len(public)} public upstream routes parsed — route extraction is broken"
        assert len(report.sdk_calls) > 200, f"only {len(report.sdk_calls)} SDK requests read — extraction is broken"
        assert any(r.method == "WS" and r.public for r in report.upstream_routes), "no run socket upstream"
        assert any(c.method == "WS" for c in report.sdk_calls), "the SDK's run socket was not found"
        runs = next(r for r in public if r.key == ("GET", "/v1/workflow-runs"))
        # A query model (`filters: WorkflowRunFilter = Query()`) and a dependency class (`PaginationRequest`).
        assert {"needs_attention", "source_turn_index", "page", "size", "start"} <= runs.query, (
            f"GET /v1/workflow-runs reads {sorted(runs.query)} — query-model or dependency expansion is broken"
        )

    def test_allow_listed_routes_are_still_public_and_still_uncalled(self):
        rc, report = self._report()
        public = {r.key for r in report.upstream_routes if r.public}
        called = {c.key for c in report.sdk_calls}
        for key, reason in rc.KNOWN_UNCOVERED_ROUTES.items():
            assert reason.strip(), f"KNOWN_UNCOVERED_ROUTES[{key}] has no stated reason"
            assert key in public, f"KNOWN_UNCOVERED_ROUTES[{key}] is no longer a public upstream route — drop it"
            assert key not in called, f"KNOWN_UNCOVERED_ROUTES[{key}] is now called by the SDK — drop it"

    def test_every_query_allowance_suppressed_something(self):
        rc, report = self._report()
        for mapping_name in ("KNOWN_UNCOVERED_QUERY_FIELDS", "KNOWN_SDK_ONLY_QUERY_FIELDS"):
            for key, reason in getattr(rc, mapping_name).items():
                assert reason.strip(), f"{mapping_name}[{key}] has no stated reason"
                method, path, name = key
                assert f"{mapping_name}:{method} {path} {name}" in report.allowances_used, (
                    f"{mapping_name}[{key}] suppressed nothing — the route or the SDK changed; drop the entry"
                )
        for location, reason in rc.KNOWN_UNRENDERABLE_CALLS.items():
            assert reason.strip(), f"KNOWN_UNRENDERABLE_CALLS[{location}] has no stated reason"
            assert f"KNOWN_UNRENDERABLE_CALLS:{location}" in report.allowances_used, (
                f"KNOWN_UNRENDERABLE_CALLS[{location}] suppressed nothing — the call is readable now; drop the entry"
            )


# --------------------------------------------------------------------------------------------- #
# Wire values: the SDK's hand-written enum twins and close codes                                  #
# --------------------------------------------------------------------------------------------- #


class TestWireValues:
    """Values `src/interactly/` restates by hand from the server, which no other harness compares."""

    #: Findings known and attributed, measured against upstream ``main`` at a87b31348: **1**.
    #:
    #: * ``SimulationStatus`` (``interactly.types``) lacks ``paused`` (upstream since 2026-11-23).
    KNOWN_WIRE_DEBT = 1

    @staticmethod
    def _report():
        import config_parity as cp
        import wire_values as wv

        root = cp.find_interactly_ai_root()
        if root is None:
            pytest.skip("interactly-ai checkout not found (set INTERACTLY_AI_ROOT to point at it)")
        return wv, wv.build_report(root)

    def test_no_new_gaps_against_upstream(self):
        _, report = self._report()
        if report.total != self.KNOWN_WIRE_DEBT:
            summary = "\n".join(f"  {label}: {items}" for label, items in report.counted_categories() if items)
            pytest.fail(
                f"Wire values read {report.total} finding(s); the recorded debt is {self.KNOWN_WIRE_DEBT}.\n"
                f"{summary}\n\nRun `make wire-check` for the full report."
            )

    def test_the_harness_actually_compared_something(self):
        wv, report = self._report()
        assert report.twins_compared == len(wv.ENUM_TWINS), (
            f"only {report.twins_compared} of {len(wv.ENUM_TWINS)} enum twins were read: {report.broken_twins}"
        )
        assert len(report.upstream_close_codes) > 10, (
            f"only {sorted(report.upstream_close_codes)} close codes found upstream — extraction is broken"
        )
        assert wv.sdk_typed_close_codes(wv.find_sdk_package()), "the SDK's close-code map was not found"

    def test_allow_lists_still_earn_their_place(self):
        wv, report = self._report()
        for mapping_name in ("KNOWN_UNRELATED_NAMESAKES", "KNOWN_TWIN_VALUE_DIVERGENCES", "KNOWN_UNTYPED_CLOSE_CODES"):
            for key, reason in getattr(wv, mapping_name).items():
                assert reason.strip(), f"{mapping_name}[{key}] has no stated reason"
                assert f"{mapping_name}:{key}" in report.allowances_used, (
                    f"{mapping_name}[{key}] suppressed nothing — drop the entry"
                )


# --------------------------------------------------------------------------------------------- #
# Symbol references in docs, notebooks and examples                                               #
# --------------------------------------------------------------------------------------------- #


class TestSymbolReferences:
    """Every `interactly` / `interactly_configs` symbol named in docs, notebooks and examples resolves.

    Renaming a class or deleting an enum member breaks those files without touching a single unit
    test. This is the check that catches it, and it runs offline in well under a second.
    """

    def test_all_references_resolve(self):
        import symbol_refs

        sdk_root = Path(__file__).resolve().parents[2]
        errors, scanned = symbol_refs.run(sdk_root)

        if not scanned:
            pytest.skip("interactly / interactly_configs not importable")

        if errors:
            shown = "\n".join(f"  {e}" for e in errors[:15])
            more = f"\n  … and {len(errors) - 15} more" if len(errors) > 15 else ""
            pytest.fail(
                f"{len(errors)} unresolved reference(s) across docs/notebooks/examples:\n{shown}{more}"
            )

    def test_the_scan_covered_the_corpus(self):
        """Same reasoning as the parity guard: zero units scanned would also report zero errors."""
        import symbol_refs

        _, scanned = symbol_refs.run(Path(__file__).resolve().parents[2])
        if not scanned:
            pytest.skip("interactly / interactly_configs not importable")

        assert scanned > 300, f"only {scanned} source units scanned — discovery is broken"


# --------------------------------------------------------------------------------------------- #
# The allow-lists themselves                                                                      #
# --------------------------------------------------------------------------------------------- #


class TestAllowListsAreStillEarningTheirPlace:
    """Parity reads 0 partly *because* of the allow-lists. Nothing audited the allow-lists.

    Every entry suppresses a real difference for a stated reason. When that reason expires — upstream
    deletes the class, adopts the divergence, or renames the field — the entry keeps suppressing
    something that is no longer there, and the 0 stops meaning what a reader assumes it means.

    Found by exactly this check: `BaseAPIModel` sat on ``KNOWN_ONLY_MIRROR`` while living in
    ``src/interactly/`` — outside the tree the harness parses — so it suppressed nothing on either
    side and merely implied the mirror contained a class it did not.
    """

    @staticmethod
    def _trees():
        import config_parity as cp

        root = cp.find_interactly_ai_root()
        if root is None:
            pytest.skip("interactly-ai checkout not found")
        return cp, cp.extract_tree(cp.upstream_paths(root)), cp.extract_tree([cp.find_mirror_configs()])

    def test_only_upstream_entries_are_still_only_upstream(self):
        cp, upstream, mirror = self._trees()
        for name in cp.KNOWN_ONLY_UPSTREAM:
            assert name in upstream, (
                f"KNOWN_ONLY_UPSTREAM['{name}'] no longer exists upstream — drop the entry"
            )
            assert name not in mirror, (
                f"KNOWN_ONLY_UPSTREAM['{name}'] is now vendored — drop the entry so parity compares it"
            )

    def test_only_mirror_entries_are_still_only_in_the_mirror(self):
        cp, upstream, mirror = self._trees()
        for name in cp.KNOWN_ONLY_MIRROR:
            assert name in mirror, (
                f"KNOWN_ONLY_MIRROR['{name}'] is not in the parsed mirror. Either it was removed, or "
                "it lives outside configs/src/interactly_configs — where this harness never looks, so "
                "the entry suppresses nothing."
            )
            assert name not in upstream, (
                f"KNOWN_ONLY_MIRROR['{name}'] now exists upstream too — drop the entry so parity "
                "compares them"
            )

    def test_field_divergences_still_diverge(self):
        cp, upstream, mirror = self._trees()
        for key, reason in cp.KNOWN_FIELD_DIVERGENCES.items():
            class_name, field_name = key.rsplit(".", 1)

            assert class_name in mirror, f"KNOWN_FIELD_DIVERGENCES['{key}'] names a class the mirror lacks"
            mirror_type = cp.resolve_fields(class_name, mirror).get(field_name)
            assert mirror_type is not None, (
                f"KNOWN_FIELD_DIVERGENCES['{key}'] names a field the mirror no longer declares"
            )

            upstream_type = (
                cp.resolve_fields(class_name, upstream).get(field_name) if class_name in upstream else None
            )
            if upstream_type is None:
                # Legitimate: upstream may inherit the field from a base this harness cannot parse —
                # `WorkflowTemplateConfig.access_*` come from a Beanie mixin in `common/`. Absence
                # upstream is not staleness, so there is nothing further to check.
                continue

            assert cp._normalise_type(upstream_type) != cp._normalise_type(mirror_type), (
                f"KNOWN_FIELD_DIVERGENCES['{key}'] no longer diverges — both sides are now "
                f"`{mirror_type}`. Drop the entry ({reason})."
            )

    def test_hoisted_nonmembers_are_still_declared_upstream(self):
        """The hoist exists because `enum.nonmember` is 3.11+ and this package supports 3.10.

        If upstream stops declaring one, the mirror is carrying a constant nothing corresponds to.
        """
        cp, upstream, _ = self._trees()
        for key in sorted(cp.KNOWN_HOISTED_NONMEMBERS):
            class_name, attribute = key.rsplit(".", 1)
            assert class_name in upstream, f"KNOWN_HOISTED_NONMEMBERS['{key}'] names an unknown enum"
            assert attribute in upstream[class_name].nonmembers, (
                f"KNOWN_HOISTED_NONMEMBERS['{key}'] is no longer declared upstream — drop the entry"
            )

    def test_hoisted_nonmembers_point_at_a_real_mirror_symbol(self):
        """The mapping's value is what the contents are compared against, so it has to exist.

        A typo here would read as "contents differ" rather than "no such symbol", which sends the reader
        looking at the wrong thing.
        """
        cp, _, _ = self._trees()
        constants = cp.extract_module_constants([cp.find_mirror_configs()])
        for key, symbol in sorted(cp.KNOWN_HOISTED_NONMEMBERS.items()):
            assert symbol in constants, (
                f"KNOWN_HOISTED_NONMEMBERS['{key}'] points at `{symbol}`, which the mirror does not define "
                "at module scope"
            )

    def test_unmirrored_dependencies_are_still_imported(self):
        cp, _, _ = self._trees()
        root = cp.find_interactly_ai_root()
        imported = {name for _, _, name in cp.find_unmirrored_dependencies(root, cp.upstream_paths(root), True)}
        for name in cp.KNOWN_UNMIRRORED_DEPENDENCIES:
            assert name in imported, (
                f"KNOWN_UNMIRRORED_DEPENDENCIES['{name}'] is no longer imported from outside the parsed "
                "sources — drop the entry"
            )

    def test_validator_renames_still_describe_a_rename(self):
        """Each rename must name a validator upstream still has, and one the mirror carries renamed."""
        cp, upstream, mirror = self._trees()
        for key, mirror_method in cp.KNOWN_VALIDATOR_RENAMES.items():
            class_name, upstream_method = key.rsplit(".", 1)
            upstream_methods = {cp.validator_method_name(s) for s in cp.resolve_validators(class_name, upstream)}
            mirror_methods = {cp.validator_method_name(s) for s in cp.resolve_validators(class_name, mirror)}
            assert upstream_method in upstream_methods, (
                f"KNOWN_VALIDATOR_RENAMES['{key}']: upstream no longer has `{upstream_method}` — drop the entry"
            )
            assert mirror_method in mirror_methods, (
                f"KNOWN_VALIDATOR_RENAMES['{key}']: the mirror has no `{mirror_method}` — drop or fix the entry"
            )
            assert upstream_method != mirror_method, f"KNOWN_VALIDATOR_RENAMES['{key}'] renames to itself"

    def test_every_entry_carries_a_reason(self):
        """A bare entry is indistinguishable from one added to make a failure go away."""
        cp, _, _ = self._trees()
        for mapping_name in (
            "KNOWN_ONLY_UPSTREAM",
            "KNOWN_ONLY_MIRROR",
            "KNOWN_FIELD_DIVERGENCES",
            "KNOWN_UNMIRRORED_DEPENDENCIES",
        ):
            for name, reason in getattr(cp, mapping_name).items():
                assert reason and reason.strip(), f"{mapping_name}['{name}'] has no stated reason"
