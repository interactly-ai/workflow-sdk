"""
Source-parity harness: `interactly_configs` vs `agentic_workflow_framework/configs`.

The vendored config package is a deliberate mirror of the server's config package (plan principle #2:
"track upstream closely; duplication is fine"). Mirrors rot silently, so this compares the two trees
structurally — classes, fields, field types, and enum values — and reports every difference that is not
on the `KNOWN_DIVERGENCES` allow-list.

Why AST rather than importing both packages: importing upstream would drag in `beanie`, `bson`,
`pymongo` and `common.*`, which is exactly the dependency the SDK exists to avoid. Parsing keeps this
tool as self-contained as the package it guards.

**Dev-only.** This is the one piece of the repo that knows where `interactly-ai` lives. It must stay
under `tests/` and must never be imported by `interactly` or `interactly_configs`, or the
self-containment guarantee (plan Phase 7) breaks.

Usage::

    python tests/tools/config_parity.py                      # human-readable summary
    python tests/tools/config_parity.py -o docs/_sync/x.md   # write the markdown report
    INTERACTLY_AI_ROOT=/path/to/interactly-ai python tests/tools/config_parity.py

Upstream is located from `$INTERACTLY_AI_ROOT`, else by walking up from this file looking for a
sibling `interactly-ai/agentic_workflow_framework/configs`. When it cannot be found the tool reports
"unavailable" and exits 0 — so a checkout without the monorepo is not a failure.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# --------------------------------------------------------------------------------------------- #
# Known, intentional divergences                                                                  #
# --------------------------------------------------------------------------------------------- #

#: Type substitutions the self-containment rule forces, applied to BOTH sides before comparing so a
#: field upstream typed `Optional[PydanticObjectId]` matches the mirror's `Optional[str]`. Matched on
#: whole identifiers only. Every entry here is a divergence the mirror is REQUIRED to have — if a
#: substitution is not forced by self-containment or house style, it belongs in the report, not here.
TYPE_SUBSTITUTIONS: Dict[str, str] = {
    # Mongo identifiers: the mirror has no beanie/bson dependency.
    "PydanticObjectId": "str",
    "ObjectId": "str",
    # LangChain message types: the mirror carries events as plain dicts so `interactly_configs` has no
    # runtime dependency on `langchain_core` (stated in the mirror's events/event.py docstring).
    "AnyMessage": "Any",
    "AIMessage": "Any",
    "BaseMessage": "Any",
    # House style: the SDK uses typing-module generics throughout, matching the bulk of upstream and
    # keeping the `UP` ruleset disabled (see pyproject). `list[str]` and `List[str]` are the same type.
    "list": "List",
    "dict": "Dict",
    "tuple": "Tuple",
    "set": "Set",
    "type": "Type",
}

#: Module relocations the mirror makes deliberately, as {upstream module: mirror module}. Reported as
#: neither a gap nor a placement difference. `event.py` lives at the package root upstream but in an
#: `events/` subpackage here, which would otherwise report 44 identical placement differences.
KNOWN_MODULE_MAPPING: Dict[str, str] = {
    "event.py": "events/event.py",
    "acls.py": "acls.py",
}

#: Classes that legitimately exist on only one side, with the reason. Anything not listed is reported.
KNOWN_ONLY_UPSTREAM: Dict[str, str] = {
    # Server-runtime scaffolding, not wire contract: it holds a live WorkflowRuntime and pickled
    # checkpoint BYTES, neither of which a client can construct, send, or interpret. Vendoring it
    # would put an opaque `Optional[bytes]` blob in the public surface and imply the SDK can resume a
    # runtime it has no way to run. Deliberately excluded (plan revision 4, risk 2).
    "AgenticGraphHolder": "server-runtime scaffolding (live runtime + pickled checkpoint bytes)",
}

KNOWN_ONLY_MIRROR: Dict[str, str] = {
    "BaseAPIModel": "SDK-only base model",
    # Upstream's WorkflowTemplateConfig inherits `AccessControlLevelModel` from
    # `common/models/access_level_model.py`, a Beanie document base that cannot be vendored. This is
    # the pure-Pydantic stand-in that supplies the same two fields.
    "AccessControlLevelConfig": "pure-Pydantic stand-in for common.models.access_level_model",
    # Client-side lifecycle enum for an interactive run. Upstream's equivalent is `WorkflowStatus`
    # (workflow_run.py), which the mirror also has; this one adds the `is_terminal()` helper the SDK
    # uses to decide whether another turn may be sent.
    "WorkflowExecutionStatus": "SDK-only run lifecycle enum with is_terminal() helper",
    # Landing pad for a node type this package does not know yet, so a lagging client neither fails
    # the whole workflow nor silently drops the node's fields. Upstream needs no equivalent: the
    # server is by definition current with its own node types.
    "UnknownNodeConfig": "forward-compat fallback for unknown node types (extra='allow')",
}

#: Field-level divergences that are deliberate, as ``ClassName.field_name`` -> reason. Each one was
#: adjudicated rather than assumed; see the Phase 2 notes in the update plan.
KNOWN_FIELD_DIVERGENCES: Dict[str, str] = {
    # Typing this as upstream's `List[NodeConfig]` makes the SDK REJECT any workflow containing a node
    # type it does not yet know -- verified empirically. For a client that necessarily lags the
    # server, that is the normal case, and it is the exact failure this sync project exists to manage.
    #
    # CORRECTION (Phase 3): the original note here claimed "SerializeAsAny keeps subclass fields on
    # the way out, so round-tripping is lossless either way". That was wrong. SerializeAsAny governs
    # SERIALIZATION, so it preserves subclass fields only for an object that already IS the subclass.
    # Validating a plain dict against the annotation coerced it straight to BaseNodeConfig and
    # silently dropped every subclass field -- a `say_llm` node came back with no `type` and no
    # `prompt_config`. The annotation is still correct, but it is only safe because
    # `_upgrade_node_configs` now validates each entry through the union first, with
    # `UnknownNodeConfig` as the fallback.
    "WorkflowConfigFullyHydrated.node_configs": "forward-compat: unknown node types must not fail validation",
    # Same reasoning as StoredEvents: typing the payload as `Event` would reject event types newer
    # than this package.
    "SimulationEvent.payload": "forward-compat: unknown event types must not fail validation",
    # Upstream declares `thread_id: str` but defaults it to None, so the annotation and the default
    # disagree. The mirror's Optional[str] is the accurate description of the values that occur.
    "WorkflowShowStateEvent.thread_id": "upstream annotates str but defaults to None; Optional is accurate",
    # Supplied by AccessControlLevelConfig above, which stands in for upstream's Beanie base.
    "WorkflowTemplateConfig.access_level": "from the AccessControlLevelConfig stand-in",
    "WorkflowTemplateConfig.access_list": "from the AccessControlLevelConfig stand-in",
}

#: Enum capability data that upstream declares inside an enum body via `enum.nonmember(...)`.
#: `nonmember` is Python 3.11+, and this package supports 3.10, so the mirror hoists these to module
#: scope in `llm.py` with the same names and values. Present, just not attached to the enum class.
KNOWN_HOISTED_NONMEMBERS: Set[str] = {
    "OPENAIModel.MODELS_WITHOUT_LOW_REASONING_EFFORT",
    "OPENAIModel.LOW_REASONING_EFFORTS",
    "OPENAIModel.MINIMUM_PRO_REASONING_EFFORT",
    "ANTHROPICModel.ADAPTIVE_THINKING_MODELS",
    "ANTHROPICModel.ALWAYS_THINKING_MODELS",
    "ANTHROPICModel.DEFAULT_MAX_TOKENS",
    "ANTHROPICModel.DEFAULT_ADAPTIVE_THINKING_MAX_TOKENS",
    "GOOGLEModel.ALWAYS_THINKING_MODELS",
}

#: Class-name renames: mirror name -> upstream name. Reported as "reconciled" rather than as a gap.
KNOWN_RENAMES: Dict[str, str] = {}

#: Fields to ignore entirely, as `ClassName.field_name` or bare `field_name` for any class.
KNOWN_IGNORED_FIELDS: Set[str] = {
    # Pydantic plumbing, not part of the data contract.
    "model_config",
}

#: Attribute names inside Enum bodies that are capability data rather than members. Upstream wraps
#: these in `nonmember(...)`; they are compared separately from real enum values.
NONMEMBER_MARKER = "nonmember"


# --------------------------------------------------------------------------------------------- #
# Extraction                                                                                      #
# --------------------------------------------------------------------------------------------- #


@dataclass
class ClassInfo:
    """One class as the AST sees it."""

    name: str
    module: str
    bases: List[str] = field(default_factory=list)
    #: field name -> normalised annotation source
    fields: Dict[str, str] = field(default_factory=dict)
    #: field name -> normalised default ("<required>" when the field has none)
    defaults: Dict[str, str] = field(default_factory=dict)
    #: field name -> {constraint kwarg: value}, e.g. {"ge": "0", "le": "100"}
    constraints: Dict[str, Dict[str, str]] = field(default_factory=dict)
    #: validator signatures, e.g. "field_validator:content" / "model_validator:after"
    validators: Set[str] = field(default_factory=set)
    #: enum member name -> literal value (only for Enum subclasses)
    enum_members: Dict[str, object] = field(default_factory=dict)
    #: names assigned via `nonmember(...)` — capability data, not selectable members
    nonmembers: Set[str] = field(default_factory=set)

    @property
    def is_enum(self) -> bool:
        return any("Enum" in b for b in self.bases)


#: `Field()` keywords that constrain accepted VALUES. A mismatch here is a real contract difference —
#: the mirror would accept input the server rejects (or vice versa) without any type error to warn you.
#: Presentation-only keywords (`title`, `description`, `json_schema_extra`) are deliberately absent.
CONSTRAINT_KWARGS: Tuple[str, ...] = (
    "ge", "gt", "le", "lt",
    "min_length", "max_length",
    "min_items", "max_items",
    "pattern", "regex",
    "multiple_of",
)

#: Marker for a field declared with no default — i.e. required.
REQUIRED = "<required>"


def _normalise_type(annotation: str) -> str:
    """Collapse the differences that self-containment and house style force, so real ones stand out.

    Substitutes on whole identifiers via a word boundary — a naive `str.replace` would rewrite the
    `list` inside `Optional[MyListThing]`.
    """
    text = " ".join(annotation.split()).replace('"', "'")
    for upstream_name, mirror_name in TYPE_SUBSTITUTIONS.items():
        text = re.sub(rf"\b{re.escape(upstream_name)}\b", mirror_name, text)
    return text


def _extract_module(path: Path, module_name: str) -> Dict[str, ClassInfo]:
    """Parse one file into {class name: ClassInfo}."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:  # pragma: no cover - defensive
        print(f"  ! could not parse {path}: {exc}", file=sys.stderr)
        return {}

    out: Dict[str, ClassInfo] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        info = ClassInfo(
            name=node.name,
            module=module_name,
            bases=[ast.unparse(b) for b in node.bases],
            validators=_extract_validators(node),
        )
        for stmt in node.body:
            # Annotated field: `name: Type = Field(...)`
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                field_name = stmt.target.id
                info.fields[field_name] = _normalise_type(ast.unparse(stmt.annotation))
                info.defaults[field_name] = _extract_default(stmt.value)
                constraints = _extract_constraints(stmt.value)
                if constraints:
                    info.constraints[field_name] = constraints
            # Bare assignment: an enum member, or capability data, or `model_config`.
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if _is_nonmember_call(stmt.value):
                        info.nonmembers.add(target.id)
                        continue
                    try:
                        info.enum_members[target.id] = ast.literal_eval(stmt.value)
                    except (ValueError, TypeError):
                        # Not a literal (e.g. `model_config = ConfigDict(...)`) — not a data contract.
                        continue
        out[node.name] = info
    return out


