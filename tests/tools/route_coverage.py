"""
Route-coverage harness: the routes the workflow service serves vs. the routes the SDK calls.

`config_parity` and `schema_sync` cover the config models. Nothing covered the client's own surface: which routes
`src/interactly/resources/**` calls, and with which query parameters. Every gap there used to be found by hand —
routes added upstream that no SDK method reaches, a list filter the server learned that no SDK method can send,
and the worse case, an SDK call to a route the server no longer serves.

Both sides are read with `ast`, as `config_parity` reads them, so nothing from the monorepo is imported:

* **Upstream:** every `APIRouter(prefix=...)` in `workflow_service/app/routers/` and every route declared on it.
  A router or route declared `include_in_schema=False` is hidden, and `/internal/` routes are service-to-service;
  neither is part of the public API. Query parameters are read the way FastAPI reads them: plain-typed
  parameters, `Query()` parameters, the fields of a model declared `= Query()` or `= Depends()`, and the
  `Query()` parameters of a plain class declared `= Depends()` (`PaginationRequest`).
* **SDK:** every `self._client.<verb>(path, params=...)` call in the resources. The path is rendered through
  module constants, path helpers and local variables; the query keys are read off the `params` dict however it
  is built (a literal, a local dict filled key by key, a helper function, a `**kwargs` helper).

What it reports:

* public routes the SDK does not call, and query fields it cannot send on routes it does call;
* SDK calls to routes upstream does not declare at all (a certain 404), and query keys upstream does not read;
* SDK calls whose path or params this harness could not render. Those count: a call the harness cannot read
  would otherwise pass as coverage.

Known limits: a query parameter declared by a dependency *function* (`Depends(some_function)`) or read straight
off `request.query_params` is not seen. Request bodies are not compared.

Usage::

    python tests/tools/route_coverage.py
    python tests/tools/route_coverage.py -o docs/_sync/route-coverage.md

Exits 0 when the `interactly-ai` checkout cannot be found, so a checkout without the monorepo is not a failure.
"""

from __future__ import annotations

import argparse
import ast
import itertools
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

# `config_parity` owns the one piece of knowledge about where the monorepo lives.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_parity import find_interactly_ai_root  # noqa: E402

# --------------------------------------------------------------------------------------------- #
# What to compare                                                                                 #
# --------------------------------------------------------------------------------------------- #

#: Where the routers live, relative to the `interactly-ai` root.
ROUTERS_DIR = "workflow_service/app/routers"

#: Where a class named in a route signature (a query model, a dependency class) is looked up, relative to the
#: `interactly-ai` root.
CLASS_SOURCES: Tuple[str, ...] = ("workflow_service", "common", "agentic_workflow_framework")

#: The SDK's resources, relative to the SDK root.
SDK_RESOURCES = "src/interactly/resources"

#: Public routes the SDK deliberately does not call, as (method, path) -> reason. Paths use `{}` for every
#: path parameter. An entry that stops suppressing anything is reported by the staleness test.
KNOWN_UNCOVERED_ROUTES: Dict[Tuple[str, str], str] = {
    **{
        route: "secure notifications are raised and approved by the platform's own flows, behind a per-team flag; "
        "not a client API"
        for route in (
            ("GET", "/v1/secure-notifications"),
            ("POST", "/v1/secure-notifications"),
            ("POST", "/v1/secure-notifications/approvals"),
            ("GET", "/v1/secure-notifications/{}"),
            ("POST", "/v1/secure-notifications/{}/approve"),
            ("POST", "/v1/secure-notifications/{}/decline"),
        )
    },
    **{
        route: "super-admin only: a deployment operator's upgrade checklist, not a customer API"
        for route in (
            ("GET", "/v1/upgrade-checklist"),
            ("POST", "/v1/upgrade-checklist/reset"),
            ("POST", "/v1/upgrade-checklist/saved-keys/test"),
            ("PUT", "/v1/upgrade-checklist/steps/{}"),
        )
    },
}

#: Query fields the SDK deliberately does not send, as (method, path, name) -> reason.
KNOWN_UNCOVERED_QUERY_FIELDS: Dict[Tuple[str, str, str], str] = {
    ("GET", "/v1/workflow-runs", "copilot_runs_only"): "super-admin only: lists the copilot's own conversations, "
    "which the server refuses to every other role",
}

#: Query keys the SDK sends that upstream's route signatures do not declare, as (method, path, name) -> reason.
#: Only for a key the server is known to read some other way (a dependency function, `request.query_params`).
KNOWN_SDK_ONLY_QUERY_FIELDS: Dict[Tuple[str, str, str], str] = {}

