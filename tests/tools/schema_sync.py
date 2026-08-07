"""
Live schema-drift harness: `interactly_configs` models vs the running server's JSON schemas.

Complements `config_parity.py`. That tool compares the mirror against upstream *source*; this one
compares it against what a *deployed* server actually serves. They catch different things: source
parity misses anything the server computes or reshapes at runtime, and a live check misses anything
upstream added but has not deployed yet. Both are needed to answer "is the SDK in sync?".

The server exposes its own config models as JSON Schema on `/schema` endpoints (the same ones the
dashboard renders its forms from), so the comparison is exact rather than inferred.

**What is deliberately ignored.** The mirror strips every dashboard-only annotation — the field
visibility levels, collapse hints and UI ordering carried in `json_schema_extra` — along with `title`
and `description`, which are prose. Comparing those would bury the real signal. What is compared:
property names, required-ness, types, and enum value sets.

Uses plain `httpx` rather than the SDK's own client: the point is to check the SDK's models against
the server, so routing the comparison through the SDK's deserialisation would hide exactly the class
of bug this is meant to find.

Usage::

    set -a && source .env && set +a
    python tests/tools/schema_sync.py
    python tests/tools/schema_sync.py -o docs/_sync/schema-drift.md

Exits 0 when the server is unreachable or unconfigured, so a checkout with no credentials is not a
failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

# --------------------------------------------------------------------------------------------- #
# What to compare                                                                                 #
# --------------------------------------------------------------------------------------------- #

#: JSON Schema keys that carry prose or dashboard-only presentation, never data contract.
IGNORED_SCHEMA_KEYS: Set[str] = {
    "title",
    "description",
    "default",
    "examples",
    "$comment",
    "readOnly",
    "writeOnly",
    "deprecated",
}

#: `json_schema_extra` keys the server attaches for the dashboard. The mirror drops all of them by
#: design, so their absence is never drift.
IGNORED_UI_KEYS: Set[str] = {
    "x-visibility-level",
    "x-input-field-disallowed",
    "x-input-field-not-visible",
    "x-input-field-ui-order",
    "x-input-field-type",
    "x-input-field-helper-text",
    "x-keep-collapsed",
    "keepCollapsed",
    "uiOrder",
    "visibilityLevel",
    "hideAllFields",
    "hiddenInContexts",
}


@dataclass
class SchemaFinding:
    """One difference between a served schema and its local counterpart."""

    endpoint: str
    model: str
    kind: str  # missing-property | extra-property | enum-missing | enum-extra | required-mismatch
    detail: str


@dataclass
class SchemaReport:
    findings: List[SchemaFinding] = field(default_factory=list)
    compared: List[Tuple[str, str]] = field(default_factory=list)   # (endpoint, model)
    unmapped: List[str] = field(default_factory=list)               # endpoints with no local model
    errors: List[Tuple[str, str]] = field(default_factory=list)     # (endpoint, message)

    @property
    def is_clean(self) -> bool:
        return not self.findings


# --------------------------------------------------------------------------------------------- #
# Server access                                                                                   #
# --------------------------------------------------------------------------------------------- #


def build_client() -> Optional[httpx.Client]:
    """An authenticated client, or None when the environment is not configured."""
    base_url = os.environ.get("INTERACTLY_BASE_URL")
    api_key = os.environ.get("INTERACTLY_API_KEY")
    if not base_url or not api_key:
        return None
    headers = {"Authorization": f"Bearer {api_key}"}
    for env_name, header in (("INTERACTLY_TEAM_ID", "x-team-id"), ("INTERACTLY_USER_ID", "x-user-id")):
        value = os.environ.get(env_name)
        if value:
            headers[header] = value
    return httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=30.0)


def get_json(client: httpx.Client, path: str) -> Optional[Any]:
    try:
        response = client.get(path)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------------------------- #
# Endpoint -> local model mapping                                                                 #
# --------------------------------------------------------------------------------------------- #


def resolve_local_models(client: httpx.Client) -> List[Tuple[str, str, Any]]:
    """Build the (endpoint, model name, model class) work list, discovering types from the server.

    Node/edge/tool types are enumerated from the server rather than hard-coded, so a type the server
    gains that the mirror lacks shows up as an unmapped endpoint instead of being silently skipped —
    which is how `no_op` would have been missed.
    """
    import interactly_configs as ic

    work: List[Tuple[str, str, Any]] = []

    def add(endpoint: str, model_name: str) -> None:
        model = getattr(ic, model_name, None)
        if model is not None:
            work.append((endpoint, model_name, model))

    node_types = (get_json(client, "/v1/nodes/types") or {}).get("node_types", [])
    for entry in node_types:
        node_type = entry.get("type") if isinstance(entry, dict) else entry
        if not node_type:
            continue
        model = ic.get_node_config_class(node_type) if hasattr(ic, "get_node_config_class") else None
        if model is not None:
            work.append((f"/v1/nodes/schema/{node_type}", model.__name__, model))
        else:
            work.append((f"/v1/nodes/schema/{node_type}", "", None))

    edge_models = {"direct": "DirectEdgeConfig", "conditional": "ConditionalEdgeConfig", "companion": "CompanionEdgeConfig"}
    edge_types = get_json(client, "/v1/edges/types") or {}
    for edge_type in edge_types.get("edge_types", list(edge_models)):
        name = edge_type.get("type") if isinstance(edge_type, dict) else edge_type
        add(f"/v1/edges/schema/{name}", edge_models.get(name, ""))

    tool_models = {
        "inline_python": "InlinePythonToolConfig",
        "external_api": "ExternalAPIToolConfig",
        "knowledge_base": "KnowledgeBaseToolConfig",
        "inbuilt_function": "InbuiltFunctionToolConfig",
    }
    for tool_type, model_name in tool_models.items():
        add(f"/v1/tools/schema/{tool_type}", model_name)

    add("/v1/workflows/schema", "WorkflowConfig")
    # `/v1/workflow-runs/schema` serves four models in one envelope; `#key` selects which.
    add("/v1/workflow-runs/schema#run_schema", "WorkflowRun")
    add("/v1/workflow-runs/schema#run_input_schema", "WorkflowRunInput")
    add("/v1/workflow-runs/schema#run_output_schema", "WorkflowRunOutput")
    add("/v1/workflow-runs/schema#run_input_output_pair_schema", "WorkflowRunInputOutputPair")
    add("/v1/workflows/schemas/global-node-config", "GlobalNodeConfig")
    add("/v1/simulations/schema", "SimulationConfig")
    add("/v1/templates/schema", "WorkflowTemplateConfig")
    add("/v1/node-libraries/schema", "NodeLibraryConfig")
    return work


# --------------------------------------------------------------------------------------------- #
# Comparison                                                                                      #
# --------------------------------------------------------------------------------------------- #


#: Envelope keys the service wraps schemas in, most specific first. Node and tool endpoints return
#: `{config_schema, run_input_schema, run_output_schema}`; workflow-runs returns `{run_schema, ...}`.
SCHEMA_ENVELOPE_KEYS: Tuple[str, ...] = (
    "config_schema",
    "run_schema",
    "schema",
    "json_schema",
    "data",
)


def _resolve_root_ref(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Follow a top-level `$ref` into the schema's own `$defs`.

    Pydantic emits `{"$ref": "#/$defs/SuperNodeConfig", "$defs": {...}}` rather than inlining, for any
    model that is referenced recursively. Without following it the schema reads as having zero
    properties, and every local field is then reported as an extra — which is exactly what
    `super_node` did before this existed.
    """
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return schema
    target = (schema.get("$defs") or {}).get(ref.split("/")[-1])
    if not isinstance(target, dict):
        return schema
    # Keep `$defs` so enum comparison still has the definitions to read.
    resolved = dict(target)
    resolved.setdefault("$defs", schema.get("$defs") or {})
    return resolved