def _is_field_call(value: Optional[ast.expr]) -> Optional[ast.Call]:
    """The `Field(...)` call in `x: int = Field(default=5)`, or None if the RHS is a plain value."""
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "Field":
            return value
    return None


def _canonical_default(rendered: str) -> str:
    """Collapse the ways of spelling the same default into one form.

    Pydantic v2 deep-copies a mutable default per instance, so `default=Thing()` and
    `default_factory=Thing` produce identical behaviour — likewise `default={}` and
    `default_factory=dict`. Reporting those as differences would bury the ones that actually change
    what the server receives, like `BEDROCKModel.GLM_4_7_FLASH` vs `None`.

    Note this deliberately does NOT run `_normalise_type`: that applies house-style casing
    (`dict` -> `Dict`), which is right for annotations and wrong for values — it would turn the
    callable `dict` into the non-callable `Dict`.
    """
    text = " ".join(rendered.split()).replace('"', "'")
    equivalents = {"factory:dict": "{}", "factory:list": "[]", "factory:set": "set()", "factory:tuple": "()"}
    if text in equivalents:
        return equivalents[text]
    # `factory:Thing` <-> `Thing()`
    if text.startswith("factory:"):
        return f"{text[len('factory:'):]}()"
    return text


def _extract_default(value: Optional[ast.expr]) -> str:
    """Normalised default for a field, or REQUIRED when it has none.

    `Field(None, ...)` and `Field(default=None, ...)` mean the same thing and must compare equal, so
    a leading positional argument is read as `default`. `Field(...)` (literal Ellipsis) means required.
    """
    if value is None:
        return REQUIRED

    call = _is_field_call(value)
    if call is None:
        return _canonical_default(ast.unparse(value))

    for keyword in call.keywords:
        if keyword.arg == "default":
            return _canonical_default(ast.unparse(keyword.value))
        if keyword.arg == "default_factory":
            return _canonical_default(f"factory:{ast.unparse(keyword.value)}")
    if call.args:
        rendered = ast.unparse(call.args[0])
        return REQUIRED if rendered == "..." else _canonical_default(rendered)
    return REQUIRED