#: SDK calls this harness cannot render, as "file:function" -> reason. Prefer making the call renderable.
KNOWN_UNRENDERABLE_CALLS: Dict[str, str] = {}

#: HTTP verbs a route decorator or an SDK client call can name.
VERBS: Tuple[str, ...] = ("get", "post", "put", "patch", "delete")

#: Parameter markers that put a value somewhere other than the query string.
_NON_QUERY_MARKERS = {"Body", "Header", "Path", "Cookie", "File", "Form", "Security"}
#: Annotations FastAPI fills from the request itself.
_FRAMEWORK_TYPES = {"Request", "Response", "BackgroundTasks", "WebSocket", "HTTPConnection"}
#: Annotations FastAPI reads as a scalar query value when no marker says otherwise.
_SCALAR_TYPES = {
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "PydanticObjectId",
    "ObjectId",
    "datetime",
    "date",
    "time",
    "UUID",
    "Decimal",
}
_PATH_PARAMETER = re.compile(r"\{(\w+)(?::[^}]*)?\}")


# --------------------------------------------------------------------------------------------- #
# Data                                                                                            #
# --------------------------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Route:
    """One upstream route."""

    method: str  # GET, POST, PUT, PATCH, DELETE or WS
    path: str  # normalised: `{}` for every path parameter, no trailing slash
    router: str  # the router module's file stem
    query: FrozenSet[str]
    public: bool  # False for hidden routers or routes, `/internal/` paths and anything outside `/v1/`

    @property
    def key(self) -> Tuple[str, str]:
        return (self.method, self.path)


@dataclass
class SdkCall:
    """One request the SDK sends."""

    method: str
    path: str
    location: str  # resources-relative file:function
    query: Set[str] = field(default_factory=set)
    #: resources-relative file:line of the call. A call whose path renders more than one way (a helper with an
    #: `if`) yields one SdkCall per rendering, all sharing this id.
    call_id: str = ""

    @property
    def key(self) -> Tuple[str, str]:
        return (self.method, self.path)


@dataclass
class RouteReport:
    upstream_routes: List[Route] = field(default_factory=list)
    sdk_calls: List[SdkCall] = field(default_factory=list)
    #: (location, what could not be rendered)
    unrenderable_calls: List[Tuple[str, str]] = field(default_factory=list)
    missing_routes: List[Route] = field(default_factory=list)
    #: (method, path, query name)
    missing_query_fields: List[Tuple[str, str, str]] = field(default_factory=list)
    #: (method, path, locations)
    sdk_routes_not_upstream: List[Tuple[str, str, str]] = field(default_factory=list)
    #: (method, path, query name)
    sdk_query_not_upstream: List[Tuple[str, str, str]] = field(default_factory=list)
    #: "LIST_NAME:entry" for every allow-list entry that suppressed something
    allowances_used: Set[str] = field(default_factory=set)

    def counted_categories(self) -> List[Tuple[str, Sequence[object]]]:
        return [
            ("routes the SDK does not call", self.missing_routes),
            ("query fields the SDK cannot send", self.missing_query_fields),
            ("SDK calls to routes upstream does not declare", self.sdk_routes_not_upstream),
            ("SDK query keys upstream does not read", self.sdk_query_not_upstream),
            ("SDK calls the harness could not render", self.unrenderable_calls),
        ]

    @property
    def total(self) -> int:
        return sum(len(items) for _, items in self.counted_categories())


def normalise_path(path: str) -> str:
    """`/v1/workflows/{workflow_id}/` -> `/v1/workflows/{}`, so the two sides can be compared."""
    return re.sub(r"\{[^}]*\}", "{}", path).rstrip("/") or "/"


# --------------------------------------------------------------------------------------------- #
# Upstream: routes and the query fields each one reads                                            #
# --------------------------------------------------------------------------------------------- #


def extract_routes(ai_root: Path, routers_dir: Optional[Path] = None) -> List[Route]:
    """Every route declared in the routers, public or not, with the query fields it reads."""
    index = ClassIndex(ai_root)
    routes: List[Route] = []
    for path in sorted((routers_dir or ai_root / ROUTERS_DIR).glob("*.py")):
        tree = _parse(path)
        if tree is None:
            continue
        module = _module_name(path, ai_root)
        routers = _routers_in(tree)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                route = _route_from_decorator(decorator, routers)
                if route is None:
                    continue
                method, full_path, hidden = route
                path_parameters = set(_PATH_PARAMETER.findall(full_path))
                query = (
                    frozenset(_query_fields(node, path_parameters, module, index)) if method != "WS" else frozenset()
                )
                public = not hidden and full_path.startswith("/v1/")
                routes.append(Route(method, normalise_path(full_path), path.stem, query, public))
    return routes


