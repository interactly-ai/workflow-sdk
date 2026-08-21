"""Tool configuration models."""

import json
import keyword
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Type, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from interactly_configs.prompt import StaticMessagesConfig

#: Which arguments a registered inbuilt tool declares, keyed by ``tool_id``.
#:
#: **Empty by default, and that is deliberate.** Upstream, this comes from an in-process registry of
#: server-side Python functions; there is nothing to read it from here and the SDK is intentionally
#: self-contained, so ``InbuiltFunctionToolConfig._check_bindings_are_declared_arguments`` skips and the
#: server remains the authority for that rule. Register a mapping to opt in — a test harness that knows
#: the signatures, or a future SDK that fetches them from the API.
#:
#: A registered empty list means "this tool accepts no arguments", which is a real answer and not the
#: same as absence. See :func:`declared_arguments_for`.
_INBUILT_ARGUMENT_PROVIDER: Dict[str, List[str]] = {}


def register_inbuilt_arguments(arguments_by_tool_id: Dict[str, List[str]]) -> None:
    """Teach this process which arguments each inbuilt tool accepts. Merges; does not replace."""
    _INBUILT_ARGUMENT_PROVIDER.update(arguments_by_tool_id)


def clear_inbuilt_arguments() -> None:
    """Forget every registered signature. For tests that must assert the offline no-op."""
    _INBUILT_ARGUMENT_PROVIDER.clear()


def declared_arguments_for(tool_id: str) -> Optional[List[str]]:
    """The arguments ``tool_id`` accepts, or ``None`` when this process does not know.

    **``None`` and ``[]`` are different answers, and collapsing them was a real defect upstream.**
    ``None`` means "no information, defer to the server"; ``[]`` means "this tool accepts nothing", which
    is the case where *every* binding is an offender and the check has the most to say. Membership in the
    provider decides which: a registered tool answers with its list, however short.
    """
    if tool_id not in _INBUILT_ARGUMENT_PROVIDER:
        return None
    return list(_INBUILT_ARGUMENT_PROVIDER[tool_id] or [])


class ToolType(str, Enum):
    """Enumeration of tool types."""

    INBUILT_FUNCTION = "inbuilt_function"
    INLINE_PYTHON = "inline_python"
    EXTERNAL_API = "external_api"
    KNOWLEDGE_BASE = "knowledge_base"

    @classmethod
    def list(cls) -> List["ToolType"]:
        return [cls.INBUILT_FUNCTION, cls.INLINE_PYTHON, cls.EXTERNAL_API, cls.KNOWLEDGE_BASE]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.list()

    @classmethod
    def get_description(cls) -> str:
        return f"Type of the tool. Must be one of: {', '.join(t.value for t in cls.list())}"

    @classmethod
    def get_type_to_config_map(cls) -> Dict["ToolType", Type["BaseToolConfig"]]:
        """Returns a mapping of tool types to their respective configuration classes."""
        return {
            cls.INBUILT_FUNCTION: InbuiltFunctionToolConfig,
            cls.INLINE_PYTHON: InlinePythonToolConfig,
            cls.EXTERNAL_API: ExternalAPIToolConfig,
            cls.KNOWLEDGE_BASE: KnowledgeBaseToolConfig,
        }


class ToolVariableSource(str, Enum):
    """Which namespace a variable-bound tool argument is read from."""

    AUTO = "auto"
    RUNTIME = "runtime"
    DYNAMIC = "dynamic"
    LITERAL = "literal"

    @classmethod
    def list(cls) -> list["ToolVariableSource"]:
        return [cls.AUTO, cls.RUNTIME, cls.DYNAMIC, cls.LITERAL]