def _extract_constraints(value: Optional[ast.expr]) -> Dict[str, str]:
    """Value constraints declared on a `Field(...)`, e.g. `{"ge": "0", "le": "100"}`."""
    call = _is_field_call(value)
    if call is None:
        return {}
    return {
        keyword.arg: ast.unparse(keyword.value)
        for keyword in call.keywords
        if keyword.arg in CONSTRAINT_KWARGS
    }


def _extract_validators(node: ast.ClassDef) -> Set[str]:
    """Validator decorators on a class, as comparable signatures.

    Compares *presence and target*, not body: a validator's logic is prose to an AST walk, but a
    missing one is a concrete gap — `SelfLoopConfig`'s cross-field check and `CommentRequest`'s
    blank-rejection are contract, and silently dropping either would let the mirror build a config
    the server refuses.
    """
    found: Set[str] = set()
    for stmt in node.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in stmt.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            func = call.func if call else decorator
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in ("field_validator", "model_validator", "validator", "root_validator"):
                continue
            targets = []
            if call:
                targets = [
                    ast.literal_eval(arg)
                    for arg in call.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                ]
                targets += [
                    ast.unparse(kw.value).strip("'\"")
                    for kw in call.keywords
                    if kw.arg == "mode"
                ]
            found.add(f"{name}:{','.join(sorted(targets)) or '*'}")
    return found


