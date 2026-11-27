"""
Wire-value harness: values the SDK restates by hand from the workflow service.

`config_parity` compares the vendored `interactly_configs` package with upstream. Two kinds of hand-written value in
`src/interactly/` sit outside it, and both drifted unseen:

* **Enum twins.** `interactly.types` keeps its own copies of enums the server owns: run status, workflow command,
  webhook actions, schedule status, re-run modes. A value the server gained and the twin lacks fails to parse
  wherever a field is typed with the enum (`Schedule.status` raised on a schedule `in_progress`), and cannot be
  named where it is not. A value only the twin has is one no server sends.
* **WebSocket close codes.** The run socket closes with one code per refusal. The SDK maps the codes it knows to a
  typed `StreamError`; any other arrives as a bare `StreamError` carrying only the close reason.

Both sides are read with `ast`, so nothing from the monorepo is imported.

Usage::

    python tests/tools/wire_values.py
    python tests/tools/wire_values.py -o docs/_sync/wire-values.md

Exits 0 when the `interactly-ai` checkout cannot be found.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_parity import find_interactly_ai_root  # noqa: E402

# --------------------------------------------------------------------------------------------- #
# What to compare                                                                                 #
# --------------------------------------------------------------------------------------------- #

#: Each SDK enum that restates an upstream one, as "file relative to src/interactly:Class" -> (upstream file
#: relative to the `interactly-ai` root, upstream class).
ENUM_TWINS: Dict[str, Tuple[str, str]] = {
    "types/shared.py:RunStatus": ("agentic_workflow_framework/configs/workflow_run.py", "WorkflowStatus"),
    "types/shared.py:WorkflowCommand": ("agentic_workflow_framework/configs/workflow_run.py", "WorkflowCommand"),
    "types/simulations/simulation.py:SimulationStatus": (
        "agentic_workflow_framework/configs/simulation.py",
        "SimulationStatus",
    ),
    "types/schedules/schedule.py:ScheduleStatus": (
        "workflow_service/src/models/workflow_scheduled_runs.py",
        "WorkflowScheduleStatus",
    ),
    "types/webhooks/webhook.py:WebhookAction": (
        "workflow_service/src/models/workflow_webhooks.py",
        "WorkflowWebhookAction",
    ),
    "types/webhooks/webhook.py:WebhookEventStatus": (
        "workflow_service/src/models/workflow_webhooks.py",
        "WorkflowWebhookEventStatus",
    ),
    "types/reruns/rerun.py:RerunMode": ("workflow_service/src/workflow_runs/rerun_compatibility.py", "RerunMode"),
    "types/reruns/rerun.py:NodeMatchKind": (
        "workflow_service/src/workflow_runs/rerun_compatibility.py",
        "NodeMatchKind",
    ),
    "types/reruns/rerun.py:HistoryMode": ("workflow_service/src/services/branch_service.py", "HistoryMode"),
}

#: SDK enums that share a name with an upstream enum but mean something else, as name -> reason. Never compared.
KNOWN_UNRELATED_NAMESAKES: Dict[str, str] = {
    "WorkflowStatus": "the SDK's is a workflow's lifecycle (active, draft, archived); upstream's is a run's status, "
    "which the SDK calls RunStatus",
}

#: Values one side has on purpose, as "SdkEnum.value" -> reason.
KNOWN_TWIN_VALUE_DIVERGENCES: Dict[str, str] = {}

#: Upstream locations searched for enums that share a name with an SDK enum (the namesake check), relative to the
#: `interactly-ai` root.
NAMESAKE_SOURCES: Tuple[str, ...] = (
    "agentic_workflow_framework/configs",
    "workflow_service/src",
    "workflow_service/utils",
    "common/models",
)

#: The files the run socket's close codes come from, relative to the `interactly-ai` root: the handler, and the
#: access checks it runs before accepting a socket.
RUN_SOCKET_SOURCES: Tuple[str, ...] = (
    "workflow_service/app/routers/workflow_runs.py",
    "workflow_service/src/access/viewer_gate.py",
    "common/models/request_models.py",
    "common/models/read_only_access.py",
)

#: Close codes the SDK leaves as a plain `StreamError` on purpose, as code -> reason.
KNOWN_UNTYPED_CLOSE_CODES: Dict[int, str] = {
    1000: "the normal end of a run, not a refusal",
}

#: Where the SDK maps close codes to exceptions, relative to src/interactly, and the mapping's name.
SDK_CLOSE_CODE_MAP: Tuple[str, str] = ("_streaming.py", "_CLOSE_CODE_ERRORS")


# --------------------------------------------------------------------------------------------- #
# Data                                                                                            #
# --------------------------------------------------------------------------------------------- #


@dataclass
class WireReport:
    #: (SDK enum, value) the upstream twin has and the SDK's lacks
    twin_values_missing: List[Tuple[str, str]] = field(default_factory=list)
    #: (SDK enum, value) only the SDK's twin has
    twin_values_extra: List[Tuple[str, str]] = field(default_factory=list)
    #: SDK enums named like an upstream enum that are neither mapped as twins nor listed as unrelated
    unmapped_namesakes: List[str] = field(default_factory=list)
    #: twins whose SDK or upstream class could not be found, as (twin key, what is missing)
    broken_twins: List[Tuple[str, str]] = field(default_factory=list)
    #: close codes the server uses that the SDK has no typed exception for
    close_codes_untyped: List[int] = field(default_factory=list)
    #: close codes the SDK maps that no upstream source uses
    close_codes_stale: List[int] = field(default_factory=list)
    #: how many twins and codes were compared, so a run that compared nothing is visible
    twins_compared: int = 0
    upstream_close_codes: Set[int] = field(default_factory=set)
    allowances_used: Set[str] = field(default_factory=set)

    def counted_categories(self) -> List[Tuple[str, Sequence[object]]]:
        return [
            ("enum values the SDK twin lacks", self.twin_values_missing),
            ("enum values only the SDK twin has", self.twin_values_extra),
            ("unmapped enum namesakes", self.unmapped_namesakes),
            ("twins that could not be read", self.broken_twins),
            ("close codes with no typed exception", self.close_codes_untyped),
            ("close codes the SDK maps but the server never sends", self.close_codes_stale),
        ]

    @property
    def total(self) -> int:
        return sum(len(items) for _, items in self.counted_categories())


# --------------------------------------------------------------------------------------------- #
# Extraction and comparison                                                                       #
# --------------------------------------------------------------------------------------------- #


def enum_values(path: Path, class_name: str) -> Optional[Set[str]]:
    """The string values of an enum's members, read from source; None when the class is not there."""
    tree = _parse(path)
    if tree is None:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            values: Set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant):
                    values.add(str(stmt.value.value))
            return values
    return None


