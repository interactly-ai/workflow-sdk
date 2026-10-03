"""The drift harnesses' own checks, proven against fixtures where the right answer is known.

`test_drift_guards.py` runs the harnesses against the real trees, which proves they run and that the
count has not moved. It cannot prove a check *detects* what it claims to: a check that never fires
reads exactly like a mirror with nothing wrong. Each test here builds the smallest pair of trees, or
schemas, that a check must flag — and the nearest pair it must not — so a check that goes blind fails
here rather than reporting a reassuring zero.

All offline. No monorepo and no server needed.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import config_parity as cp  # noqa: E402
import schema_sync as ss  # noqa: E402

# --------------------------------------------------------------------------------------------- #
# config_parity                                                                                   #
# --------------------------------------------------------------------------------------------- #


def _write(root: Path, files: Dict[str, str]) -> Path:
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source), encoding="utf-8")
    return root


def _parity(tmp_path: Path, upstream: Dict[str, str], mirror: Dict[str, str]) -> cp.ParityReport:
    up_root = _write(tmp_path / "upstream", upstream)
    mir_root = _write(tmp_path / "mirror", mirror)
    return cp.compare(
        cp.extract_tree([up_root]),
        cp.extract_tree([mir_root]),
        mirror_constants=cp.extract_module_constants([mir_root]),
        upstream_unions=cp.extract_unions([up_root]),
        mirror_unions=cp.extract_unions([mir_root]),
    )


_TWO_VALIDATORS = """
    from pydantic import BaseModel, model_validator

    class ToolCfg(BaseModel):
        x: int = 0

        @model_validator(mode="after")
        def _first(self):
            return self

        @model_validator(mode="after")
        def _second(self):
            return self
"""

_FIRST_VALIDATOR_ONLY = """
    from pydantic import BaseModel, model_validator

    class ToolCfg(BaseModel):
        x: int = 0

        @model_validator(mode="after")
        def _first(self):
            return self