class ClassIndex:
    """Finds the class a route signature names, the way the router's own imports would."""

    def __init__(self, ai_root: Path):
        self._root = ai_root
        self._modules: Dict[str, Optional[ast.Module]] = {}
        self._by_name: Optional[Dict[str, List[Tuple[str, ast.ClassDef]]]] = None

    def resolve(self, name: str, module: str, _depth: int = 0) -> Optional[Tuple[str, ast.ClassDef]]:
        """The class `name` means inside `module`: defined there, imported into it, or unique by name."""
        if _depth > 4:
            return None
        tree = self._module(module)
        if tree is not None:
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == name:
                    return module, node
            for node in tree.body:
                if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    for alias in node.names:
                        if (alias.asname or alias.name) == name:
                            found = self.resolve(alias.name, node.module, _depth + 1)
                            if found is not None:
                                return found
        candidates = self._all_classes().get(name, [])
        return candidates[0] if len(candidates) == 1 else None

    def is_model(self, module: str, node: ast.ClassDef, _depth: int = 0) -> bool:
        """A pydantic model or Beanie document, judged by its bases."""
        return self._inherits(module, node, ("BaseModel", "Document", "BaseDocument"), _depth)

    def is_enum(self, module: str, node: ast.ClassDef, _depth: int = 0) -> bool:
        return self._inherits(module, node, ("Enum",), _depth)

    def query_fields_of(self, module: str, node: ast.ClassDef) -> Set[str]:
        """What a class contributes to the query string when a route declares it `= Query()` or `= Depends()`."""
        if self.is_model(module, node):
            return self._model_fields(module, node)
        return _init_query_parameters(node)

    def _model_fields(self, module: str, node: ast.ClassDef, _depth: int = 0) -> Set[str]:
        names: Set[str] = set()
        if _depth > 6:
            return names
        for base in node.bases:
            base_name = _plain_name(base)
            if base_name in (None, "BaseModel", "Document", "BaseDocument", "Generic"):
                continue
            found = self.resolve(base_name, module)
            if found is not None:
                names |= self._model_fields(found[0], found[1], _depth + 1)
        for stmt in node.body:
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
                continue
            name = stmt.target.id
            if name.startswith("_") or name == "model_config" or "ClassVar" in ast.unparse(stmt.annotation):
                continue
            names.add(_alias_of(stmt.value) or name)
        return names

    def _inherits(self, module: str, node: ast.ClassDef, roots: Tuple[str, ...], depth: int) -> bool:
        if depth > 6:
            return False
        for base in node.bases:
            rendered = ast.unparse(base)
            if any(root in rendered for root in roots):
                return True
            base_name = _plain_name(base)
            found = self.resolve(base_name, module) if base_name else None
            if found is not None and self._inherits(found[0], found[1], roots, depth + 1):
                return True
        return False

    def _module(self, module: str) -> Optional[ast.Module]:
        if module not in self._modules:
            base = self._root / module.replace(".", "/")
            candidates = [base.with_suffix(".py"), base / "__init__.py"]
            path = next((c for c in candidates if c.is_file()), None)
            self._modules[module] = _parse(path) if path is not None else None
        return self._modules[module]

    def _all_classes(self) -> Dict[str, List[Tuple[str, ast.ClassDef]]]:
        if self._by_name is None:
            self._by_name = defaultdict(list)
            for source in CLASS_SOURCES:
                for path in _python_files(self._root / source):
                    tree = _parse(path)
                    if tree is None:
                        continue
                    module = _module_name(path, self._root)
                    for node in tree.body:
                        if isinstance(node, ast.ClassDef):
                            self._by_name[node.name].append((module, node))
        return self._by_name


# --------------------------------------------------------------------------------------------- #
# SDK: the requests each resource sends                                                           #
# --------------------------------------------------------------------------------------------- #


def extract_sdk_calls(resources_root: Path) -> Tuple[List[SdkCall], List[Tuple[str, str]]]:
    """Every `self._client.<verb>(...)` request in the resources, plus the ones that could not be rendered."""
    calls: List[SdkCall] = []
    unrenderable: List[Tuple[str, str]] = []
    for path in sorted(resources_root.rglob("*.py")):
        tree = _parse(path)
        if tree is None:
            continue
        scope = _SdkModule(tree)
        relative = path.relative_to(resources_root).as_posix()
        for func in scope.functions():
            location = f"{relative}:{func.name}"
            for call in _calls_in(func):
                verb = _client_verb(call)
                if verb is None:
                    continue
                path_expr = call.args[0] if call.args else _keyword(call, "path")
                paths = scope.render(path_expr, func) if path_expr is not None else set()
                params_expr = _keyword(call, "params")
                keys, keys_ok = scope.param_keys(params_expr, func) if params_expr is not None else (set(), True)
                if not paths:
                    unrenderable.append((location, f"path `{ast.unparse(path_expr) if path_expr else '?'}`"))
                    continue
                if not keys_ok:
                    unrenderable.append((location, f"params `{ast.unparse(params_expr)}`"))
                call_id = f"{relative}:{call.lineno}"
                for rendered in sorted(paths):
                    calls.append(SdkCall(verb.upper(), normalise_path(rendered), location, set(keys), call_id))
        # The run socket is opened by URL, not through a verb: a `/ws` path constant is the call.
        for name, value in scope.constants.items():
            if value.startswith("/v1/") and value.endswith("/ws"):
                calls.append(SdkCall("WS", normalise_path(value), f"{relative}:{name}"))
    return calls, unrenderable


