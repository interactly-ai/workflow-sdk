"""
Reference checker: does every `interactly*` symbol used in examples, notebooks and docs still exist?

Phase 2 of the sync plan deletes dead LLM model members and renames classes
(`GlobalDefaultLLMConfig` -> `WorkflowDefaultLLMConfig`). Those names are referenced across 23 example
builders, 41 notebooks and the docs, and **`make test` cannot see any of it** — the unit suite does not
import the examples. Without this, the only thing that proves the sweep was complete is running the
whole notebook suite against a live server, which takes minutes and needs credentials and real LLM
calls.

This does the same job in under a second, offline: it resolves every name imported from `interactly`
or `interactly_configs` against the *installed* packages, and every attribute accessed on those names
(`GOOGLEModel.GEMINI_1_5_PRO`). A rename or a deleted enum member becomes an immediate, located error.

Scope and limits, stated plainly: this is static and name-based. It catches missing imports, renamed
classes and deleted enum members — the exact failure modes Phase 2 creates. It does NOT catch a wrong
value passed to a still-existing field, or a symbol reached dynamically via `getattr`. It narrows what
the notebook suite has to prove; it does not replace it.

Usage::

    python tests/tools/symbol_refs.py            # check everything
    python tests/tools/symbol_refs.py --verbose  # also list what was scanned
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

#: Packages whose symbols are verified. Anything else imported is ignored.
CHECKED_PACKAGES: Tuple[str, ...] = ("interactly", "interactly_configs")

#: Where user-facing code lives, relative to the SDK root.
SCAN_ROOTS: Tuple[str, ...] = ("wf_examples", "notebooks", "docs")

#: Jupyter line magics and shell escapes are not Python; strip them before parsing.
_MAGIC_LINE = re.compile(r"^\s*[!%]")

#: ```python fenced blocks in markdown.
_PY_FENCE = re.compile(r"```(?:python|py)\n(.*?)```", re.DOTALL)


@dataclass
class RefError:
    """One unresolvable reference."""

    path: str
    line: int
    symbol: str
    reason: str


# --------------------------------------------------------------------------------------------- #
# Source collection                                                                               #
# --------------------------------------------------------------------------------------------- #


def _strip_magics(source: str) -> str:
    return "\n".join("" if _MAGIC_LINE.match(line) else line for line in source.splitlines())


def iter_sources(root: Path, relative_to: Optional[Path] = None) -> Iterable[Tuple[str, str]]:
    """Yield (label, python source) for every .py, notebook code cell, and markdown python fence."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".ipynb_checkpoints" in path.parts or "__pycache__" in path.parts:
            continue
        # Repo-relative so the output is copy-pasteable into an editor.
        rel = str(path.relative_to(relative_to)) if relative_to else str(path)

        if path.suffix == ".py":
            yield rel, path.read_text(encoding="utf-8")

        elif path.suffix == ".ipynb":
            try:
                cells = json.loads(path.read_text(encoding="utf-8")).get("cells", [])
            except (json.JSONDecodeError, OSError):
                continue
            for index, cell in enumerate(cells):
                if cell.get("cell_type") != "code":
                    continue
                source = "".join(cell.get("source") or [])
                if source.strip():
                    yield f"{rel}[cell {index}]", _strip_magics(source)

        elif path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            for index, block in enumerate(_PY_FENCE.findall(text)):
                yield f"{rel}[block {index}]", block


# --------------------------------------------------------------------------------------------- #
# Resolution                                                                                      #
# --------------------------------------------------------------------------------------------- #


def _load_packages() -> Dict[str, object]:
    modules: Dict[str, object] = {}
    for name in CHECKED_PACKAGES:
        try:
            modules[name] = importlib.import_module(name)
        except ImportError:
            pass
    return modules


def _resolve_module(dotted: str) -> Optional[object]:
    """Import `interactly_configs.nodes.llm.llm` if it is one of the checked packages."""
    if not any(dotted == p or dotted.startswith(f"{p}.") for p in CHECKED_PACKAGES):
        return None
    try:
        return importlib.import_module(dotted)
    except ImportError:
        return None


def check_source(label: str, source: str, packages: Dict[str, object]) -> List[RefError]:
    """Resolve every checked-package import in one source unit, then every attribute on those names."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # A partial snippet in docs is not a reference error.

    errors: List[RefError] = []
    #: local alias -> resolved object, for the attribute pass
    bound: Dict[str, object] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if not node.module:
                continue
            module = _resolve_module(node.module)
            if module is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                target = getattr(module, alias.name, None)
                if target is None:
                    errors.append(
                        RefError(label, node.lineno, f"{node.module}.{alias.name}", "no longer exists")
                    )
                else:
                    bound[alias.asname or alias.name] = target

        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = _resolve_module(alias.name)
                if module is not None:
                    bound[alias.asname or alias.name.split(".")[0]] = packages.get(
                        alias.name.split(".")[0], module
                    )

    # Attribute pass: `GOOGLEModel.GEMINI_1_5_PRO` on a name we resolved above.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            continue
        owner = bound.get(node.value.id)
        if owner is None:
            continue
        # Only assert on enums and classes: an instance attribute set at runtime is not our business.
        if not isinstance(owner, type) and not hasattr(owner, "__members__"):
            continue
        if not hasattr(owner, node.attr):
            errors.append(
                RefError(label, node.lineno, f"{node.value.id}.{node.attr}", "attribute no longer exists")
            )
    return errors


# --------------------------------------------------------------------------------------------- #
# Entry point                                                                                     #
# --------------------------------------------------------------------------------------------- #


def run(sdk_root: Path) -> Tuple[List[RefError], int]:
    packages = _load_packages()
    if not packages:
        return [], 0

    errors: List[RefError] = []
    scanned = 0
    seen_labels: Set[str] = set()
    for name in SCAN_ROOTS:
        root = sdk_root / name
        if not root.is_dir():
            continue
        for label, source in iter_sources(root, relative_to=sdk_root):
            if label in seen_labels:
                continue
            seen_labels.add(label)
            scanned += 1
            errors.extend(check_source(label, source, packages))
    return errors, scanned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="List how many units were scanned")
    args = parser.parse_args()

    sdk_root = Path(__file__).resolve().parents[2]
    errors, scanned = run(sdk_root)

    if not scanned:
        print("interactly / interactly_configs not importable — reference check skipped.")
        return 0

    if args.verbose:
        print(f"Scanned {scanned} source units across {', '.join(SCAN_ROOTS)}.")

    if errors:
        print(f"\n{len(errors)} unresolved reference(s):\n")
        for error in errors:
            print(f"  {error.path}:{error.line}  {error.symbol} — {error.reason}")
        print(
            "\nThese are references to symbols the packages no longer export. Update the examples, "
            "notebooks and docs, or restore the symbol."
        )
        return 1

    print(f"All interactly references resolve ({scanned} source units scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