def enums_defined_in(paths: Iterable[Path]) -> Dict[str, List[Path]]:
    """Every `class X(..., Enum)` in the given files, as name -> files."""
    found: Dict[str, List[Path]] = {}
    for path in paths:
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any("Enum" in ast.unparse(b) for b in node.bases):
                found.setdefault(node.name, []).append(path)
    return found


def upstream_close_codes(ai_root: Path, sources: Optional[Sequence[str]] = None) -> Set[int]:
    """Every close code the run socket's sources (`RUN_SOCKET_SOURCES` by default) can send.

    Read from three spellings: a literal or a module constant passed as `code=` (to `close` or a
    `WebSocketException`), a module-level `*_CLOSE_CODE` constant (the take-back codes travel through a helper's
    parameter), and Starlette's `status.WS_NNNN_*` names.
    """
    codes: Set[int] = set()
    for relative in RUN_SOCKET_SOURCES if sources is None else sources:
        tree = _parse(ai_root / relative)
        if tree is None:
            continue
        constants = {
            target.id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        codes |= {value for name, value in constants.items() if name.endswith("_CLOSE_CODE")}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg != "code":
                        continue
                    if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, int):
                        codes.add(keyword.value.value)
                    elif isinstance(keyword.value, ast.Name) and keyword.value.id in constants:
                        codes.add(constants[keyword.value.id])
            elif isinstance(node, ast.Attribute):
                match = re.match(r"WS_(\d{4})_", node.attr)
                if match:
                    codes.add(int(match.group(1)))
    return codes


def sdk_typed_close_codes(sdk_package: Path) -> Optional[Set[int]]:
    """The keys of the SDK's close-code-to-exception map; None when the map cannot be found."""
    relative, name = SDK_CLOSE_CODE_MAP
    tree = _parse(sdk_package / relative)
    if tree is None:
        return None
    for node in tree.body:
        target = (
            node.target
            if isinstance(node, ast.AnnAssign)
            else node.targets[0]
            if isinstance(node, ast.Assign)
            else None
        )
        if isinstance(target, ast.Name) and target.id == name and isinstance(node.value, ast.Dict):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, int)}
    return None