# --------------------------------------------------------------------------------------------- #
# Comparison                                                                                      #
# --------------------------------------------------------------------------------------------- #


def compare(routes: List[Route], calls: List[SdkCall], unrenderable: List[Tuple[str, str]]) -> RouteReport:
    declared = {route.key: route for route in routes}

    # A path helper with an `if` (`f"{base}/{n}" if n is not None else base`) renders every branch, and only the
    # branch each caller takes is a route. When some rendering of a call matches a declared route, the others are
    # branches that call never takes; when none does, every rendering is reported.
    by_call: Dict[str, List[SdkCall]] = defaultdict(list)
    for call in calls:
        by_call[call.call_id or f"{id(call)}"].append(call)
    calls = [
        call
        for group in by_call.values()
        for call in group
        if call.key in declared or not any(other.key in declared for other in group)
    ]

    report = RouteReport(upstream_routes=routes, sdk_calls=calls)
    sdk_query: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    sdk_locations: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for call in calls:
        sdk_query[call.key] |= call.query
        sdk_locations[call.key].append(call.location)

    for route in sorted((r for r in routes if r.public), key=lambda r: (r.router, r.path, r.method)):
        if route.key in sdk_query:
            continue
        if route.key in KNOWN_UNCOVERED_ROUTES:
            report.allowances_used.add(f"KNOWN_UNCOVERED_ROUTES:{route.method} {route.path}")
            continue
        report.missing_routes.append(route)

    for key in sorted(sdk_query):
        method, path = key
        route = declared.get(key)
        if route is None:
            report.sdk_routes_not_upstream.append((method, path, ", ".join(sorted(set(sdk_locations[key])))))
            continue
        for name in sorted(route.query - sdk_query[key]):
            if (method, path, name) in KNOWN_UNCOVERED_QUERY_FIELDS:
                report.allowances_used.add(f"KNOWN_UNCOVERED_QUERY_FIELDS:{method} {path} {name}")
                continue
            report.missing_query_fields.append((method, path, name))
        for name in sorted(sdk_query[key] - route.query):
            if (method, path, name) in KNOWN_SDK_ONLY_QUERY_FIELDS:
                report.allowances_used.add(f"KNOWN_SDK_ONLY_QUERY_FIELDS:{method} {path} {name}")
                continue
            report.sdk_query_not_upstream.append((method, path, name))

    for location, what in unrenderable:
        if location in KNOWN_UNRENDERABLE_CALLS:
            report.allowances_used.add(f"KNOWN_UNRENDERABLE_CALLS:{location}")
            continue
        report.unrenderable_calls.append((location, what))
    return report


def find_sdk_resources() -> Path:
    """`src/interactly/resources`, relative to this file."""
    return Path(__file__).resolve().parents[2] / SDK_RESOURCES


def build_report(ai_root: Path, resources_root: Optional[Path] = None) -> RouteReport:
    calls, unrenderable = extract_sdk_calls(resources_root or find_sdk_resources())
    return compare(extract_routes(ai_root), calls, unrenderable)


# --------------------------------------------------------------------------------------------- #
# Reporting                                                                                       #
# --------------------------------------------------------------------------------------------- #