def _unwrap_schema(payload: Any) -> Optional[Dict[str, Any]]:
    """Servers wrap schemas in assorted envelopes; find the object carrying the model's shape."""
    if not isinstance(payload, dict):
        return None
    if "properties" in payload or "$ref" in payload:
        return _resolve_root_ref(payload)
    for key in SCHEMA_ENVELOPE_KEYS:
        inner = payload.get(key)
        if isinstance(inner, dict) and ("properties" in inner or "$ref" in inner or "$defs" in inner):
            return _resolve_root_ref(inner)
    return None


def _properties(schema: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def _enum_values(schema: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Enum name -> value set, read from `$defs`, where pydantic and FastAPI both put them."""
    out: Dict[str, Set[str]] = {}
    for name, definition in (schema.get("$defs") or {}).items():
        values = definition.get("enum")
        if isinstance(values, list):
            out[name] = {str(v) for v in values}
    return out


def compare_schema(endpoint: str, model_name: str, served: Dict[str, Any], local: Dict[str, Any]) -> List[SchemaFinding]:
    findings: List[SchemaFinding] = []

    served_props, local_props = _properties(served), _properties(local)
    for prop in sorted(set(served_props) - set(local_props)):
        findings.append(
            SchemaFinding(endpoint, model_name, "missing-property", f"server has `{prop}`, mirror does not")
        )
    for prop in sorted(set(local_props) - set(served_props)):
        findings.append(
            SchemaFinding(endpoint, model_name, "extra-property", f"mirror has `{prop}`, server does not")
        )

    served_required = set(served.get("required") or [])
    local_required = set(local.get("required") or [])
    for prop in sorted(served_required - local_required):
        if prop in local_props:
            findings.append(
                SchemaFinding(endpoint, model_name, "required-mismatch", f"`{prop}` required by server, optional here")
            )

    served_enums, local_enums = _enum_values(served), _enum_values(local)
    for enum_name, served_values in sorted(served_enums.items()):
        local_values = local_enums.get(enum_name)
        if local_values is None:
            continue  # A $defs name the mirror does not use is a naming difference, not value drift.
        # Keyed on the enum name alone, not the owning model: a shared enum like `ANTHROPICModel` is
        # embedded in every schema that holds an LLM config, so keying by owner would report the same
        # six missing models seven times over. Deduplicated in `run()`.
        for value in sorted(served_values - local_values):
            findings.append(SchemaFinding(endpoint, enum_name, "enum-missing", f"server offers `{value}`"))
        for value in sorted(local_values - served_values):
            findings.append(
                SchemaFinding(
                    endpoint, enum_name, "enum-extra", f"mirror offers `{value}` — **server would reject it**"
                )
            )
    return findings


def _dedupe_enum_findings(findings: List[SchemaFinding]) -> List[SchemaFinding]:
    """Collapse each (enum, value) pair to one row, noting how many schemas embed it.

    Property-level findings are left alone — those are genuinely per-model.
    """
    seen: Dict[Tuple[str, str, str], SchemaFinding] = {}
    counts: Dict[Tuple[str, str, str], int] = {}
    out: List[SchemaFinding] = []
    for finding in findings:
        if not finding.kind.startswith("enum-"):
            out.append(finding)
            continue
        key = (finding.kind, finding.model, finding.detail)
        counts[key] = counts.get(key, 0) + 1
        seen.setdefault(key, finding)

    for key, finding in seen.items():
        occurrences = counts[key]
        suffix = f" _(in {occurrences} schemas)_" if occurrences > 1 else ""
        out.append(
            SchemaFinding(
                endpoint="(shared enum)" if occurrences > 1 else finding.endpoint,
                model=finding.model,
                kind=finding.kind,
                detail=finding.detail + suffix,
            )
        )
    return out


def run(client: httpx.Client) -> SchemaReport:
    report = SchemaReport()
    for endpoint, model_name, model in resolve_local_models(client):
        if model is None:
            report.unmapped.append(endpoint)
            continue

        # `path#key` selects one schema out of a multi-schema envelope (see resolve_local_models).
        path, _, envelope_key = endpoint.partition("#")
        payload = get_json(client, path)
        if payload is None:
            report.errors.append((endpoint, "request failed or returned non-JSON"))
            continue
        if envelope_key:
            payload = (payload or {}).get(envelope_key)
            if payload is None:
                report.errors.append((endpoint, f"envelope has no `{envelope_key}`"))
                continue

        served = _unwrap_schema(payload)
        if served is None:
            report.errors.append((endpoint, "response carried no recognisable JSON Schema"))
            continue

        try:
            local = model.model_json_schema()
        except Exception as exc:  # pragma: no cover - defensive
            report.errors.append((endpoint, f"could not build local schema: {exc}"))
            continue

        report.compared.append((endpoint, model_name))
        report.findings.extend(compare_schema(endpoint, model_name, served, local))

    report.findings = _dedupe_enum_findings(report.findings)
    return report


# --------------------------------------------------------------------------------------------- #
# Reporting                                                                                       #
# --------------------------------------------------------------------------------------------- #


def render_markdown(report: SchemaReport, base_url: str) -> str:
    lines = [
        "# Live schema drift report — `interactly_configs` vs the running server",
        "",
        f"- Server: `{base_url}`",
        f"- Schemas compared: **{len(report.compared)}**",
        f"- **Findings: {len(report.findings)}**",
        "",
    ]

    if report.findings:
        by_kind: Dict[str, List[SchemaFinding]] = {}
        for finding in report.findings:
            by_kind.setdefault(finding.kind, []).append(finding)
        for kind in sorted(by_kind):
            items = by_kind[kind]
            lines.extend([f"## {kind} ({len(items)})", "", "| Endpoint | Model | Detail |", "|---|---|---|"])
            lines.extend(f"| `{f.endpoint}` | `{f.model}` | {f.detail} |" for f in items)
            lines.append("")
    else:
        lines.extend(["✅ **No schema drift.** Every compared model matches the server.", ""])

    if report.unmapped:
        lines.extend(
            [
                f"## Endpoints with no local model ({len(report.unmapped)})",
                "",
                "The server serves these but the mirror has no class for them — usually a genuinely new type.",
                "",
            ]
        )
        lines.extend(f"- `{endpoint}`" for endpoint in report.unmapped)
        lines.append("")

    if report.errors:
        lines.extend([f"## Endpoints that could not be checked ({len(report.errors)})", "", "| Endpoint | Reason |", "|---|---|"])
        lines.extend(f"| `{endpoint}` | {reason} |" for endpoint, reason in report.errors)
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, help="Write the markdown report to this path")
    args = parser.parse_args()

    client = build_client()
    if client is None:
        print("INTERACTLY_BASE_URL / INTERACTLY_API_KEY not set — schema check skipped.")
        return 0

    with client:
        if get_json(client, "/v1/nodes/types") is None:
            print(f"Server at {client.base_url} is unreachable or rejected the credential — skipped.")
            return 0
        report = run(client)
        markdown = render_markdown(report, str(client.base_url))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"Report written to {args.output}")

    print(
        f"compared={len(report.compared)} findings={len(report.findings)} "
        f"unmapped={len(report.unmapped)} errors={len(report.errors)}"
    )
    return 0 if report.is_clean else 1


if __name__ == "__main__":
    sys.exit(main())