def build_report(ai_root: Path, sdk_package: Optional[Path] = None) -> WireReport:
    sdk_package = sdk_package or find_sdk_package()
    report = WireReport()

    for key, (upstream_file, upstream_class) in sorted(ENUM_TWINS.items()):
        sdk_file, sdk_class = key.split(":")
        sdk_values = enum_values(sdk_package / sdk_file, sdk_class)
        upstream = enum_values(ai_root / upstream_file, upstream_class)
        if sdk_values is None or upstream is None:
            missing = (
                f"src/interactly/{sdk_file}:{sdk_class}" if sdk_values is None else f"{upstream_file}:{upstream_class}"
            )
            report.broken_twins.append((key, missing))
            continue
        report.twins_compared += 1
        for value in sorted(upstream - sdk_values):
            if _allowed(report, f"{sdk_class}.{value}"):
                continue
            report.twin_values_missing.append((sdk_class, value))
        for value in sorted(sdk_values - upstream):
            if _allowed(report, f"{sdk_class}.{value}"):
                continue
            report.twin_values_extra.append((sdk_class, value))

    sdk_enums = enums_defined_in(sorted(sdk_package.rglob("*.py")))
    upstream_enums = enums_defined_in(path for source in NAMESAKE_SOURCES for path in _python_files(ai_root / source))
    mapped = {key.split(":")[1] for key in ENUM_TWINS}
    for name in sorted(set(sdk_enums) & set(upstream_enums)):
        if name in mapped:
            continue
        if name in KNOWN_UNRELATED_NAMESAKES:
            report.allowances_used.add(f"KNOWN_UNRELATED_NAMESAKES:{name}")
            continue
        report.unmapped_namesakes.append(name)

    report.upstream_close_codes = upstream_close_codes(ai_root)
    typed = sdk_typed_close_codes(sdk_package) or set()
    for code in sorted(report.upstream_close_codes - typed):
        if code in KNOWN_UNTYPED_CLOSE_CODES:
            report.allowances_used.add(f"KNOWN_UNTYPED_CLOSE_CODES:{code}")
            continue
        report.close_codes_untyped.append(code)
    report.close_codes_stale = sorted(typed - report.upstream_close_codes)
    return report


def find_sdk_package() -> Path:
    """`src/interactly`, relative to this file."""
    return Path(__file__).resolve().parents[2] / "src" / "interactly"


# --------------------------------------------------------------------------------------------- #
# Reporting                                                                                       #
# --------------------------------------------------------------------------------------------- #


def render_markdown(report: WireReport) -> str:
    lines: List[str] = [
        "# Wire-value report — the SDK's hand-written enums and close codes vs. upstream",
        "",
        f"- Enum twins compared: **{report.twins_compared}** of {len(ENUM_TWINS)}",
        f"- Close codes the run socket can send: {', '.join(str(c) for c in sorted(report.upstream_close_codes))}",
        f"- **Total findings: {report.total}**",
        "",
    ]
    for label, items in report.counted_categories():
        if not items:
            continue
        lines.extend([f"## {label[0].upper()}{label[1:]} ({len(items)})", ""])
        lines.extend(f"- `{_render(item)}`" for item in items)
        lines.append("")
    if report.total == 0:
        lines.extend(["✅ **Every twin matches upstream, and every close code has a typed exception.**", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, help="Write the markdown report to this path")
    args = parser.parse_args()

    ai_root = find_interactly_ai_root()
    if ai_root is None:
        print("interactly-ai not found — wire-value check skipped (set INTERACTLY_AI_ROOT to enable).")
        return 0

    report = build_report(ai_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_markdown(report), encoding="utf-8")
        print(f"Report written to {args.output}")
    print(" | ".join(f"{label}={len(items)}" for label, items in report.counted_categories()))
    print(f"TOTAL FINDINGS: {report.total}")
    return 0 if report.total == 0 else 1


# --------------------------------------------------------------------------------------------- #
# Private helpers                                                                                 #
# --------------------------------------------------------------------------------------------- #


def _allowed(report: WireReport, key: str) -> bool:
    if key in KNOWN_TWIN_VALUE_DIVERGENCES:
        report.allowances_used.add(f"KNOWN_TWIN_VALUE_DIVERGENCES:{key}")
        return True
    return False


def _render(item: object) -> str:
    return ".".join(str(part) for part in item) if isinstance(item, tuple) else str(item)


def _parse(path: Path) -> Optional[ast.Module]:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None


def _python_files(root: Path) -> Iterable[Path]:
    skipped = {"tests", "venv", ".venv", "__pycache__", "notebooks", "node_modules"}
    for path in sorted(root.rglob("*.py")):
        if not skipped.intersection(path.relative_to(root).parts):
            yield path


if __name__ == "__main__":
    raise SystemExit(main())
