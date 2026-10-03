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
property names, required-ness, published defaults, and enum value sets — for the endpoint's own model
AND for every model nested in its `$defs`.

**Why nested models matter.** An LLM node's schema embeds every LLM config class in `$defs`. When only
the root model's properties were compared, a whole provider family (`XAILLMConfig` and three siblings)
and new fields on existing ones (`GoogleLLMConfig.backend`) were live on the server and reported
nowhere. Each `$defs` model is compared once, however many schemas embed it.

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
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

# --------------------------------------------------------------------------------------------- #
# What to compare                                                                                 #
# --------------------------------------------------------------------------------------------- #

#: JSON Schema keys that carry prose or dashboard-only presentation, never data contract. `default` is
#: NOT among them: the dashboard seeds its forms from it, and a field with no published default is left
#: undefined rather than empty, so a missing or different default changes what a client sends.
IGNORED_SCHEMA_KEYS: Set[str] = {
    "title",
    "description",
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


#: Fields whose default the SERVER's schema omits because of a serializer the mirror does not need, as
#: field name -> reason. Suppresses only the exact shape "server publishes no default, mirror publishes
#: `null`"; any other default difference on these fields is still reported.
#:
#: Pydantic leaves a field's default out of a serialization-mode schema when a `field_serializer`
#: applies to it, since the serializer may turn the default into anything. Upstream puts
#: `@field_serializer(..., when_used="json")` on every `PydanticObjectId` field to stringify it; the
#: mirror types those fields as `str` (the forced self-containment substitution) and has nothing to
#: serialize, so its schema keeps `default: null`. Verified by building both shapes side by side.
KNOWN_SERIALIZER_DROPPED_DEFAULTS: Dict[str, str] = {
    "workflow_id": "upstream stringifies PydanticObjectId with a field_serializer; mirror field is str",
    "workflow_run_id": "upstream stringifies PydanticObjectId with a field_serializer; mirror field is str",
    "source_workflow_run_id": "upstream stringifies PydanticObjectId with a field_serializer; mirror field is str",
    "evaluator_workflow_id": "upstream stringifies PydanticObjectId with a field_serializer; mirror field is str",
    "evaluation_workflow_run_id": "upstream stringifies PydanticObjectId with a field_serializer; mirror field is str",
    "access_list": "upstream stringifies List[PydanticObjectId] with a field_serializer; mirror field is List[str]",
}

#: `$defs` the server publishes that the mirror deliberately has no class for, as name -> reason.
KNOWN_SERVER_ONLY_DEFS: Dict[str, str] = {
    # LangChain message and tool-call types, embedded through `WorkflowRun`'s message history. The mirror
    # carries messages as plain dicts so `interactly_configs` has no runtime dependency on
    # `langchain_core` -- the same reason config_parity maps `AnyMessage` to `Any`.
    **{
        name: "LangChain type; the mirror carries messages as plain dicts (no langchain_core dependency)"
        for name in (
            "AIMessage",
            "AIMessageChunk",
            "ChatMessage",
            "ChatMessageChunk",
            "FunctionMessage",
            "FunctionMessageChunk",
            "HumanMessage",
            "HumanMessageChunk",
            "InputTokenDetails",
            "InvalidToolCall",
            "OutputTokenDetails",
            "SystemMessage",
            "SystemMessageChunk",
            "ToolCall",
            "ToolCallChunk",
            "ToolMessage",
            "ToolMessageChunk",
            "UsageMetadata",
        )
    },
}

#: How the server's package paths map onto the mirror's, for `$defs` names Pydantic module-qualifies
#: (`agentic_workflow_framework__configs__workflow__GlobalConditionEdgeEvaluationMethod`) because two
#: classes share a name. Most specific prefix first.
MODULE_PREFIX_MAPPING: Tuple[Tuple[str, str], ...] = (
    ("agentic_workflow_framework.runtime.event", "interactly_configs.events.event"),
    ("agentic_workflow_framework.configs", "interactly_configs"),
    ("common.models.acls", "interactly_configs.acls"),
    ("common.configs.features.gemini_models", "interactly_configs.gemini_models"),
)


@dataclass
class SchemaFinding:
    """One difference between a served schema and its local counterpart."""

    endpoint: str
    model: str
    #: missing-property | extra-property | required-mismatch | default-mismatch | enum-missing |
    #: enum-extra | model-missing | enum-class-missing
    kind: str
    detail: str


@dataclass
class SchemaReport:
    findings: List[SchemaFinding] = field(default_factory=list)
    compared: List[Tuple[str, str]] = field(default_factory=list)   # (endpoint, model)
    nested_compared: List[str] = field(default_factory=list)        # `$defs` model names compared
    #: allow-list entries that actually suppressed something this run, as "<list name>:<key>". The live
    #: guard checks every entry appears here, so an entry whose reason has expired is reported.
    allowances_used: Set[str] = field(default_factory=set)
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

    # Discovered from the server like node types, not hard-coded: a fixed list of four never compared
    # `codebase_function` once the server grew it. The type list is role-filtered server-side, so a
    # credential below super-admin sees fewer types — what it cannot see, it cannot compare.
    local_tool_models = {kind.value: cls for kind, cls in ic.ToolType.get_type_to_config_map().items()}
    tool_types = (get_json(client, "/v1/tools/types") or {}).get("tool_types", [])
    for tool_type in tool_types:
        tool_model = local_tool_models.get(tool_type)
        endpoint = f"/v1/tools/schema/{tool_type}"
        work.append((endpoint, tool_model.__name__, tool_model) if tool_model is not None else (endpoint, "", None))

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


#: Marker for "this property publishes no default", distinct from a published default of `null`.
_NO_DEFAULT = object()

#: An id minted per process, such as `llm_b23a17fe-...`: a model-instance default (`llms_config`'s
#: `WorkflowDefaultLLMConfig()`) carries a `logical_id` generated when the class was defined, so the two
#: sides publish different uuids for what is the same default.
_GENERATED_ID = re.compile(r"^([A-Za-z_]*_)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _normalise_generated_ids(value: Any) -> Any:
    """Replace every minted uuid inside a default with a placeholder that keeps its prefix."""
    if isinstance(value, str):
        match = _GENERATED_ID.match(value)
        return f"{match.group(1) or ''}<uuid>" if match else value
    if isinstance(value, list):
        return [_normalise_generated_ids(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalise_generated_ids(item) for key, item in value.items()}
    return value


def _render_default(value: Any) -> str:
    return "(none)" if value is _NO_DEFAULT else f"`{json.dumps(value, sort_keys=True)}`"


_MIRROR_CLASSES: Optional[Dict[str, Any]] = None


def mirror_classes() -> Dict[str, Any]:
    """Every pydantic model and Enum defined anywhere in `interactly_configs`, keyed by plain name and by
    `module.Name`. Built once.

    Needed because a model's schema embeds only the classes its *own* annotations reach. The mirror
    types `WorkflowConfigFullyHydrated.node_configs` loosely on purpose (see config_parity's
    KNOWN_FIELD_DIVERGENCES), so the super-node schema does not embed the Google Docs or Athena configs
    the server's does — yet the mirror has every one of those classes, and they must be compared.
    """
    global _MIRROR_CLASSES
    if _MIRROR_CLASSES is not None:
        return _MIRROR_CLASSES

    import enum
    import importlib
    import inspect
    import pkgutil

    import interactly_configs
    from pydantic import BaseModel

    found: Dict[str, Any] = {}
    modules = [interactly_configs] + [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(interactly_configs.__path__, prefix="interactly_configs.")
    ]
    for module in modules:
        for name, obj in vars(module).items():
            if not inspect.isclass(obj) or obj.__module__ != module.__name__:
                continue
            if issubclass(obj, BaseModel) or (issubclass(obj, enum.Enum) and obj is not enum.Enum):
                found.setdefault(name, obj)
                found[f"{module.__name__}.{name}"] = obj
    _MIRROR_CLASSES = found
    return found


def _mirror_class_for_def(def_name: str) -> Optional[Any]:
    """The mirror class for a served `$defs` name, following Pydantic's module-qualified names."""
    classes = mirror_classes()
    if "__" not in def_name:
        return classes.get(def_name)
    *module_parts, class_name = def_name.split("__")
    server_module = ".".join(module_parts)
    for server_prefix, mirror_prefix in MODULE_PREFIX_MAPPING:
        if server_module == server_prefix or server_module.startswith(server_prefix + "."):
            mirror_module = mirror_prefix + server_module[len(server_prefix):]
            return classes.get(f"{mirror_module}.{class_name}")
    return None


def _local_definition(def_name: str, local_defs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The mirror's schema for a served `$defs` entry: from the local schema if it embeds one, else
    generated from the mirror class of that name."""
    embedded = local_defs.get(def_name)
    if isinstance(embedded, dict):
        return embedded
    cls = _mirror_class_for_def(def_name)
    if cls is None:
        return None
    import enum

    if issubclass(cls, enum.Enum):
        return {"enum": [member.value for member in cls]}
    return _resolve_root_ref(cls.model_json_schema(mode="serialization"))


def compare_model(
    endpoint: str,
    model_name: str,
    served: Dict[str, Any],
    local: Dict[str, Any],
    allowances_used: Optional[Set[str]] = None,
) -> List[SchemaFinding]:
    """Compare one object model's shape: property names, required-ness and published defaults."""
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

    for prop in sorted(set(served_props) & set(local_props)):
        served_default = _normalise_generated_ids(served_props[prop].get("default", _NO_DEFAULT))
        local_default = _normalise_generated_ids(local_props[prop].get("default", _NO_DEFAULT))
        if served_default is _NO_DEFAULT and local_default is None and prop in KNOWN_SERIALIZER_DROPPED_DEFAULTS:
            if allowances_used is not None:
                allowances_used.add(f"KNOWN_SERIALIZER_DROPPED_DEFAULTS:{prop}")
            continue
        if served_default != local_default:
            findings.append(
                SchemaFinding(
                    endpoint,
                    model_name,
                    "default-mismatch",
                    f"`{prop}`: server publishes {_render_default(served_default)}, "
                    f"mirror publishes {_render_default(local_default)}",
                )
            )
    return findings


def compare_schema(
    endpoint: str,
    model_name: str,
    served: Dict[str, Any],
    local: Dict[str, Any],
    allowances_used: Optional[Set[str]] = None,
) -> List[SchemaFinding]:
    """Compare an endpoint's root model, then the enums its `$defs` share with the mirror.

    Nested `$defs` *models* are compared separately, once each across the whole run — see
    `compare_nested_models`.
    """
    findings = compare_model(endpoint, model_name, served, local, allowances_used)

    served_enums, local_enums = _enum_values(served), _enum_values(local)
    for enum_name, served_values in sorted(served_enums.items()):
        local_values = local_enums.get(enum_name)
        if local_values is None:
            continue  # reported once per run as `enum-class-missing` by compare_nested_models
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


def compare_nested_models(
    endpoint: str,
    served: Dict[str, Any],
    local: Dict[str, Any],
    already_compared: Set[str],
    allowances_used: Optional[Set[str]] = None,
) -> Tuple[List[SchemaFinding], List[str]]:
    """Compare every `$defs` entry the server publishes against the mirror's definition of the same name.

    Returns `(findings, names compared)`. A name in `already_compared` is skipped and every name this
    call handles is added to it, so a definition embedded in many schemas (`GoogleLLMConfig` sits in
    every schema that carries an LLM config) is compared, and reported, exactly once.

    A served definition the mirror's schema does not contain at all is reported as `model-missing` or
    `enum-class-missing`. That is not certain to be a missing class — the mirror might name it
    differently — but the server publishing a definition the mirror never produces is worth a look
    either way, and silence is how `GoogleBackend` and four whole LLM configs went unreported.
    """
    findings: List[SchemaFinding] = []
    compared: List[str] = []
    served_defs = served.get("$defs") or {}
    local_defs = local.get("$defs") or {}

    for name in sorted(served_defs):
        if name in already_compared:
            continue
        already_compared.add(name)
        definition = served_defs[name]
        if not isinstance(definition, dict):
            continue
        is_enum = isinstance(definition.get("enum"), list)
        is_model = "properties" in definition
        if not (is_enum or is_model):
            continue
        if name in KNOWN_SERVER_ONLY_DEFS:
            if allowances_used is not None:
                allowances_used.add(f"KNOWN_SERVER_ONLY_DEFS:{name}")
            continue

        local_definition = _local_definition(name, local_defs)
        if local_definition is None:
            kind = "enum-class-missing" if is_enum else "model-missing"
            findings.append(SchemaFinding(endpoint, name, kind, "server publishes it, mirror has no class"))
            continue
        if is_model:
            compared.append(name)
            findings.extend(compare_model(endpoint, name, definition, local_definition, allowances_used))
        elif name not in local_defs:
            # An enum both schemas embed is already compared by compare_schema. One reached only through
            # the mirror-wide lookup is compared here, keyed by its plain name so _dedupe merges it.
            served_values = {str(v) for v in definition["enum"]}
            local_values = {str(v) for v in local_definition.get("enum", [])}
            plain_name = name.rsplit("__", 1)[-1]
            findings.extend(
                SchemaFinding(endpoint, plain_name, "enum-missing", f"server offers `{v}`")
                for v in sorted(served_values - local_values)
            )
            findings.extend(
                SchemaFinding(endpoint, plain_name, "enum-extra", f"mirror offers `{v}` — **server would reject it**")
                for v in sorted(local_values - served_values)
            )
    return findings, compared


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
    # Root models first, nested `$defs` second: a model that is one endpoint's root (`WorkflowConfig`)
    # can also sit in another endpoint's `$defs`, and should be compared once, as the root.
    pairs: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
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
            # `mode="serialization"` because that is what the server publishes — every schema route
            # calls `model_json_schema(mode="serialization")`. The default is validation mode, and the
            # two genuinely differ: a field declared `exclude=True` is present in the validation schema
            # and absent from the serialization one. Comparing the modes reported such a field as
            # "mirror has it, server does not" when both sides were in fact identical, which is a
            # finding about this harness rather than about the mirror.
            local = model.model_json_schema(mode="serialization")
        except Exception as exc:  # pragma: no cover - defensive
            report.errors.append((endpoint, f"could not build local schema: {exc}"))
            continue

        report.compared.append((endpoint, model_name))
        report.findings.extend(compare_schema(endpoint, model_name, served, local, report.allowances_used))
        pairs.append((endpoint, served, local))

    already_compared: Set[str] = {model_name for _, model_name in report.compared}
    for endpoint, served, local in pairs:
        findings, nested = compare_nested_models(endpoint, served, local, already_compared, report.allowances_used)
        report.findings.extend(findings)
        report.nested_compared.extend(nested)

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
        f"- Schemas compared: **{len(report.compared)}**, plus **{len(report.nested_compared)}** nested models",
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
        f"compared={len(report.compared)} nested={len(report.nested_compared)} findings={len(report.findings)} "
        f"unmapped={len(report.unmapped)} errors={len(report.errors)}"
    )
    return 0 if report.is_clean else 1


if __name__ == "__main__":
    sys.exit(main())