def render_markdown(report: RouteReport, ai_root: Path) -> str:
    public = [r for r in report.upstream_routes if r.public]
    reached = {c.key for c in report.sdk_calls}
    lines: List[str] = [
        "# Route coverage report — the SDK's requests vs. upstream's routes",
        "",
        f"- Upstream: `{ai_root / ROUTERS_DIR}`",
        f"- Public routes: **{len(public)}**, of which the SDK calls **{sum(r.key in reached for r in public)}**",
        f"- SDK requests read: **{len(report.sdk_calls)}**",
        f"- **Total findings: {report.total}**",
        "",
    ]

    def section(title: str, rows: List[str], headers: str, sep: str) -> None:
        if not rows:
            return
        lines.extend([f"## {title} ({len(rows)})", "", headers, sep, *rows, ""])

    section(
        "Public routes the SDK does not call",
        [f"| `{r.method}` | `{r.path}` | `{r.router}` |" for r in report.missing_routes],
        "| Method | Path | Router |",
        "|---|---|---|",
    )
    section(
        "Query fields the SDK cannot send",
        [f"| `{m}` | `{p}` | `{n}` |" for m, p, n in report.missing_query_fields],
        "| Method | Path | Query field |",
        "|---|---|---|",
    )
    section(
        "SDK calls to routes upstream does not declare (a certain 404)",
        [f"| `{m}` | `{p}` | {loc} |" for m, p, loc in report.sdk_routes_not_upstream],
        "| Method | Path | Called from |",
        "|---|---|---|",
    )
    section(
        "SDK query keys upstream does not read",
        [f"| `{m}` | `{p}` | `{n}` |" for m, p, n in report.sdk_query_not_upstream],
        "| Method | Path | Query key |",
        "|---|---|---|",
    )
    section(
        "SDK calls this harness could not render",
        [f"| `{loc}` | {what} |" for loc, what in report.unrenderable_calls],
        "| Call | What could not be read |",
        "|---|---|",
    )
    if report.total == 0:
        lines.extend(["✅ **Every public route is called, with every query field it reads.**", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, help="Write the markdown report to this path")
    args = parser.parse_args()

    ai_root = find_interactly_ai_root()
    if ai_root is None:
        print("interactly-ai not found — route coverage skipped (set INTERACTLY_AI_ROOT to enable).")
        return 0

    report = build_report(ai_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_markdown(report, ai_root), encoding="utf-8")
        print(f"Report written to {args.output}")

    public = [r for r in report.upstream_routes if r.public]
    print(
        f"public routes={len(public)} sdk requests={len(report.sdk_calls)} | "
        + " | ".join(f"{label}={len(items)}" for label, items in report.counted_categories())
    )
    print(f"TOTAL FINDINGS: {report.total}")
    return 0 if report.total == 0 else 1


# --------------------------------------------------------------------------------------------- #
# Private: how each side is read                                                                 #
# --------------------------------------------------------------------------------------------- #


class _SdkModule:
    """One resource module: its path constants and functions, and how to render what its calls send."""

    def __init__(self, tree: ast.Module):
        self.constants: Dict[str, str] = {}
        self._functions: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self._methods: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.constants[target.id] = node.value.value
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._methods.setdefault(item.name, item)
        self._all = [*self._functions.values()] + [
            item
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

    def functions(self) -> List[ast.FunctionDef | ast.AsyncFunctionDef]:
        return self._all

    def render(self, expr: ast.expr, func: ast.AST, depth: int = 0, given: Optional[Set[str]] = None) -> Set[str]:
        """Every string `expr` can evaluate to, with a parameter rendered as `{}`; empty when it cannot tell.

        `given` is set when rendering inside a helper, as in `param_keys`: an `if` on whether one of the helper's
        parameters was passed (`f"{base}/{n}" if n is not None else base`) takes the branch this caller takes.
        """
        if depth > 6:
            return set()
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return {expr.value}
        if isinstance(expr, ast.JoinedStr):
            parts: List[Set[str]] = []
            for value in expr.values:
                if isinstance(value, ast.Constant):
                    parts.append({str(value.value)})
                elif isinstance(value, ast.FormattedValue):
                    inner = self.render(value.value, func, depth + 1, given)
                    parts.append(inner if inner and all(s.startswith("/") for s in inner) else {"{}"})
            return {"".join(combo) for combo in itertools.islice(itertools.product(*parts), 32)}
        if isinstance(expr, ast.Name):
            assigned = _local_values(func, expr.id)
            if assigned:
                return set().union(*(self.render(v, func, depth + 1, given) for v in assigned))
            return {self.constants[expr.id]} if expr.id in self.constants else set()
        if isinstance(expr, ast.IfExp):
            if given is not None and isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parameters = {a.arg for a, _ in _arguments_with_defaults(func.args)}
                guard = _guarded_parameter(expr.test, parameters)
                if guard is not None:
                    return self.render(expr.body if guard in given else expr.orelse, func, depth + 1, given)
            return self.render(expr.body, func, depth + 1, given) | self.render(expr.orelse, func, depth + 1, given)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            left = self.render(expr.left, func, depth + 1, given)
            right = self.render(expr.right, func, depth + 1, given)
            return {a + b for a in left for b in right}
        if isinstance(expr, ast.Call):
            callee = self._callee(expr)
            if callee is not None:
                callee_given = _possibly_given(callee, expr)
                rendered: Set[str] = set()
                for value in _returned(callee):
                    rendered |= self.render(value, callee, depth + 1, callee_given)
                return rendered
        return set()

    def param_keys(
        self, expr: ast.expr, func: ast.AST, depth: int = 0, given: Optional[Set[str]] = None
    ) -> Tuple[Set[str], bool]:
        """The query keys a `params=` argument can carry, and whether every part of it could be read.

        `given` is set when reading inside a helper: the helper's parameters the call site may pass a value for.
        A key the helper writes only under `if <parameter> is not None:` counts only when that parameter is given,
        so a shared helper's optional keys are not credited to callers that never pass them.
        """
        if depth > 6:
            return set(), False
        if isinstance(expr, ast.Constant) and expr.value is None:
            return set(), True
        if isinstance(expr, ast.Dict):
            keys: Set[str] = set()
            ok = True
            for key, value in zip(expr.keys, expr.values):
                if key is None:  # `**spread`
                    more, more_ok = self.param_keys(value, func, depth + 1, given)
                    keys |= more
                    ok = ok and more_ok
                elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
                else:
                    ok = False
            return keys, ok
        if isinstance(expr, ast.Name):
            assigned = _local_values(func, expr.id)
            if not assigned:
                return set(), False  # a parameter or a global: nothing here says what it holds
            keys, ok = set(), True
            for value in assigned:
                more, more_ok = self.param_keys(value, func, depth + 1, given)
                keys |= more
                ok = ok and more_ok
            written = _keys_written_to(func, expr.id)
            keys |= {key for key, guard in written.items() if given is None or guard is None or guard in given}
            return keys, ok
        if isinstance(expr, ast.Call):
            if _plain_name(expr.func) == "dict" and not expr.args:
                return {k.arg for k in expr.keywords if k.arg}, all(k.arg for k in expr.keywords)
            callee = self._callee(expr)
            if callee is None:
                return set(), False
            if callee.args.kwarg is not None:
                # A `**params` helper (`_list_params(limit=..., after=...)`): the call site names the keys.
                return {k.arg for k in expr.keywords if k.arg}, all(k.arg for k in expr.keywords)
            callee_given = _possibly_given(callee, expr)
            keys, ok = set(), bool(_returned(callee))
            for value in _returned(callee):
                more, more_ok = self.param_keys(value, callee, depth + 1, callee_given)
                keys |= more
                ok = ok and more_ok
            return keys, ok
        return set(), False

    def _callee(self, call: ast.Call) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:
        if isinstance(call.func, ast.Name):
            return self._functions.get(call.func.id)
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self"
        ):
            return self._methods.get(call.func.attr)
        return None


def _routers_in(tree: ast.Module) -> Dict[str, Tuple[str, bool]]:
    """Module-level `name = APIRouter(prefix=..., include_in_schema=...)` as {name: (prefix, hidden)}."""
    routers: Dict[str, Tuple[str, bool]] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        if _plain_name(node.value.func) != "APIRouter":
            continue
        prefix = _keyword_constant(node.value, "prefix") or ""
        hidden = _keyword_constant(node.value, "include_in_schema") is False
        for target in node.targets:
            if isinstance(target, ast.Name):
                routers[target.id] = (prefix, hidden)
    return routers


def _route_from_decorator(decorator: ast.expr, routers: Dict[str, Tuple[str, bool]]) -> Optional[Tuple[str, str, bool]]:
    """`@router.get("/x", include_in_schema=False)` -> ("GET", prefix + "/x", hidden), or None."""
    if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
        return None
    owner = decorator.func.value
    if not (isinstance(owner, ast.Name) and owner.id in routers):
        return None
    verb = decorator.func.attr
    if verb not in VERBS and verb != "websocket":
        return None
    if not (
        decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str)
    ):
        return None
    prefix, hidden = routers[owner.id]
    hidden = hidden or _keyword_constant(decorator, "include_in_schema") is False
    method = "WS" if verb == "websocket" else verb.upper()
    return method, prefix + decorator.args[0].value, hidden