class ToolVariableArgument(BaseModel):
    """One argument supplied to a tool by the workflow rather than by the model or the node author.

    Resolved fresh at every invocation from the variable snapshot in effect at that moment, and passed
    to the tool as a **native Python value**. That is the whole point of this model: the pre-existing
    routes for getting a variable into a tool are string interpolation into ``tool_arguments`` (which
    turns a dict into its ``repr()`` and an int into ``"41"``) and textual substitution into an inline
    tool's ``code`` (which is code injection). Neither can carry a value with its type intact.

    Bound arguments are hidden from the model's ``args_schema`` by default and override anything the
    caller supplied, so a value the workflow owns cannot be invented or contradicted by generated JSON.
    """

    argument_name: str = Field(
        description="The keyword argument name passed to the tool function.",
        title="Argument Name",
    )
    source: ToolVariableSource = Field(
        default=ToolVariableSource.AUTO,
        description=(
            "Which variable namespace to read from: 'runtime' for [[vars]], 'dynamic' for {{vars}}, "
            "'auto' to try runtime first and then dynamic, or 'literal' to use literal_value verbatim."
        ),
        title="Source",
    )
    variable_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to the value, e.g. 'patient_record', 'patient_record.dob', 'items[0].id', or a "
            "node-qualified key such as 'Collect Insurance.dob'. Required unless source is 'literal'."
        ),
        title="Variable Path",
    )
    literal_value: Optional[Any] = Field(
        default=None,
        description="Used verbatim when source is 'literal'. Lets a tool argument be pinned to a constant.",
        title="Literal Value",
    )
    default: Optional[Any] = Field(
        default=None,
        description="Value used when the variable is absent or holds None. Ignored when required is true.",
        title="Default Value",
    )
    required: bool = Field(
        default=False,
        description=(
            "When true, a missing variable fails the tool call with a named error instead of passing "
            "the default. Use for arguments the tool genuinely cannot run without."
        ),
        title="Required",
    )
    expose_to_llm: bool = Field(
        default=False,
        description=(
            "When false (the default) this argument is stripped from the args_schema the model sees, so "
            "the model is never asked for it and cannot supply it. Set true only when the model should "
            "be able to override the bound value."
        ),
        title="Expose To LLM",
    )
    override_provided_value: bool = Field(
        default=True,
        description=(
            "When true the bound value replaces anything the caller (the model, or the node's "
            "tool_arguments) supplied under the same name. When false the bound value acts as a "
            "fallback used only if the caller omitted the argument."
        ),
        title="Override Provided Value",
    )

    @model_validator(mode="after")
    def _check_binding_is_usable(self) -> "ToolVariableArgument":
        if not self.argument_name.isidentifier() or keyword.iskeyword(self.argument_name):
            raise ValueError(
                f"variable_arguments: '{self.argument_name}' is not a usable argument name. It is passed "
                f"as a keyword argument, so it must be a valid, non-reserved Python identifier."
            )

        if self.source != ToolVariableSource.LITERAL and not self.variable_path:
            raise ValueError(
                f"variable_arguments['{self.argument_name}']: variable_path is required unless source " f"is 'literal'."
            )

        # Hidden AND non-overriding means nothing can ever provide this argument: the model cannot see
        # it, so it never supplies one, so the fallback never fires. Rejected rather than accepted as a
        # no-op — a binding that is configured and can never apply is the failure mode this whole
        # feature exists to remove.
        if not self.expose_to_llm and not self.override_provided_value:
            raise ValueError(
                f"variable_arguments['{self.argument_name}']: expose_to_llm=False with "
                f"override_provided_value=False can never apply — the argument is hidden from the model, "
                f"so there is never a caller-supplied value for it to fall back behind. Set "
                f"override_provided_value=True (workflow-owned) or expose_to_llm=True (model-owned with "
                f"a workflow default)."
            )
        return self

    model_config = ConfigDict(
        title="Tool Variable Argument",
    )


class ToolResultVariableScope(str, Enum):
    """Which variable store a mapped tool result is written to."""

    THREAD = "thread"
    WORKFLOW = "workflow"

    @classmethod
    def list(cls) -> list["ToolResultVariableScope"]:
        return [cls.THREAD, cls.WORKFLOW]


