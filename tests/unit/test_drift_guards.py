"""The drift harnesses, promoted from "a make target someone remembers to run" to real tests.

This is the durable fix for the problem that started this whole effort: **the SDK drifted from the
workflow service for three weeks and nobody noticed.** Three tools were built in Phase 1 to detect
that, and they worked — but only when invoked by hand. A guard nobody runs is not a guard.

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

        upstream_roots = cp.upstream_paths(root)
        if not upstream_roots:
            pytest.skip(f"no upstream config sources under {root}")

        upstream = cp.extract_tree(upstream_roots)
        mirror = cp.extract_tree([cp.find_mirror_configs()])
        return cp.compare(upstream, mirror)

    def test_no_differences_against_upstream(self):
        report = self._report()
        if report.total:
            # Name the categories rather than dumping the whole diff: the markdown report is the place
            # for that, and a 100-line assertion message helps nobody.
            summary = "\n".join(
                f"  {label}: {len(items)}"
                for label, items in (
                    ("classes missing", report.missing_classes),
                    ("classes extra", report.extra_classes),
                    ("fields missing", report.missing_fields),
                    ("fields extra", report.extra_fields),
                    ("type mismatches", report.type_mismatches),
                    ("default mismatches", report.default_mismatches),
                    ("constraint mismatches", report.constraint_mismatches),
                    ("validators missing", report.missing_validators),
                    ("enum values missing", report.missing_enum_values),
                    ("enum values extra", report.extra_enum_values),
                    ("nonmembers missing", report.missing_nonmembers),
                    ("placement", report.placement),
                )
                if items
            )
            pytest.fail(
                f"interactly_configs has drifted from upstream ({report.total} difference(s)):\n"
                f"{summary}\n\nRun `make parity-check` for the full report."
            )

    def test_the_harness_actually_compared_something(self):
        """A harness that silently finds nothing to compare reports zero differences too.

        Phase 0 found three of four quality gates in exactly that state — passing because they were
        checking nothing. This asserts the comparison had real input.
        """
        import config_parity as cp

        root = cp.find_interactly_ai_root()
        if root is None:
            pytest.skip("interactly-ai checkout not found")

        upstream = cp.extract_tree(cp.upstream_paths(root))
        mirror = cp.extract_tree([cp.find_mirror_configs()])

        assert len(upstream) > 50, f"only {len(upstream)} upstream classes parsed — harness is broken"
        assert len(mirror) > 50, f"only {len(mirror)} mirror classes parsed — harness is broken"


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

    def test_every_entry_carries_a_reason(self):
        """A bare entry is indistinguishable from one added to make a failure go away."""
        cp, _, _ = self._trees()
        for mapping_name in ("KNOWN_ONLY_UPSTREAM", "KNOWN_ONLY_MIRROR", "KNOWN_FIELD_DIVERGENCES"):
            for name, reason in getattr(cp, mapping_name).items():
                assert reason and reason.strip(), f"{mapping_name}['{name}'] has no stated reason"