def _query_fields(
    func: ast.FunctionDef | ast.AsyncFunctionDef, path_parameters: Set[str], module: str, index: ClassIndex
) -> Set[str]:
    """The query string names a route handler reads, following FastAPI's rules for each parameter."""
    names: Set[str] = set()
    for arg, default in _arguments_with_defaults(func.args):
        if arg.arg in path_parameters or arg.arg in ("self", "cls"):
            continue
        annotation, metadata = _unwrap_annotated(arg.annotation)
        marker_call = _marker_call(default) or next((m for m in metadata if _marker_call(m)), None)
        marker = _plain_name(marker_call.func) if marker_call is not None else None
        if marker in _NON_QUERY_MARKERS or _core_names(annotation) & _FRAMEWORK_TYPES:
            continue
        if marker == "Depends":
            if marker_call.args or any(k.arg == "dependency" for k in marker_call.keywords):
                continue  # a dependency function: its parameters are not read here (see the module docstring)
            found = _resolve_single(annotation, module, index)
            if found is not None:
                names |= index.query_fields_of(*found)
            continue
        if marker == "Query":
            if _keyword_constant(marker_call, "include_in_schema") is False:
                continue
            found = _resolve_single(annotation, module, index)
            if found is not None and index.is_model(*found):
                names |= index.query_fields_of(*found)
            else:
                names.add(_keyword_constant(marker_call, "alias") or arg.arg)
            continue
        if _is_scalar(annotation, module, index):
            names.add(arg.arg)
    return names