def _is_nonmember_call(value: ast.expr) -> bool:
    """True for `nonmember(...)` — upstream's marker for capability data inside an Enum body."""
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == NONMEMBER_MARKER
    )


def extract_tree(roots: List[Path]) -> Dict[str, ClassInfo]:
    """Parse every module under each root into one global {class name: ClassInfo} index.

    Indexed by class name rather than by module on purpose: the mirror legitimately places some
    classes in different modules than upstream (`BaseEntityConfig` lives in `base.py` vs `base_defs.py`),
    and that is a placement difference, not a missing class. Placement is reported separately.

    Takes a list of roots because both sides are assembled from several locations — see
    `UPSTREAM_SOURCES`.
    """
    index: Dict[str, ClassInfo] = {}
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            if "__pycache__" in path.parts:
                continue
            base = root.parent if root.is_file() else root
            module_name = str(path.relative_to(base))
            for name, info in _extract_module(path, module_name).items():
                # A duplicate class name across modules is itself worth knowing about; keep the first
                # and let the placement report surface the discrepancy.
                index.setdefault(name, info)
    return index


def _resolve_attribute(name: str, index: Dict[str, ClassInfo], attribute: str) -> Dict[str, object]:
    """Merge one per-field mapping (`fields` / `defaults` / `constraints`) across the inheritance chain.

    Without this, a field declared on a base upstream but re-declared per subclass (or vice versa)
    reads as a difference when the two are equivalent — the `tool_id` false positive that motivated
    making this inheritance-aware.
    """
    seen: Set[str] = set()

    def walk(class_name: str) -> Dict[str, object]:
        if class_name in seen or class_name not in index:
            return {}
        seen.add(class_name)
        info = index[class_name]
        merged: Dict[str, object] = {}
        for base in info.bases:
            merged.update(walk(base))
        merged.update(getattr(info, attribute))  # own declarations override inherited ones
        return merged

    return walk(name)


