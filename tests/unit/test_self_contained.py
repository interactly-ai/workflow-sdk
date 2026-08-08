"""The SDK must be installable and usable without the `interactly-ai` monorepo.

This is the constraint the whole sync effort was built around: `interactly_configs` is a deliberate
*mirror* of `agentic_workflow_framework/configs`, duplicated rather than imported, precisely so a
customer can `pip install interactly` and never see the monorepo. Every phase reinforced it, and
nothing enforced it.

An import of `common`, `agentic_workflow_framework`, `beanie`, `bson` or `pymongo` would not fail in
this repository — the monorepo sits one directory up and is usually on the path during development.
It would fail in a customer's venv, at import time, with a `ModuleNotFoundError` naming a package they
have never heard of. That gap between "works here" and "works there" is what this file closes.

The walk is over the **AST**, not the text: a docstring citing `agentic_workflow_framework@e2885fac1`
for provenance is fine and useful, while `import agentic_workflow_framework` is not, and only parsing
tells them apart.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest
import tomllib

_SDK_ROOT = Path(__file__).resolve().parents[2]

#: The two directories that actually ship. Everything else in the repo — tests, notebooks, examples,
#: the drift harnesses — may import whatever it likes.
SHIPPED_PACKAGES = (
    _SDK_ROOT / "src" / "interactly",
    _SDK_ROOT / "configs" / "src" / "interactly_configs",
)

#: Top-level modules a shipped package must never import.
#:
#: The first three are monorepo-internal and would not exist in a customer's environment at all. The
#: last three are the server's persistence stack: importing them would drag MongoDB machinery into a
#: client whose entire job is to talk HTTP, and `bson.ObjectId` leaking into a public model is the
#: specific way that has happened before.
FORBIDDEN_ROOTS = frozenset(
    {
        "common",
        "agentic_workflow_framework",
        "workflow_service",
        "beanie",
        "bson",
        "pymongo",
    }
)

#: The two facades that import `interactly_configs` at module scope, inside a `try` that re-raises
#: with installation instructions. Everything else defers the import.
FACADE_MODULES = frozenset(
    {
        _SDK_ROOT / "src" / "interactly" / "configs.py",
        _SDK_ROOT / "src" / "interactly" / "runtime" / "events.py",
    }
)

#: Every module that reaches for the optional extra at all, in any of the three safe forms. Pinned so
#: a new one shows up in review rather than silently widening the surface that must degrade
#: gracefully when the extra is absent.
KNOWN_CONFIGS_IMPORTERS = frozenset(
    Path(p)
    for p in (
        "src/interactly/configs.py",
        "src/interactly/runtime/events.py",
        "src/interactly/runtime/handle.py",
        "src/interactly/types/_config_types.py",
        "src/interactly/types/edges/edge.py",
        "src/interactly/types/llm_configs/llm_config.py",
        "src/interactly/types/node_libraries/node_library.py",
        "src/interactly/types/nodes/node.py",
        "src/interactly/types/runs/run.py",
        "src/interactly/types/super_nodes/super_node.py",
        "src/interactly/types/tools/tool.py",
        "src/interactly/types/workflows/workflow.py",
    )
)


def _python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _imported_roots(tree: ast.AST) -> Iterator[Tuple[str, int]]:
    """Every top-level module name imported by this file, with its line number.

    Relative imports (`from . import x`) yield nothing: they cannot reach outside the package.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative
                continue
            if node.module:
                yield node.module.split(".")[0], node.lineno


def _unguarded_module_scope_imports(tree: ast.Module) -> Iterator[Tuple[str, int]]:
    """Imports that run unconditionally when the module is first imported.

    Only direct children of the module body count. Everything else is already safe for an optional
    dependency, in one of three ways:

    * inside ``if TYPE_CHECKING:`` — never executed at runtime;
    * inside a function — deferred to the call, which is where the caller opted in;
    * inside a top-level ``try`` — the facade pattern, which re-raises with install instructions.
    """
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.module.split(".")[0], node.lineno


def _all_shipped_files() -> List[Path]:
    files: List[Path] = []
    for package in SHIPPED_PACKAGES:
        files.extend(_python_files(package))
    return files


_SHIPPED_FILES = _all_shipped_files()