class ToolResultVariableMapping(BaseModel):
    """Assigns part of a tool's return value to a named runtime variable.

    Without this, a tool's return value lands under a single name and can only be read as
    ``[[tool_result.score]]``. Mapping it lets a tool that returns a dict — which is nearly all of them —
    populate several individually-named variables that downstream prompts and conditional edges can use
    directly.
    """

    target_variable_name: str = Field(
        description=(
            "Runtime variable to write. Readable downstream as [[<name>]]. Must be a plain name: "
            "letters, digits and underscores, not starting with a digit or an underscore."
        ),
        title="Target Variable Name",
    )
    result_path: Optional[str] = Field(
        default=None,
        description=(
            "Path into the returned value, e.g. 'score', 'patient.dob' or 'rows[0].id'. "
            "Leave empty to assign the whole return value."
        ),
        title="Result Path",
    )
    scope: ToolResultVariableScope = Field(
        default=ToolResultVariableScope.THREAD,
        description=(
            "Which variable store to write to. 'thread' (the default) writes to the conversation this "
            "tool ran in, and is what almost every mapping wants. 'workflow' writes to the run's shared "
            "memory, readable as [[<name>]] from every node in every thread — use it for something "
            "established once and true for the whole run, such as a verified patient id. A thread-local "
            "variable of the same name always wins where both exist."
        ),
        title="Scope",
    )
    default: Optional[Any] = Field(
        default=None,
        description="Value written when result_path is not present in the return value.",
        title="Default Value",
    )
    required: bool = Field(
        default=False,
        description=(
            "When true, a missing result_path marks the tool call as failed and records the reason in "
            "<result_runtime_variable_name>_error, instead of writing the default."
        ),
        title="Required",
    )

    @field_validator("target_variable_name")
    @classmethod
    def _check_target_is_addressable(cls, value: str) -> str:
        """Reject a target name that cannot be read back, or that trespasses on framework naming.

        Two failure modes, neither of which raises on its own:

        *Unaddressable.* A blank name, or one containing dots, brackets or spaces, is written into the
        runtime-variable dict happily enough — ``ThreadState.update_runtime_variables`` merges whatever
        it is given — but it cannot then be resolved unambiguously. Dots are the worst case rather than
        merely untidy: ``update_runtime_variables`` already writes every variable a second and third time
        as ``<node logical_id>.<var>`` and ``<node name>.<var>``, so a target literally named
        ``patient.dob`` collides with that namespace and ``resolve_variable_path`` cannot tell which
        reading was meant.

        *Reserved.* A leading underscore is how the framework marks its own entries in the variable
        stores (``_evaluated_dynamic_variables`` and friends). ``build_result_variable_updates`` already
        refuses to write those on the ``expand_result_into_runtime_variables`` path, so permitting them
        for explicit mappings was an inconsistency in this feature rather than merely a missing check.

        The rule is deliberately the same one applied to ``ToolVariableArgument.argument_name``, and
        deliberately the strict end of the defensible range: it can be relaxed later, whereas a loose
        rule cannot be tightened without invalidating configs that were already saved.
        """
        if not value or not value.strip():
            raise ValueError("result_variable_mappings: target_variable_name must not be blank.")
        if value.startswith("_"):
            raise ValueError(
                f"result_variable_mappings: target_variable_name '{value}' starts with an underscore, "
                f"which is reserved for the framework's own variables. Choose another name."
            )
        if not value.isidentifier():
            raise ValueError(
                f"result_variable_mappings: target_variable_name '{value}' is not a plain variable name. "
                f"Use letters, digits and underscores only — a name containing dots, brackets or spaces "
                f"collides with the '<node name>.<variable>' keys the runtime already writes and cannot "
                f"be resolved unambiguously in [[...]]."
            )
        return value

    # ``_reject_unsupported_scope`` used to live here, refusing ``scope="workflow"`` because
    # ``WorkflowMemory.runtime_variables`` was not consulted by ``NodeRuntime.get_dynamic_runtime_variables``
    # — so the write existed but nothing could read it, which is worse than not offering the option. It was
    # deleted rather than relaxed once that merge landed: the read side now exists, beneath the thread
    # variables and skipping the framework's own underscore-prefixed keys. The enum value never changed,
    # so turning this on was the removal of a validator rather than a config migration, exactly as it was
    # designed to be.
    #
    # Mirrored because it is a *rejection*: leaving it here would make the SDK refuse a config the server
    # now accepts, so an SDK user would be blocked from building something the dashboard offers.

    model_config = ConfigDict(
        title="Tool Result Variable Mapping",
    )