def _init_query_parameters(node: ast.ClassDef) -> Set[str]:
    """A plain dependency class's `__init__` parameters declared `= Query(...)`, by their query name."""
    for stmt in node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "__init__":
            names: Set[str] = set()
            for arg, default in _arguments_with_defaults(stmt.args):
                _, metadata = _unwrap_annotated(arg.annotation)
                call = _marker_call(default) or next((m for m in metadata if _marker_call(m)), None)
                if call is not None and _plain_name(call.func) == "Query":
                    if _keyword_constant(call, "include_in_schema") is not False:
                        names.add(_keyword_constant(call, "alias") or arg.arg)
            return names
    return set()


def _is_scalar(annotation: Optional[ast.expr], module: str, index: ClassIndex) -> bool:
    """Whether FastAPI reads a parameter of this annotation from the query string (no marker present)."""
    if annotation is None:
        return True  # an unannotated parameter is a string query parameter
    if isinstance(annotation, ast.Subscript) and _plain_name(annotation.value) == "Literal":
        return True
    names = _core_names(annotation) - {"None"}
    if not names:
        return False
    for name in names:
        if name in _SCALAR_TYPES:
            continue
        found = index.resolve(name, module)
        if found is None or not index.is_enum(*found):
            return False
    return True


def _resolve_single(
    annotation: Optional[ast.expr], module: str, index: ClassIndex
) -> Optional[Tuple[str, ast.ClassDef]]:
    names = _core_names(annotation) - {"None"}
    return index.resolve(next(iter(names)), module) if len(names) == 1 else None


def _client_verb(call: ast.Call) -> Optional[str]:
    """`self._client.get(...)` -> "get"; anything else -> None."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr in VERBS):
        return None
    owner = func.value
    if isinstance(owner, ast.Attribute) and owner.attr == "_client":
        return func.attr
    return None


def _calls_in(func: ast.AST) -> Iterable[ast.Call]:
    """The calls in a function's own body, not in functions nested inside it."""
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def _local_values(func: ast.AST, name: str) -> List[ast.expr]:
    """Every value assigned to `name` in a function's own body."""
    values: List[ast.expr] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            values.append(node.value)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value
        ):
            values.append(node.value)
    return values


def _keys_written_to(func: ast.AST, name: str) -> Dict[str, Optional[str]]:
    """Keys a function adds to a local dict after building it (`name["k"] = ...`, `.update(...)`, `.setdefault(...)`).

    Maps each key to the function parameter that guards the write (`if page is not None: name["page"] = page`), or
    None when the write is unconditional, so a caller that never passes that parameter is not credited with it.
    """
    parameters = (
        {a.arg for a, _ in _arguments_with_defaults(func.args)}
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        else set()
    )
    keys: Dict[str, Optional[str]] = {}

    def record(key: str, guard: Optional[str]) -> None:
        # Unconditional anywhere wins: the key is always sent.
        keys[key] = None if key in keys and keys[key] is None else guard

    stack: List[Tuple[ast.AST, Optional[str]]] = [(child, None) for child in ast.iter_child_nodes(func)]
    while stack:
        node, guard = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.If):
            inner = _guarded_parameter(node.test, parameters) or guard
            stack.extend((child, inner) for child in node.body)
            stack.extend((child, guard) for child in node.orelse)
            stack.append((node.test, guard))
            continue
        targets = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AugAssign) else []
        )
        for target in targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == name
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                record(target.slice.value, guard)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
        ):
            if node.func.attr == "update":
                for keyword in node.keywords:
                    if keyword.arg:
                        record(keyword.arg, guard)
                for arg in node.args:
                    if isinstance(arg, ast.Dict):
                        for key in arg.keys:
                            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                record(key.value, guard)
            elif node.func.attr == "setdefault" and node.args and isinstance(node.args[0], ast.Constant):
                record(str(node.args[0].value), guard)
        stack.extend((child, guard) for child in ast.iter_child_nodes(node))
    return keys