def resolve_fields(name: str, index: Dict[str, ClassInfo]) -> Dict[str, str]:
    """All fields visible on a class, including inherited ones. Subclass declarations win."""
    return {k: str(v) for k, v in _resolve_attribute(name, index, "fields").items()}


def resolve_defaults(name: str, index: Dict[str, ClassInfo]) -> Dict[str, str]:
    """All field defaults visible on a class, inherited ones included."""
    return {k: str(v) for k, v in _resolve_attribute(name, index, "defaults").items()}


def resolve_constraints(name: str, index: Dict[str, ClassInfo]) -> Dict[str, Dict[str, str]]:
    """All field value-constraints visible on a class, inherited ones included."""
    return {k: dict(v) for k, v in _resolve_attribute(name, index, "constraints").items()}  # type: ignore[arg-type]


def resolve_validators(name: str, index: Dict[str, ClassInfo]) -> Set[str]:
    """All validator signatures visible on a class, inherited ones included."""
    seen: Set[str] = set()

    def walk(class_name: str) -> Set[str]:
        if class_name in seen or class_name not in index:
            return set()
        seen.add(class_name)
        info = index[class_name]
        merged: Set[str] = set(info.validators)
        for base in info.bases:
            merged |= walk(base)
        return merged

    return walk(name)


# --------------------------------------------------------------------------------------------- #
# Comparison                                                                                      #
# --------------------------------------------------------------------------------------------- #