class BaseToolConfig(BaseModel):
    """Base configuration for a tool."""

    logical_id: Optional[str] = Field(
        default_factory=lambda: "tool_" + str(uuid4()),
        description="Unique identifier for the tool",
        title="Tool ID",
    )
    side_effect: Optional[str] = Field(
        default=None,
        description=(
            "Side-effect classification used by the test-tool feature to decide whether the tool can be "
            "safely executed directly, or must be dry-run / confirmation-gated first. One of "
            "'none', 'reads', 'writes', 'sends', 'unknown'. When not set, it is inferred from the tool type."
        ),
        title="Side Effect",
    )
    tool_id: Optional[str] = Field(
        default=None,
        description=(
            "Reference to the tool already created in the Workflow System. "
            "If not provided, the tool config is assumed to be provided inline here."
        ),
        title="Attachable Tool ID",
    )
    name: Optional[str] = Field(default=None, description="Name for the tool", title="Tool Name")
    description: Optional[str] = Field(
        default=None,
        description="Human friendly description for the tool (not used by AI)",
        title="Tool Description",
    )
    category: Optional[str] = Field(
        default=None,
        description="Category for the tool. E.g math, ehr, etc",
        title="Tool Category",
    )
    signature: Optional[str] = Field(
        default=None,
        description=(
            "Docstring or signature for the tool used by AI. "
            "If provided and there is a default signature already, it will override the default signature."
        ),
        title="Tool Signature",
    )
    args_schema: Optional[dict] = Field(
        default=None,
        description=(
            "Schema for the arguments that the tool accepts. "
            "This should be a JSON schema dictionary."
        ),
        title="Tool Arguments Schema",
    )
    static_messages_config: Optional[StaticMessagesConfig] = Field(
        default=None,
        description="Static messages that an LLM node should emit while this tool is being invoked",
        title="Static Messages Configuration",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default="tool_result",
        description="Name of the runtime variable to store the result from this tool call",
        title="Result Runtime Variable Name",
    )
    ignore_content_received_during_llm_tool_call_specification: bool = Field(
        default=False,
        description=(
            "If true, any free-text content the LLM returns in the same response as a call to "
            "this tool is ignored: not emitted via AssistantResponseEvent, not added to chat "
            "history, and not added to the node's structured output. When a response contains "
            "multiple tool calls, the text is ignored only if every tool call targets a tool "
            "for which this flag is set."
        ),
        title="Ignore content received during LLM tool call specification",
    )
    timeout_seconds: Optional[int] = Field(
        default=None,
        description=(
            "Wall-clock ceiling in seconds for one invocation of this tool. Leave empty to use the "
            "platform default. Raise it for a tool that is legitimately slow (a large EHR sync, say) "
            "rather than letting it be cut off. Note: an inline-Python body that is CPU-bound with no "
            "await points cannot be interrupted - the timeout frees the conversation to continue, but "
            "the work carries on in the background."
        ),
        title="Tool Timeout (seconds)",
    )
    variable_arguments: List[ToolVariableArgument] = Field(
        default_factory=list,
        description=(
            "Arguments supplied to this tool from the workflow's runtime/dynamic variables, resolved at "
            "invocation time and passed as native Python values. Use this instead of embedding "
            "[[variables]] in an inline tool's source code: the value keeps its type, and it is passed "
            "as an argument rather than spliced into the code."
        ),
        title="Variable Arguments",
    )
    result_variable_mappings: List[ToolResultVariableMapping] = Field(
        default_factory=list,
        description=(
            "Assigns parts of this tool's return value to named runtime variables, so a tool that "
            "returns a dict can populate several variables at once."
        ),
        title="Result Variable Mappings",
    )
    expand_result_into_runtime_variables: bool = Field(
        default=False,
        description=(
            "When true and the tool returns a dict, every top-level key is also written as a runtime "
            "variable of the same name. A convenience alternative to listing every mapping explicitly; "
            "explicit result_variable_mappings win on a name collision."
        ),
        title="Expand Result Into Runtime Variables",
    )

    @model_validator(mode="after")
    def _check_variable_bindings_are_unambiguous(self) -> "BaseToolConfig":
        """Reject duplicate argument names and duplicate result targets.

        Both are silent-loss bugs otherwise: two bindings for one argument mean whichever is applied
        last wins by list order, and two mappings for one variable mean one of the tool's outputs is
        overwritten before anything can read it. Neither is ever intentional, and neither raises on its
        own.
        """
        seen_arguments = set()
        for binding in self.variable_arguments:
            if binding.argument_name in seen_arguments:
                raise ValueError(
                    f"variable_arguments declares '{binding.argument_name}' more than once. "
                    f"Each argument may be bound at most once."
                )
            seen_arguments.add(binding.argument_name)

        # The two derived keys a **tool node** writes alongside the result itself, and which conditional
        # edges branch on. Reserved here so tool data cannot occupy them.
        #
        # Scope, stated precisely because an earlier version of this comment claimed both invocation paths
        # write them and that is false: only the tool node does. The LLM tool-call path writes the result
        # name and nothing derived from it — no success flag on success, on failure, or anywhere — so on
        # that path a mapping to one of these names is just an ordinary variable with nothing to collide
        # with. The tool node also derives them from *its own* result_runtime_variable_name, which is a
        # different field from this one, so this check cannot see the name actually used there; a matching
        # validator on ToolNodeConfig covers that half, and the node's write order covers the rest.
        #
        # The base name itself is deliberately NOT reserved: pointing it at a sub-path
        # (result_path="data" -> target=the base name) is a legitimate way to make [[tool_result]] mean the
        # payload rather than the envelope.
        base_result_name = self.result_runtime_variable_name or "tool_result"
        reserved_targets = {f"{base_result_name}_success", f"{base_result_name}_error"}

        seen_targets = set()
        for mapping in self.result_variable_mappings:
            if mapping.target_variable_name in seen_targets:
                raise ValueError(
                    f"result_variable_mappings writes '{mapping.target_variable_name}' more than once. "
                    f"Each target variable may be written at most once."
                )
            if mapping.target_variable_name in reserved_targets:
                raise ValueError(
                    f"result_variable_mappings writes '{mapping.target_variable_name}', which this tool "
                    f"already writes as the outcome of the call (derived from "
                    f"result_runtime_variable_name='{base_result_name}'). Mapping onto it would replace "
                    f"the success flag or the error message with tool data, and conditional edges branch "
                    f"on those. Choose another target name."
                )
            seen_targets.add(mapping.target_variable_name)

        return self