def test_both_shipped_packages_were_found():
    """A walk over an empty tree passes vacuously.

    Phase 0 found three of four quality gates in exactly that state, so discovery gets its own
    assertion rather than being trusted.
    """
    for package in SHIPPED_PACKAGES:
        assert package.is_dir(), f"shipped package not found: {package}"
    assert len(_SHIPPED_FILES) > 100, f"only {len(_SHIPPED_FILES)} shipped modules found"


class TestNoMonorepoImports:
    @pytest.mark.parametrize("path", _SHIPPED_FILES, ids=lambda p: str(p.relative_to(_SDK_ROOT)))
    def test_file_imports_nothing_from_the_monorepo(self, path: Path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders = [
            (root, lineno) for root, lineno in _imported_roots(tree) if root in FORBIDDEN_ROOTS
        ]
        assert not offenders, (
            f"{path.relative_to(_SDK_ROOT)} imports {offenders} — these do not exist in a customer's "
            "environment. The configs package is a deliberate mirror; copy the definition rather than "
            "importing it."
        )


class TestOptionalConfigsExtra:
    """`interactly` works without `interactly_configs` installed."""

    def test_no_module_imports_it_unguarded(self):
        """Ten modules reference `interactly_configs`; none may do so unconditionally.

        They use the three safe forms — ``if TYPE_CHECKING:`` for annotations, function-local imports
        for runtime upgrades, and a top-level ``try`` in the two facades. An unguarded module-scope
        import would break ``import interactly`` outright for anyone who installed the base package.
        """
        offenders = []
        for path in _python_files(SHIPPED_PACKAGES[0]):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for root, lineno in _unguarded_module_scope_imports(tree):
                if root == "interactly_configs":
                    offenders.append(f"{path.relative_to(_SDK_ROOT)}:{lineno}")

        assert not offenders, (
            f"{offenders} import interactly_configs unguarded at module scope. The typed configs are "
            'an optional extra — `pip install "interactly[configs]"` — so this breaks the base '
            "install at import time. Use `if TYPE_CHECKING:`, a function-local import, or the facade "
            "try/except pattern."
        )

    def test_the_guarded_importers_are_the_ones_we_expect(self):
        """Tracks WHICH modules reach for the optional extra, so a new one is a deliberate decision.

        Not a correctness constraint — the test above is — but each addition widens the surface that
        has to keep degrading gracefully, and that is worth noticing in review.
        """
        importers = set()
        for path in _python_files(SHIPPED_PACKAGES[0]):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if any(root == "interactly_configs" for root, _ in _imported_roots(tree)):
                importers.add(path.relative_to(_SDK_ROOT))

        assert importers == KNOWN_CONFIGS_IMPORTERS, (
            "the set of modules touching the optional configs extra changed:\n"
            f"  added:   {sorted(importers - KNOWN_CONFIGS_IMPORTERS)}\n"
            f"  removed: {sorted(KNOWN_CONFIGS_IMPORTERS - importers)}\n"
            "If deliberate, update KNOWN_CONFIGS_IMPORTERS — and check the new module degrades "
            "gracefully without the extra."
        )

    @pytest.mark.parametrize("path", sorted(FACADE_MODULES))
    def test_the_facades_guard_the_import(self, path: Path):
        """Each facade wraps its import in `try` and re-raises with installation instructions.

        Without the guard the failure is a bare ModuleNotFoundError for a package the caller has no
        reason to know the name of.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        guarded = any(
            isinstance(node, ast.Try)
            and any(
                root == "interactly_configs"
                for child in ast.walk(node)
                for root, _ in _imported_roots(child)
            )
            for node in ast.walk(tree)
        )
        assert guarded, f"{path.relative_to(_SDK_ROOT)} imports interactly_configs without a try/except"


class TestDriftHarnessesStayInTests:
    """`tests/tools/config_parity.py` is the only code that knows where `interactly-ai` lives.

    It has to: comparing the mirror against upstream source means locating that source. Which is
    exactly why it must never become reachable from a shipped package — it would turn an optional
    development convenience into a hard requirement on a directory the customer does not have.
    """

    def test_no_shipped_module_imports_a_harness(self):
        harness_names = {"config_parity", "schema_sync", "symbol_refs"}
        offenders = []
        for path in _SHIPPED_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for root, lineno in _imported_roots(tree):
                if root in harness_names or root == "tests":
                    offenders.append(f"{path.relative_to(_SDK_ROOT)}:{lineno} imports {root}")
        assert not offenders, offenders

    def test_the_monorepo_locator_lives_only_in_the_harness(self):
        """Grep-level, deliberately: this catches a *path* being reconstructed, not just an import."""
        locators = []
        for path in _SHIPPED_FILES:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            # Strings inside code, not docstrings or comments — a provenance note citing an upstream
            # commit is fine and there are several.
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if "INTERACTLY_AI_ROOT" in node.value:
                        locators.append(f"{path.relative_to(_SDK_ROOT)}:{node.lineno}")
        assert not locators, (
            f"{locators} reference the monorepo location from a shipped package"
        )


class TestPackagingBoundary:
    """The built wheels contain the package and nothing else."""

    @pytest.mark.parametrize(
        "pyproject_rel,expected",
        [
            ("pyproject.toml", "src/interactly"),
            ("configs/pyproject.toml", "src/interactly_configs"),
        ],
    )
    def test_wheel_ships_only_the_package(self, pyproject_rel: str, expected: str):
        data = tomllib.loads((_SDK_ROOT / pyproject_rel).read_text(encoding="utf-8"))
        packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        assert packages == [expected], (
            f"{pyproject_rel} would ship {packages}; tests/ and the drift harnesses must stay out of "
            "the wheel"
        )

    def test_no_monorepo_runtime_dependency(self):
        """A dependency on anything monorepo-shaped would defeat the whole arrangement."""
        for rel in ("pyproject.toml", "configs/pyproject.toml"):
            data = tomllib.loads((_SDK_ROOT / rel).read_text(encoding="utf-8"))
            declared = " ".join(data["project"].get("dependencies", [])).lower()
            for forbidden in ("agentic", "workflow-service", "beanie", "pymongo"):
                assert forbidden not in declared, f"{rel} declares a dependency on {forbidden}"

    def test_the_configs_extra_is_optional(self):
        """`interactly_configs` must be an extra, never a base dependency."""
        data = tomllib.loads((_SDK_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        base = " ".join(data["project"].get("dependencies", []))
        extras = data["project"].get("optional-dependencies", {})

        assert "interactly-configs" not in base, "the typed configs must stay optional"
        assert "configs" in extras, "the `configs` extra is what the docs tell people to install"
        assert any("interactly-configs" in spec for spec in extras["configs"])


class TestVersionsAgree:
    """Both packages carry a *single* source of version truth, and everything reads from it.

    `_version.py` claimed to be that source while both `pyproject.toml` files hardcoded the number
    alongside it — two values free to disagree, with nothing to notice when they did. They are now
    wired with `[tool.hatch.version]`, and these tests keep it that way.
    """

    @pytest.mark.parametrize(
        "pyproject_rel,version_path",
        [
            ("pyproject.toml", "src/interactly/_version.py"),
            ("configs/pyproject.toml", "src/interactly_configs/_version.py"),
        ],
    )
    def test_pyproject_reads_the_version_file(self, pyproject_rel: str, version_path: str):
        data = tomllib.loads((_SDK_ROOT / pyproject_rel).read_text(encoding="utf-8"))

        assert "version" not in data["project"], (
            f"{pyproject_rel} hardcodes a version alongside {version_path}; that is two sources of "
            "truth. Use `dynamic = [\"version\"]`."
        )
        assert data["project"].get("dynamic") == ["version"]
        assert data["tool"]["hatch"]["version"]["path"] == version_path

    @pytest.mark.parametrize(
        "module_name,version_file",
        [
            ("interactly", SHIPPED_PACKAGES[0] / "_version.py"),
            ("interactly_configs", SHIPPED_PACKAGES[1] / "_version.py"),
        ],
    )
    def test_dunder_version_matches_the_version_file(self, module_name: str, version_file: Path):
        module = sys.modules.get(module_name) or __import__(module_name)
        namespace: dict = {}
        exec(version_file.read_text(encoding="utf-8"), namespace)  # noqa: S102 - reading our own file
        assert module.__version__ == namespace["__version__"]