@dataclass
class ParityReport:
    missing_classes: List[Tuple[str, str]] = field(default_factory=list)      # (class, upstream module)
    extra_classes: List[Tuple[str, str]] = field(default_factory=list)        # (class, mirror module)
    missing_fields: List[Tuple[str, str, str]] = field(default_factory=list)  # (class, field, type)
    extra_fields: List[Tuple[str, str, str]] = field(default_factory=list)
    type_mismatches: List[Tuple[str, str, str, str]] = field(default_factory=list)  # cls, fld, up, mir
    default_mismatches: List[Tuple[str, str, str, str]] = field(default_factory=list)
    constraint_mismatches: List[Tuple[str, str, str, str]] = field(default_factory=list)
    missing_validators: List[Tuple[str, str]] = field(default_factory=list)  # (class, signature)
    missing_enum_values: List[Tuple[str, str]] = field(default_factory=list)  # (enum, value)
    extra_enum_values: List[Tuple[str, str]] = field(default_factory=list)
    missing_nonmembers: List[Tuple[str, str]] = field(default_factory=list)   # (enum, attr)
    placement: List[Tuple[str, str, str]] = field(default_factory=list)       # cls, up module, mirror

    @property
    def total(self) -> int:
        return (
            len(self.missing_classes)
            + len(self.extra_classes)
            + len(self.missing_fields)
            + len(self.extra_fields)
            + len(self.type_mismatches)
            + len(self.default_mismatches)
            + len(self.constraint_mismatches)
            + len(self.missing_validators)
            + len(self.missing_enum_values)
            + len(self.extra_enum_values)
            + len(self.missing_nonmembers)
        )

    @property
    def is_clean(self) -> bool:
        """Placement differences are informational and do not fail the report."""
        return self.total == 0


def _render_rules(rules: Dict[str, str]) -> str:
    """`{"ge": "0", "le": "100"}` -> `ge=0, le=100`; empty -> `(none)`."""
    return ", ".join(f"{k}={v}" for k, v in sorted(rules.items())) or "(none)"


def compare(upstream: Dict[str, ClassInfo], mirror: Dict[str, ClassInfo]) -> ParityReport:
    report = ParityReport()

    def ignored(class_name: str, field_name: str) -> bool:
        qualified = f"{class_name}.{field_name}"
        return (
            field_name in KNOWN_IGNORED_FIELDS
            or qualified in KNOWN_IGNORED_FIELDS
            or qualified in KNOWN_FIELD_DIVERGENCES
        )

    mirror_by_upstream_name = {KNOWN_RENAMES.get(n, n): n for n in mirror}

    for name, up_info in sorted(upstream.items()):
        mirror_name = mirror_by_upstream_name.get(name)
        if mirror_name is None:
            if name not in KNOWN_ONLY_UPSTREAM:
                report.missing_classes.append((name, up_info.module))
            continue

        mir_info = mirror[mirror_name]
        expected_module = KNOWN_MODULE_MAPPING.get(up_info.module, up_info.module)
        if expected_module != mir_info.module:
            report.placement.append((name, up_info.module, mir_info.module))

        up_fields = resolve_fields(name, upstream)
        mir_fields = resolve_fields(mirror_name, mirror)

        for fname, ftype in sorted(up_fields.items()):
            if ignored(name, fname):
                continue
            if fname not in mir_fields:
                report.missing_fields.append((name, fname, ftype))
            elif mir_fields[fname] != ftype:
                report.type_mismatches.append((name, fname, ftype, mir_fields[fname]))

        for fname, ftype in sorted(mir_fields.items()):
            if not ignored(name, fname) and fname not in up_fields:
                report.extra_fields.append((name, fname, ftype))

        # Defaults, value constraints and validators. A field can match on name AND type and still
        # behave differently — a default of None vs 3, a missing `le=100`, or an absent cross-field
        # validator all let the mirror build a config the server rejects, with no type error to warn you.
        up_defaults, mir_defaults = resolve_defaults(name, upstream), resolve_defaults(mirror_name, mirror)
        for fname, up_default in sorted(up_defaults.items()):
            if ignored(name, fname) or fname not in mir_defaults:
                continue  # absent fields are already reported above
            if mir_defaults[fname] != up_default:
                report.default_mismatches.append((name, fname, up_default, mir_defaults[fname]))

        up_constraints = resolve_constraints(name, upstream)
        mir_constraints = resolve_constraints(mirror_name, mirror)
        for fname, up_rules in sorted(up_constraints.items()):
            if ignored(name, fname) or fname not in mir_fields:
                continue
            mir_rules = mir_constraints.get(fname, {})
            if mir_rules != up_rules:
                report.constraint_mismatches.append(
                    (name, fname, _render_rules(up_rules), _render_rules(mir_rules))
                )

        for signature in sorted(resolve_validators(name, upstream) - resolve_validators(mirror_name, mirror)):
            report.missing_validators.append((name, signature))

        if up_info.is_enum or mir_info.is_enum:
            up_values = {str(v) for v in up_info.enum_members.values()}
            mir_values = {str(v) for v in mir_info.enum_members.values()}
            for value in sorted(up_values - mir_values):
                report.missing_enum_values.append((name, value))
            for value in sorted(mir_values - up_values):
                report.extra_enum_values.append((name, value))
            for attr in sorted(up_info.nonmembers - mir_info.nonmembers):
                if f"{name}.{attr}" in KNOWN_HOISTED_NONMEMBERS:
                    continue  # present at module scope in the mirror; see KNOWN_HOISTED_NONMEMBERS
                report.missing_nonmembers.append((name, attr))

    for name, mir_info in sorted(mirror.items()):
        upstream_name = KNOWN_RENAMES.get(name, name)
        if upstream_name not in upstream and name not in KNOWN_ONLY_MIRROR:
            report.extra_classes.append((name, mir_info.module))

    return report