class InbuiltFunctionToolConfig(BaseToolConfig):
    """Configuration for an inbuilt function tool registered in the tools registry."""

    type: Literal["inbuilt_function"] = Field(
        default=ToolType.INBUILT_FUNCTION.value,
        description="Type of the tool. Must be 'inbuilt_function'",
        title="Tool Type",
    )
    configurable_key: Optional[str] = Field(
        default=None,
        description=(
            "Stable key identifying which configurable inbuilt tool this is (e.g. 'call_forward'). "
            "None for plain static inbuilt references."
        ),
        title="Configurable Tool Key",
    )
    extra_config: Optional[dict] = Field(
        default=None,
        description="Tool-specific user configuration values. Schema is defined per configurable key.",
        title="Extra Configuration",
    )

    @model_validator(mode="after")
    def _check_bindings_are_declared_arguments(self) -> "InbuiltFunctionToolConfig":
        """Reject a binding naming an argument the registered function does not accept.

        **The server is the authority for this rule, and this mirror cannot be.** Upstream, the check
        compares the binding against the registered function's Pydantic ``args_schema``, read from an
        in-process registry of server-side Python functions. There is no registry here and there cannot
        be one — the SDK is deliberately self-contained.

        So this validator is a **documented no-op offline**: with no provider registered it skips, and a
        config the server will reject with a 422 constructs happily here. That is a real capability the
        mirror does not have, and it is the honest trade — the alternative is a second, drifting copy of
        23 function signatures. It is kept structurally identical to its upstream twin so that the parity
        harness sees a validator in both trees, and so a host that *does* have the argument names (a test
        harness, or a future SDK that fetches them from the API) can supply them.

        The rule it enforces when a provider is registered: LangChain validates an inbuilt tool's kwargs
        against a Pydantic ``args_schema``, so ``extra="ignore"`` discards a binding naming an undeclared
        argument — configured, resolved, logged as resolved, then dropped, with the workflow reading as
        correct while the tool runs on a default.

        One case upstream enforces that this cannot: a ``tool_id`` that is a saved-tool ObjectId, which
        needs a database read to resolve. Upstream handles that at its node routes and reports it during
        hydration; here it simply falls into the unknown-tool skip above.
        """
        if not self.variable_arguments or not self.tool_id:
            return self

        declared = declared_arguments_for(self.tool_id)
        # Absent, not empty — mirroring the same distinction upstream draws between an *absent*
        # ``args_schema`` and one declaring zero fields. `None` is "this process cannot say"; an empty
        # list is "the function accepts nothing", and every binding on it is an offender.
        if declared is None:
            # No provider, or a tool this provider does not know. Skipping is the point; see above.
            return self

        offenders = sorted({binding.argument_name for binding in self.variable_arguments} - set(declared))
        if offenders:
            raise ValueError(
                f"Inbuilt tool '{self.tool_id}': variable_arguments binds {offenders}, which the "
                f"registered function does not accept (it accepts {sorted(declared)}). Those values would "
                f"be validated away before the function saw them, so the binding would silently do "
                f"nothing. Rename the binding, or bind one of the accepted arguments."
            )
        return self

    model_config = ConfigDict(title="Inbuilt Function Tool")


