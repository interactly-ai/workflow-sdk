"""Headless end-to-end runner for the docs notebooks.

Executes each notebook in ``notebooks/`` against a live Interactly server
(the same server the SDK talks to) and reports a
per-notebook PASS/FAIL, surfacing the failing cell source and error on failure.

This is maintainer tooling (underscore-prefixed, like ``_bootstrap.py``); it is
**not** a lesson notebook.

Usage (from the ``workflow_sdk`` dir)::

    pipenv run python notebooks/_run_e2e.py            # run all (core + wf_example_notebooks)
    pipenv run python notebooks/_run_e2e.py 01 09 16   # run a subset (by number/name)
    pipenv run python notebooks/_run_e2e.py --list      # just list what would run

Credentials are read from the SDK's ``.env`` file (loaded automatically at
startup); your shell environment always wins over ``.env``. Each notebook is
executed in the ``notebooks/`` working directory so its first ``import _bootstrap``
cell resolves the in-folder ``interactly`` package. Notebooks in the
``wf_example_notebooks/`` subfolder are discovered too.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

NOTEBOOKS_DIR = Path(__file__).resolve().parent
SDK_ROOT = NOTEBOOKS_DIR.parent
DEFAULT_CELL_TIMEOUT = 240  # seconds; LLM turns can be slow


def _load_env() -> None:
    """Load the SDK's ``.env`` (shell env wins) so the client only needs the .env file."""
    env_path = SDK_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=str(env_path), override=False)
    except Exception:
        pass


def _ensure_kernel() -> None:
    """Guarantee the ``python3`` kernel points at the interpreter running this script.

    Notebooks run through nbclient, which starts a kernel by name. A globally
    registered ``python3`` kernelspec that points at a stale/removed interpreter
    (e.g. an old virtualenv) makes every notebook fail before executing. To stay
    fully self-contained and avoid touching global state, mint a throwaway
    ``python3`` kernelspec that uses ``sys.executable`` (this venv) and prepend it
    to ``JUPYTER_PATH`` so it always wins over any stale spec on the machine.
    """
    import json
    import tempfile

    kroot = Path(tempfile.mkdtemp(prefix="wfsdk-kernels-"))
    kdir = kroot / "kernels" / "python3"
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                "display_name": "Python 3 (workflow_sdk)",
                "language": "python",
            }
        )
    )
    existing = os.environ.get("JUPYTER_PATH", "")
    os.environ["JUPYTER_PATH"] = str(kroot) + (os.pathsep + existing if existing else "")


def _discover(selectors: list[str]) -> list[Path]:
    """Return the notebooks to run (core + subfolders), filtered by ``selectors``.

    Discovery is recursive so ``wf_example_notebooks/`` is included; hidden dirs
    and Jupyter checkpoints are skipped.
    """
    all_nbs = sorted(
        p
        for p in NOTEBOOKS_DIR.rglob("*.ipynb")
        if not p.name.startswith(".") and ".ipynb_checkpoints" not in p.parts
    )
    if not selectors:
        return all_nbs
    chosen: list[Path] = []
    for sel in selectors:
        matches = [p for p in all_nbs if sel in str(p.relative_to(NOTEBOOKS_DIR))]
        if not matches:
            print(f"  ! no notebook matches selector {sel!r}", file=sys.stderr)
        chosen.extend(m for m in matches if m not in chosen)
    return chosen


def _run_one(path: Path, timeout: int) -> tuple[bool, str]:
    """Execute a single notebook; return (ok, detail)."""
    nb = nbformat.read(path, as_version=4)
    client = NotebookClient(
        nb,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOKS_DIR)}},
        allow_errors=False,
    )
    try:
        client.execute()
        return True, "ok"
    except CellExecutionError as exc:
        return False, _format_cell_error(nb, exc)
    except Exception as exc:  # noqa: BLE001 - report any kernel/protocol failure
        return False, f"{type(exc).__name__}: {exc}"


def _format_cell_error(nb, exc: CellExecutionError) -> str:
    """Find the first errored cell and render a compact source+error snippet."""
    for idx, cell in enumerate(nb.cells):
        if cell.get("cell_type") != "code":
            continue
        for out in cell.get("outputs", []):
            if out.get("output_type") == "error":
                src = "".join(cell.get("source", "")).strip()
                head = "\n".join(src.splitlines()[:12])
                ename = out.get("ename", "Error")
                evalue = "".join(out.get("evalue", "")).splitlines()[:1]
                evalue_s = evalue[0] if evalue else ""
                return f"cell #{idx} failed: {ename}: {evalue_s}\n    --- source ---\n{head}"
    return f"CellExecutionError: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selectors", nargs="*", help="notebook number/name substrings (default: all)")
    parser.add_argument("--list", action="store_true", help="list notebooks that would run and exit")
    parser.add_argument("--timeout", type=int, default=DEFAULT_CELL_TIMEOUT, help="per-cell timeout (s)")
    args = parser.parse_args()

    _load_env()
    _ensure_kernel()

    notebooks = _discover(args.selectors)
    if args.list:
        for nb in notebooks:
            print(nb.relative_to(NOTEBOOKS_DIR))
        return 0

    if not os.environ.get("INTERACTLY_API_KEY"):
        print("ERROR: INTERACTLY_API_KEY not set — add it to the SDK's .env file.", file=sys.stderr)
        return 2

    print(f"Running {len(notebooks)} notebook(s) against {os.environ.get('INTERACTLY_BASE_URL', '<default>')}\n")
    results: list[tuple[str, bool, str, float]] = []
    for nb in notebooks:
        name = str(nb.relative_to(NOTEBOOKS_DIR))
        print(f"▶ {name} ...", flush=True)
        start = time.time()
        ok, detail = _run_one(nb, args.timeout)
        elapsed = time.time() - start
        results.append((name, ok, detail, elapsed))
        status = "PASS" if ok else "FAIL"
        print(f"  {status} ({elapsed:.1f}s)")
        if not ok:
            print("    " + detail.replace("\n", "\n    "))
        print()

    passed = sum(1 for _, ok, _, _ in results if ok)
    print("=" * 72)
    print(f"SUMMARY: {passed}/{len(results)} passed")
    for name, ok, _, elapsed in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  ({elapsed:.1f}s)")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