"""


class TestValidatorsAreComparedByName:
    def test_a_second_same_mode_validator_missing_from_the_mirror_is_reported(self, tmp_path):
        # Arrange: upstream has two `after` validators, the mirror only the first.
        # Act
        report = _parity(tmp_path, {"tool.py": _TWO_VALIDATORS}, {"tool.py": _FIRST_VALIDATOR_ONLY})
        # Assert
        assert report.missing_validators == [("ToolCfg", "model_validator:after:_second")]

    def test_identical_validators_report_nothing(self, tmp_path):
        report = _parity(tmp_path, {"tool.py": _TWO_VALIDATORS}, {"tool.py": _TWO_VALIDATORS})
        assert report.missing_validators == []

    def test_a_listed_rename_is_not_reported(self, tmp_path, monkeypatch):
        # Arrange: the mirror carries `_second` under another name, and says so.
        renamed = _TWO_VALIDATORS.replace("def _second", "def _second_renamed")
        monkeypatch.setitem(cp.KNOWN_VALIDATOR_RENAMES, "ToolCfg._second", "_second_renamed")
        # Act
        report = _parity(tmp_path, {"tool.py": _TWO_VALIDATORS}, {"tool.py": renamed})
        # Assert
        assert report.missing_validators == []

    def test_an_unlisted_rename_is_reported(self, tmp_path):
        renamed = _TWO_VALIDATORS.replace("def _second", "def _second_renamed")
        report = _parity(tmp_path, {"tool.py": _TWO_VALIDATORS}, {"tool.py": renamed})
        assert report.missing_validators == [("ToolCfg", "model_validator:after:_second")]

    def test_an_inherited_validator_satisfies_a_subclass(self, tmp_path):
        # Upstream declares the validator on the subclass; the mirror on its base. Same behaviour.
        upstream = """
            from pydantic import BaseModel, model_validator
            class Base(BaseModel):
                pass
            class Child(Base):
                @model_validator(mode="after")
                def _check(self):
                    return self
        """
        mirror = """
            from pydantic import BaseModel, model_validator
            class Base(BaseModel):
                @model_validator(mode="after")
                def _check(self):
                    return self
            class Child(Base):
                pass
        """
        report = _parity(tmp_path, {"m.py": upstream}, {"m.py": mirror})
        assert ("Child", "model_validator:after:_check") not in report.missing_validators


class TestDefaultsKeepLiteralAndFactoryApart:
    @staticmethod
    def _field(default: str) -> str:
        return f"""
            from typing import List
            from pydantic import BaseModel, Field
            class Cfg(BaseModel):
                items: List[str] = Field({default})
        """

    def test_a_literal_upstream_and_a_factory_in_the_mirror_is_reported(self, tmp_path):
        # Arrange / Act
        report = _parity(
            tmp_path, {"m.py": self._field("default=[]")}, {"m.py": self._field("default_factory=list")}
        )
        # Assert: only the literal reaches the published JSON Schema, so this is a real difference.
        assert report.default_mismatches == [("Cfg", "items", "[]", "factory:list")]

    def test_the_same_literal_on_both_sides_is_not_reported(self, tmp_path):
        report = _parity(tmp_path, {"m.py": self._field("default=[]")}, {"m.py": self._field("default=[]")})
        assert report.default_mismatches == []

    def test_quote_style_and_whitespace_are_not_differences(self, tmp_path):
        report = _parity(
            tmp_path, {"m.py": self._field("default=['a',  'b']")}, {"m.py": self._field('default=["a", "b"]')}
        )
        assert report.default_mismatches == []


_UPSTREAM_ENUM = """
    from enum import Enum, nonmember

    class GOOGLEModel(str, Enum):
        A = "model-a"
        B = "model-b"
        C = "model-c"
        ALWAYS_THINKING_MODELS = nonmember(frozenset({A, B}))
        DEFAULT_TOKENS = nonmember(4096)