class InlinePythonToolConfig(BaseToolConfig):
    """Configuration for an inline Python tool.

    The ``code`` field should contain a self-contained executable Python function::

        def add(a: float, b: float) -> float:
            return float(a + b)
    """

    type: Literal["inline_python"] = Field(
        default=ToolType.INLINE_PYTHON.value,
        description="Type of the tool. Must be 'inline_python'",
        title="Tool Type",
    )
    code: Optional[str] = Field(
        default=None,
        description=(
            "Python code to be executed by the tool. "
            "It should define a function with proper signature and descriptions for its parameters."
        ),
        title="Tool Code",
    )

    model_config = ConfigDict(title="Inline Python Tool")


class APIMethodType(str, Enum):
    """Enumeration of HTTP methods for API calls."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"

    @classmethod
    def list(cls) -> List["APIMethodType"]:
        return [cls.GET, cls.POST, cls.PUT, cls.DELETE]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.list()

    @classmethod
    def get_description(cls) -> str:
        return f"HTTP method. Must be one of: {', '.join(m.value for m in cls.list())}"


class ExternalAPIToolConfig(BaseToolConfig):
    """Configuration for an external API tool."""

    type: Literal["external_api"] = Field(
        default=ToolType.EXTERNAL_API.value,
        description="Type of the tool. Must be 'external_api'",
        title="Tool Type",
    )
    api_endpoint: Optional[str] = Field(
        default=None,
        description="The endpoint URL of the external API",
        title="API Endpoint",
    )
    api_method: Optional[APIMethodType] = Field(
        default=APIMethodType.GET,
        description="HTTP method to use for the API call (e.g., GET, POST)",
        title="API Method",
    )
    api_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers to include with the API request",
        title="API Headers",
    )
    api_body: Optional[Union[dict, str]] = Field(
        default=None,
        description="The request body payload for the API call.",
        title="API Request Body",
    )

    @model_validator(mode="after")
    def _reject_variable_arguments(self) -> "ExternalAPIToolConfig":
        """External-API tools do not support variable-bound arguments yet.

        Their arguments are substituted into the endpoint, headers and body with ``str.format``, so a
        bound ``dict`` or ``list`` means something materially different here than it does as an argument
        to a Python function. Supporting it properly needs its own design and its own tests. Until then
        this raises rather than accepting a binding and ignoring it — a config that reads as working and
        silently does nothing is the exact failure this feature was built to remove.
        """
        if self.variable_arguments:
            raise ValueError(
                "variable_arguments is not supported on external_api tools yet (their arguments are "
                "formatted into the endpoint/headers/body rather than passed to a function). Pass the "
                "value through the endpoint or body with a [[runtime]] / {{dynamic}} placeholder instead."
            )
        return self

    @field_validator("api_body", mode="before")
    @classmethod
    def parse_api_body(cls, v: dict | str | None) -> Optional[dict]:
        if isinstance(v, str):
            if not v.strip():
                return None
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"api_body must be valid JSON when provided as a string. Error: {e}") from e
        return v

    model_config = ConfigDict(title="External API Tool")


class KnowledgeBaseToolConfig(BaseToolConfig):
    """Configuration for a knowledge base tool."""

    type: Literal["knowledge_base"] = Field(
        default=ToolType.KNOWLEDGE_BASE.value,
        description="Type of the tool. Must be 'knowledge_base'",
        title="Tool Type",
    )
    target_knowledge_base_ids: List[str] = Field(
        default_factory=list,
        description="The IDs of the knowledge bases to query",
        title="Target Knowledge Base IDs",
    )
    category: Optional[str] = Field(
        default="Knowledge Base",
        description="Category for the tool.",
        title="Tool Category",
    )
    signature: Optional[str] = Field(
        default=(
            "Searches the knowledge bases given a natural language query "
            "and retrieves relevant chunks of information matching the query."
        ),
        description="Docstring or signature for the tool used by AI.",
        title="Tool Signature",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default="kb_tool_result",
        description="Name of the runtime variable to store the result from this tool call",
        title="Result Runtime Variable Name",
    )

    @model_validator(mode="after")
    def _check_bindings_reach_the_query(self) -> "KnowledgeBaseToolConfig":
        """``query`` is the only bindable argument, because it is the only one that reaches anything.

        ``KnowledgeBaseToolRuntime`` generates its own args_schema and its request builder sends exactly
        two things — ``kwargs["query"]`` and ``target_knowledge_base_ids``. Every other keyword argument
        is discarded by the runtime itself, schema or no schema. So binding ``query`` is genuinely useful
        (a deterministic KB lookup driven by a runtime variable rather than by a model) and binding
        anything else goes nowhere at all.

        ``justification`` used to be permitted here and should not have been. It is a
        reason-before-you-answer field that exists to make the *model* think before composing a query;
        nothing consumes it. It is absent from the outbound payload, the KB service reads only
        ``kb_ids``/``query``/``timeout_ms``, and repo-wide the only code that consumes a field by that name
        belongs to the unrelated conditional-edge feature. Binding it was therefore accepted, resolved,
        logged as resolved, and then dropped — the silently-inert config every validator in this feature
        exists to reject. Leaving it in the schema for the model to fill in is still correct and unchanged.
        """
        allowed = {"query"}
        offenders = sorted({b.argument_name for b in self.variable_arguments} - allowed)
        if offenders:
            raise ValueError(
                f"variable_arguments on a knowledge_base tool can only bind 'query'; {offenders} would be "
                f"discarded, because the knowledge base request carries only the query and the configured "
                f"knowledge base IDs. ('justification' is filled in by the model to explain its query; "
                f"nothing reads a bound value.)"
            )
        return self

    model_config = ConfigDict(title="Knowledge Base Tool")


class MCPServerConfig(BaseModel):
    """Configuration for an MCP (Model Context Protocol) server connection."""

    name: Optional[str] = Field(
        default=None,
        description="Display name for this MCP server connection",
        title="Server Name",
    )
    server_url: str = Field(
        description="MCP server URL (e.g. 'https://mcp.example.com/mcp')",
        title="Server URL",
    )
    api_headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="HTTP headers to include when connecting to the MCP server",
        title="API Headers",
    )

    model_config = ConfigDict(title="MCP Server Configuration")


ToolConfig = Annotated[
    InlinePythonToolConfig | InbuiltFunctionToolConfig | ExternalAPIToolConfig | KnowledgeBaseToolConfig,
    Field(discriminator="type"),
]


class ToolsConfig(BaseModel):
    tools: List[ToolConfig] = Field(
        default_factory=list,
        description="List of tool configurations",
        title="Tools Configuration",
    )

    model_config = ConfigDict(title="Tools Configuration")