# --------------------------------------------------------------------------------------------- #
# Locating upstream                                                                               #
# --------------------------------------------------------------------------------------------- #

#: The mirror vendors from THREE upstream locations, not one. Comparing only against
#: `agentic_workflow_framework/configs` silently skips the event models and the ACL enums — which is
#: how a manual audit missed the event drift entirely. Each entry is a path relative to the
#: `interactly-ai` root; directories are walked, single files are parsed on their own.
UPSTREAM_SOURCES: Tuple[str, ...] = (
    "agentic_workflow_framework/configs",           # -> interactly_configs/*
    "agentic_workflow_framework/runtime/event.py",  # -> interactly_configs/events/event.py
    "common/models/acls.py",                        # -> interactly_configs/acls.py
)


def find_interactly_ai_root() -> Optional[Path]:
    """Locate the `interactly-ai` checkout, or None when the monorepo is not present."""
    env_root = os.environ.get("INTERACTLY_AI_ROOT")
    if env_root:
        candidate = Path(env_root)
        return candidate if candidate.is_dir() else None

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "interactly-ai"
        if (candidate / "agentic_workflow_framework").is_dir():
            return candidate
    return None


def upstream_paths(root: Path) -> List[Path]:
    """The upstream files/directories the mirror is built from, skipping any that are absent."""
    return [p for p in (root / rel for rel in UPSTREAM_SOURCES) if p.exists()]


def find_mirror_configs() -> Path:
    """`configs/src/interactly_configs`, relative to this file."""
    return Path(__file__).resolve().parents[2] / "configs" / "src" / "interactly_configs"


# --------------------------------------------------------------------------------------------- #
# Reporting                                                                                       #
# --------------------------------------------------------------------------------------------- #