"""


def _mirror_enum(always_thinking: str, default_tokens: str = "4096") -> str:
    return f"""
        from enum import Enum

        class GOOGLEModel(str, Enum):
            A = "model-a"
            B = "model-b"
            C = "model-c"

        ALWAYS_THINKING_GOOGLE_MODELS = {always_thinking}
        DEFAULT_TOKENS = {default_tokens}
    """


@pytest.fixture
def hoisted(monkeypatch):
    monkeypatch.setattr(
        cp,
        "KNOWN_HOISTED_NONMEMBERS",
        {
            "GOOGLEModel.ALWAYS_THINKING_MODELS": "ALWAYS_THINKING_GOOGLE_MODELS",
            "GOOGLEModel.DEFAULT_TOKENS": "DEFAULT_TOKENS",
        },
    )


class TestHoistedCapabilityDataIsComparedByValue:
    def test_a_stale_hoisted_set_is_reported(self, tmp_path, hoisted):
        # Arrange: upstream added B to the set; the mirror's hoisted copy still has only A.
        mirror = _mirror_enum("frozenset({GOOGLEModel.A})")
        # Act
        report = _parity(tmp_path, {"llm.py": _UPSTREAM_ENUM}, {"llm.py": mirror})
        # Assert
        assert report.nonmember_value_mismatches == [
            ("GOOGLEModel", "ALWAYS_THINKING_MODELS", "{'model-a', 'model-b'}", "{'model-a'}")
        ]
        assert report.missing_nonmembers == []

    def test_the_same_members_in_another_order_and_spelling_match(self, tmp_path, hoisted):
        # Bare names upstream, qualified names in the mirror, different order: the same set.
        mirror = _mirror_enum("frozenset({GOOGLEModel.B, GOOGLEModel.A})")
        report = _parity(tmp_path, {"llm.py": _UPSTREAM_ENUM}, {"llm.py": mirror})
        assert report.nonmember_value_mismatches == []

    def test_a_changed_scalar_is_reported(self, tmp_path, hoisted):
        mirror = _mirror_enum("frozenset({GOOGLEModel.A, GOOGLEModel.B})", default_tokens="8192")
        report = _parity(tmp_path, {"llm.py": _UPSTREAM_ENUM}, {"llm.py": mirror})
        assert report.nonmember_value_mismatches == [("GOOGLEModel", "DEFAULT_TOKENS", "4096", "8192")]

    def test_a_hoisted_symbol_absent_from_the_mirror_is_reported(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cp, "KNOWN_HOISTED_NONMEMBERS", {"GOOGLEModel.ALWAYS_THINKING_MODELS": "NOT_THERE"})
        upstream = _UPSTREAM_ENUM.replace("        DEFAULT_TOKENS = nonmember(4096)\n", "")
        report = _parity(tmp_path, {"llm.py": upstream}, {"llm.py": _mirror_enum("frozenset()")})
        assert len(report.nonmember_value_mismatches) == 1
        assert "NOT_THERE" in report.nonmember_value_mismatches[0][3]

    def test_an_unlisted_nonmember_is_reported_as_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cp, "KNOWN_HOISTED_NONMEMBERS", {})
        report = _parity(tmp_path, {"llm.py": _UPSTREAM_ENUM}, {"llm.py": _mirror_enum("frozenset()")})
        assert sorted(report.missing_nonmembers) == [
            ("GOOGLEModel", "ALWAYS_THINKING_MODELS"),
            ("GOOGLEModel", "DEFAULT_TOKENS"),
        ]

    def test_an_expression_the_evaluator_cannot_reduce_is_never_equal(self):
        expr = ast.parse("compute_models()", mode="eval").body
        rendered = cp.evaluate_capability_value(expr, {}, {})
        assert rendered.startswith("<unresolved:")


class TestUnionMembership:
    _UPSTREAM = """
        from typing import Annotated, Union
        from pydantic import BaseModel, Field
        class A(BaseModel): ...
        class B(BaseModel): ...
        Cfg = Annotated[Union[A, B], Field(discriminator="type")]
    """

    def test_a_member_missing_from_the_mirror_union_is_reported(self, tmp_path):
        # Arrange: the mirror has class B, but left it out of the union a payload is validated against.
        mirror = self._UPSTREAM.replace("Union[A, B]", "A")
        # Act
        report = _parity(tmp_path, {"m.py": self._UPSTREAM}, {"m.py": mirror})
        # Assert
        assert report.missing_union_members == [("Cfg", "B")]
        assert report.missing_classes == []

    def test_pep_604_and_union_subscript_compare_equal(self, tmp_path):
        mirror = self._UPSTREAM.replace("Union[A, B]", "A | B")
        report = _parity(tmp_path, {"m.py": self._UPSTREAM}, {"m.py": mirror})
        assert report.missing_union_members == []
        assert report.extra_union_members == []

    def test_a_union_the_mirror_lacks_entirely_is_reported(self, tmp_path):
        mirror = self._UPSTREAM.replace('Cfg = Annotated[Union[A, B], Field(discriminator="type")]', "")
        report = _parity(tmp_path, {"m.py": self._UPSTREAM}, {"m.py": mirror})
        assert report.missing_unions == ["Cfg"]

    def test_a_plain_type_alias_is_not_a_union(self):
        tree = ast.parse("Alias = List[str]")
        assert cp._union_members(tree.body[0].value) is None


class TestUnmirroredDependencies:
    @staticmethod
    def _monorepo(tmp_path: Path, imported_class: str) -> Tuple[Path, List[Path]]:
        root = _write(
            tmp_path / "interactly-ai",
            {
                "agentic_workflow_framework/configs/llm.py": f"""
                    from common.features.levels import {imported_class}
                    from common.logging.custom_logger import logger
                """,
                "common/features/levels.py": f"class {imported_class}:\n    pass\n",
                "common/logging/custom_logger.py": "logger = object()\n",
            },
        )
        return root, [root / "agentic_workflow_framework/configs"]

    def test_a_class_imported_from_an_unparsed_module_is_reported(self, tmp_path):
        # Arrange / Act
        root, sources = self._monorepo(tmp_path, "ThinkingLevel")
        found = cp.find_unmirrored_dependencies(root, sources)
        # Assert: the class is reported, the logger (not a class) is not.
        assert found == [("agentic_workflow_framework/configs/llm.py", "common.features.levels", "ThinkingLevel")]

    def test_an_import_from_inside_the_sources_is_not_reported(self, tmp_path):
        root, sources = self._monorepo(tmp_path, "ThinkingLevel")
        assert cp.find_unmirrored_dependencies(root, sources + [root / "common/features/levels.py"]) == []

    def test_an_allow_listed_class_is_reported_only_when_asked(self, tmp_path, monkeypatch):
        monkeypatch.setitem(cp.KNOWN_UNMIRRORED_DEPENDENCIES, "ThinkingLevel", "fixture")
        root, sources = self._monorepo(tmp_path, "ThinkingLevel")
        assert cp.find_unmirrored_dependencies(root, sources) == []
        assert len(cp.find_unmirrored_dependencies(root, sources, include_known=True)) == 1


# --------------------------------------------------------------------------------------------- #
# schema_sync                                                                                     #
# --------------------------------------------------------------------------------------------- #


def _model(properties: Dict[str, dict], required: Tuple[str, ...] = ()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required)}


class TestNestedModelsAreCompared:
    def test_a_property_missing_from_a_nested_model_is_reported_against_that_model(self):
        # Arrange: the server's LLM config gained `backend`; the root model is identical on both sides.
        served = {"properties": {}, "$defs": {"FakeLLMConfig": _model({"model": {}, "backend": {}})}}
        local = {"properties": {}, "$defs": {"FakeLLMConfig": _model({"model": {}})}}
        # Act
        findings, compared = ss.compare_nested_models("/v1/x", served, local, set())
        # Assert
        assert compared == ["FakeLLMConfig"]
        assert [(f.model, f.kind) for f in findings] == [("FakeLLMConfig", "missing-property")]

    def test_a_definition_embedded_in_many_schemas_is_compared_once(self):
        served = {"$defs": {"FakeLLMConfig": _model({"backend": {}})}}
        local = {"$defs": {"FakeLLMConfig": _model({})}}
        seen: set = set()
        first, _ = ss.compare_nested_models("/v1/a", served, local, seen)
        second, _ = ss.compare_nested_models("/v1/b", served, local, seen)
        assert len(first) == 1
        assert second == []

    def test_a_model_the_mirror_has_no_class_for_is_reported(self):
        served = {"$defs": {"BrandNewLLMConfig": _model({"model": {}}), "BrandNewBackend": {"enum": ["a"]}}}
        findings, _ = ss.compare_nested_models("/v1/x", served, {"$defs": {}}, set())
        assert sorted((f.model, f.kind) for f in findings) == [
            ("BrandNewBackend", "enum-class-missing"),
            ("BrandNewLLMConfig", "model-missing"),
        ]

    def test_a_class_the_local_schema_does_not_embed_is_found_in_the_mirror_package(self):
        # `GoogleLLMConfig` exists in the mirror but is absent from this local schema's `$defs`.
        served = {"$defs": {"GoogleLLMConfig": ss._local_definition("GoogleLLMConfig", {})}}
        findings, compared = ss.compare_nested_models("/v1/x", served, {"$defs": {}}, set())
        assert compared == ["GoogleLLMConfig"]
        assert findings == []

    def test_an_allow_listed_server_only_definition_is_skipped_and_recorded(self):
        served = {"$defs": {"AIMessage": _model({"content": {}})}}
        used: set = set()
        findings, _ = ss.compare_nested_models("/v1/x", served, {"$defs": {}}, set(), used)
        assert findings == []
        assert used == {"KNOWN_SERVER_ONLY_DEFS:AIMessage"}

    def test_a_module_qualified_name_resolves_to_the_class_in_the_matching_module(self):
        # Both `interactly_configs.workflow` and `interactly_configs.nodes.node` define this enum.
        cls = ss._mirror_class_for_def("agentic_workflow_framework__configs__workflow__GlobalConditionEdgeEvaluationMethod")
        assert cls is not None
        assert cls.__module__ == "interactly_configs.workflow"


class TestPublishedDefaultsAreCompared:
    def test_a_default_the_server_publishes_and_the_mirror_does_not_is_reported(self):
        served = _model({"variable_arguments": {"default": []}})
        local = _model({"variable_arguments": {}})
        findings = ss.compare_model("/v1/tools/schema/x", "ToolCfg", served, local)
        assert [(f.kind, f.detail.split(":")[0]) for f in findings] == [("default-mismatch", "`variable_arguments`")]

    def test_defaults_differing_only_in_a_minted_uuid_are_equal(self):
        served = _model({"llms_config": {"default": {"logical_id": "llm_b23a17fe-bedc-47d7-b34e-58d643aa3692"}}})
        local = _model({"llms_config": {"default": {"logical_id": "llm_b08848e9-c420-4fde-88cd-e179a5bf0e8d"}}})
        assert ss.compare_model("/v1/x", "M", served, local) == []

    def test_a_serializer_dropped_default_is_suppressed_only_for_listed_fields(self):
        served = _model({"workflow_id": {}, "other_id": {}})
        local = _model({"workflow_id": {"default": None}, "other_id": {"default": None}})
        used: set = set()
        findings = ss.compare_model("/v1/x", "M", served, local, used)
        assert [f.detail.split(":")[0] for f in findings] == ["`other_id`"]
        assert used == {"KNOWN_SERIALIZER_DROPPED_DEFAULTS:workflow_id"}

    def test_a_field_ahead_of_the_server_is_suppressed_only_when_listed(self, monkeypatch):
        monkeypatch.setattr(ss, "KNOWN_NOT_YET_DEPLOYED", {"M.new_field": "fixture"})
        served = _model({})
        local = _model({"new_field": {}, "other_new_field": {}})
        used: set = set()
        findings = ss.compare_model("/v1/x", "M", served, local, used)
        assert [(f.kind, f.detail) for f in findings] == [
            ("extra-property", "mirror has `other_new_field`, server does not")
        ]
        assert used == {"KNOWN_NOT_YET_DEPLOYED:M.new_field"}

    def test_a_listed_field_with_a_different_real_default_is_still_reported(self):
        served = _model({"workflow_id": {"default": "abc"}})
        local = _model({"workflow_id": {"default": None}})
        assert len(ss.compare_model("/v1/x", "M", served, local)) == 1


class TestToolTypesAreDiscoveredFromTheServer:
    def test_a_tool_type_the_mirror_lacks_is_unmapped_rather_than_skipped(self, monkeypatch):
        # Arrange: the server lists a type the mirror has never heard of.
        responses = {
            "/v1/tools/types": {"tool_types": ["external_api", "a_tool_type_from_the_future"]},
            "/v1/nodes/types": {"node_types": []},
            "/v1/edges/types": {"edge_types": []},
        }
        monkeypatch.setattr(ss, "get_json", lambda client, path: responses.get(path))
        # Act
        work = ss.resolve_local_models(client=None)
        # Assert
        tools = {endpoint: name for endpoint, name, _ in work if endpoint.startswith("/v1/tools/")}
        assert tools == {
            "/v1/tools/schema/external_api": "ExternalAPIToolConfig",
            "/v1/tools/schema/a_tool_type_from_the_future": "",
        }