def _guarded_parameter(test: ast.expr, parameters: Set[str]) -> Optional[str]:
    """The parameter an `if` tests for presence: `x is not None`, `x`, `is_given(x)`, or the first such in an `and`."""
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        return next((p for p in (_guarded_parameter(v, parameters) for v in test.values) if p), None)
    if isinstance(test, ast.Name) and test.id in parameters:
        return test.id
    if (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id in parameters
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.IsNot)
    ):
        return test.left.id
    if isinstance(test, ast.Call) and _plain_name(test.func) == "is_given" and test.args:
        arg = test.args[0]
        return arg.id if isinstance(arg, ast.Name) and arg.id in parameters else None
    return None


def _possibly_given(callee: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call) -> Set[str]:
    """The callee's parameters this call may pass something other than None to, defaults included."""
    pairs = _arguments_with_defaults(callee.args)
    positional = [a for a, _ in pairs if a in callee.args.posonlyargs + callee.args.args]
    if positional and positional[0].arg in ("self", "cls") and isinstance(call.func, ast.Attribute):
        positional = positional[1:]
    passed: Dict[str, ast.expr] = {arg.arg: value for arg, value in zip(positional, call.args)}
    passed.update({k.arg: k.value for k in call.keywords if k.arg})
    given: Set[str] = set()
    for arg, default in pairs:
        value = passed.get(arg.arg, default)
        if value is None or (isinstance(value, ast.Constant) and value.value is None):
            continue
        given.add(arg.arg)
    return given


def _returned(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[ast.expr]:
    """The values a function returns, from its own body only."""
    values: List[ast.expr] = []
    stack = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return) and node.value is not None:
            values.append(node.value)
        stack.extend(ast.iter_child_nodes(node))
    return values


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


def _module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _plain_name(node: Optional[ast.expr]) -> Optional[str]:
    """`Foo` -> "Foo", `fastapi.Query` -> "Query", anything else -> None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _keyword(call: ast.Call, name: str) -> Optional[ast.expr]:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _keyword_constant(call: Optional[ast.Call], name: str) -> object:
    value = _keyword(call, name) if call is not None else None
    return value.value if isinstance(value, ast.Constant) else None


def _alias_of(value: Optional[ast.expr]) -> Optional[str]:
    """The `alias=` of a `Field(...)`/`Query(...)` default, which is the name the query string uses."""
    if isinstance(value, ast.Call):
        alias = _keyword_constant(value, "alias")
        return alias if isinstance(alias, str) else None
    return None


def _marker_call(node: Optional[ast.expr]) -> Optional[ast.Call]:
    """`Query(...)`, `Depends()`, `Body(...)`… as a call, or None."""
    if isinstance(node, ast.Call) and _plain_name(node.func) in _NON_QUERY_MARKERS | {"Query", "Depends"}:
        return node
    return None


def _unwrap_annotated(annotation: Optional[ast.expr]) -> Tuple[Optional[ast.expr], List[ast.expr]]:
    """`Annotated[X, Query()]` -> (X, [Query()]); anything else -> (annotation, [])."""
    if isinstance(annotation, ast.Subscript) and _plain_name(annotation.value) == "Annotated":
        elements = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        return elements[0], list(elements[1:])
    return annotation, []


def _core_names(annotation: Optional[ast.expr]) -> Set[str]:
    """The type names inside `Optional[...]`, `Union[...]`, `X | None`, `List[...]`, `Annotated[...]`."""
    if annotation is None:
        return set()
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            return _core_names(ast.parse(annotation.value, mode="eval").body)
        except SyntaxError:
            return set()
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return {"None"}
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _core_names(annotation.left) | _core_names(annotation.right)
    if isinstance(annotation, ast.Subscript):
        outer = _plain_name(annotation.value)
        elements = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        if outer == "Annotated":
            return _core_names(elements[0])
        if outer in ("Optional", "Union", "List", "list", "Sequence", "Set", "set", "FrozenSet", "Tuple", "tuple"):
            return set().union(*(_core_names(e) for e in elements))
        return {outer} if outer else set()
    name = _plain_name(annotation)
    return {name} if name else set()


def _arguments_with_defaults(arguments: ast.arguments) -> List[Tuple[ast.arg, Optional[ast.expr]]]:
    positional = arguments.posonlyargs + arguments.args
    padded = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
    return list(zip(positional, padded)) + list(zip(arguments.kwonlyargs, arguments.kw_defaults))


if __name__ == "__main__":
    raise SystemExit(main())