def render_markdown(report: ParityReport, upstream_roots: List[Path], mirror_root: Path) -> str:
    sources = ", ".join(f"`{p.name}`" for p in upstream_roots)
    lines: List[str] = [
        "# Config parity report — `interactly_configs` vs upstream",
        "",
        f"- Upstream sources ({len(upstream_roots)}): {sources}",
        f"- Mirror:   `{mirror_root}`",
        f"- **Total differences: {report.total}** "
        f"({len(report.placement)} placement differences, reported but not counted)",
        "",
    ]

    def section(title: str, rows: List[str], headers: str, sep: str) -> None:
        if not rows:
            return
        lines.extend([f"## {title} ({len(rows)})", "", headers, sep])
        lines.extend(rows)
        lines.append("")

    section(
        "Classes missing from the mirror",
        [f"| `{c}` | `{m}` |" for c, m in report.missing_classes],
        "| Class | Upstream module |",
        "|---|---|",
    )
    section(
        "Classes only in the mirror",
        [f"| `{c}` | `{m}` |" for c, m in report.extra_classes],
        "| Class | Mirror module |",
        "|---|---|",
    )
    section(
        "Fields missing from the mirror",
        [f"| `{c}` | `{f}` | `{t}` |" for c, f, t in report.missing_fields],
        "| Class | Field | Upstream type |",
        "|---|---|---|",
    )
    section(
        "Fields only in the mirror",
        [f"| `{c}` | `{f}` | `{t}` |" for c, f, t in report.extra_fields],
        "| Class | Field | Mirror type |",
        "|---|---|---|",
    )
    section(
        "Field type mismatches",
        [f"| `{c}` | `{f}` | `{u}` | `{m}` |" for c, f, u, m in report.type_mismatches],
        "| Class | Field | Upstream | Mirror |",
        "|---|---|---|---|",
    )
    section(
        "Default value mismatches",
        [f"| `{c}` | `{f}` | `{u}` | `{m}` |" for c, f, u, m in report.default_mismatches],
        "| Class | Field | Upstream default | Mirror default |",
        "|---|---|---|---|",
    )
    section(
        "Value constraint mismatches",
        [f"| `{c}` | `{f}` | `{u}` | `{m}` |" for c, f, u, m in report.constraint_mismatches],
        "| Class | Field | Upstream | Mirror |",
        "|---|---|---|---|",
    )
    section(
        "Validators missing from the mirror",
        [f"| `{c}` | `{s}` |" for c, s in report.missing_validators],
        "| Class | Validator |",
        "|---|---|",
    )
    section(
        "Enum values missing from the mirror",
        [f"| `{e}` | `{v}` |" for e, v in report.missing_enum_values],
        "| Enum | Value |",
        "|---|---|",
    )
    section(
        "Enum values only in the mirror (server would reject these)",
        [f"| `{e}` | `{v}` |" for e, v in report.extra_enum_values],
        "| Enum | Value |",
        "|---|---|",
    )
    section(
        "Enum capability data (`nonmember`) missing from the mirror",
        [f"| `{e}` | `{a}` |" for e, a in report.missing_nonmembers],
        "| Enum | Attribute |",
        "|---|---|",
    )
    section(
        "Module placement differences (informational)",
        [f"| `{c}` | `{u}` | `{m}` |" for c, u, m in report.placement],
        "| Class | Upstream module | Mirror module |",
        "|---|---|---|",
    )

    if report.is_clean:
        lines.extend(["✅ **No structural differences.** The mirror is in parity with upstream.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, help="Write the markdown report to this path")
    args = parser.parse_args()

    ai_root = find_interactly_ai_root()
    if ai_root is None:
        print("interactly-ai not found — parity check skipped (set INTERACTLY_AI_ROOT to enable).")
        return 0

    upstream_roots = upstream_paths(ai_root)
    mirror_root = find_mirror_configs()
    report = compare(extract_tree(upstream_roots), extract_tree([mirror_root]))
    markdown = render_markdown(report, upstream_roots, mirror_root)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"Report written to {args.output}")

    print(
        f"classes missing={len(report.missing_classes)} extra={len(report.extra_classes)} | "
        f"fields missing={len(report.missing_fields)} extra={len(report.extra_fields)} "
        f"type-mismatch={len(report.type_mismatches)} | "
        f"default-mismatch={len(report.default_mismatches)} "
        f"constraint-mismatch={len(report.constraint_mismatches)} "
        f"validators-missing={len(report.missing_validators)} | "
        f"enum missing={len(report.missing_enum_values)} extra={len(report.extra_enum_values)} "
        f"nonmember-missing={len(report.missing_nonmembers)} | "
        f"placement={len(report.placement)}"
    )
    print(f"TOTAL DIFFERENCES: {report.total}")
    return 0 if report.is_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
