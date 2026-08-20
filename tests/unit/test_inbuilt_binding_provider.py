"""The mirrored inbuilt-binding check, and the fact that it is a no-op here by design.

Upstream, `InbuiltFunctionToolConfig` rejects a `variable_arguments` binding that names an argument the
registered function does not declare — read from an in-process registry of server-side Python functions.
There is no such registry here and there cannot be one: the SDK is deliberately self-contained
(`test_self_contained.py`), and a hand-maintained copy of 23 function signatures would drift into being
wrong in a way nothing would catch.

So the mirror carries the same validator over an injectable provider that is empty by default. Two
things need pinning, and they pull in opposite directions:

* **offline it must not reject** — an SDK that refused a config the server accepts would be worse than
  one that defers, because the author has no way to override it;
* **given signatures it must reject exactly as the server does** — otherwise the provider is decoration.

The gap this leaves is real and is the point of the docstring on the validator: a config can pass here
and be rejected by `POST /workflows` with a 422. The server is the authority.
"""

import pytest
from pydantic import ValidationError

from interactly_configs.tool import (
    InbuiltFunctionToolConfig,
    ToolVariableArgument,
    clear_inbuilt_arguments,
    declared_arguments_for,
    register_inbuilt_arguments,
)

SMS_TOOL_ID = "communication_send_sms_3f5b2c1e-4d3a-4e2b-9f7a-2c6e8f4b9a1d"


@pytest.fixture(autouse=True)
def _no_registered_signatures():
    """Every test states its own provider contents; none inherits another's."""
    clear_inbuilt_arguments()
    yield
    clear_inbuilt_arguments()


def _config(argument_name: str, **overrides) -> InbuiltFunctionToolConfig:
    defaults = dict(
        logical_id="tool_sms",
        tool_id=SMS_TOOL_ID,
        variable_arguments=[
            ToolVariableArgument(argument_name=argument_name, variable_path="patient.phone", expose_to_llm=False)
        ],
    )
    defaults.update(overrides)
    return InbuiltFunctionToolConfig(**defaults)


class TestOfflineItDefersRatherThanRejecting:
    def test_an_undeclared_argument_is_accepted_with_no_provider(self):
        # Not a bug. With nothing to compare against, refusing would block a config the server accepts
        # and give the author no way around it.
        assert _config("recipient").variable_arguments[0].argument_name == "recipient"

    def test_the_provider_reports_no_knowledge_rather_than_no_arguments(self):
        """`None`, not `[]`. Collapsing the two was a real defect upstream: an empty list is a real
        answer meaning "this tool accepts nothing", and every binding on such a tool is an offender."""
        assert declared_arguments_for(SMS_TOOL_ID) is None

    def test_a_tool_the_provider_does_not_know_is_skipped(self):
        register_inbuilt_arguments({"some_other_tool": ["a", "b"]})

        assert _config("recipient", tool_id=SMS_TOOL_ID)


class TestWithSignaturesItMatchesTheServer:
    def test_an_undeclared_argument_is_rejected(self):
        register_inbuilt_arguments({SMS_TOOL_ID: ["message", "phone_number"]})

        with pytest.raises(ValidationError, match="does not accept"):
            _config("recipient")

    def test_the_message_names_the_offender_and_the_accepted_set(self):
        # Word-for-word the server's message, so an author who hits it in both places reads one thing.
        register_inbuilt_arguments({SMS_TOOL_ID: ["message", "phone_number"]})

        with pytest.raises(ValidationError) as excinfo:
            _config("recipient")

        message = str(excinfo.value)
        assert "recipient" in message
        assert "phone_number" in message
        assert "silently do nothing" in message

    def test_a_declared_argument_is_accepted(self):
        register_inbuilt_arguments({SMS_TOOL_ID: ["message", "phone_number"]})

        assert _config("phone_number")

    def test_registering_merges_rather_than_replaces(self):
        register_inbuilt_arguments({SMS_TOOL_ID: ["phone_number"]})
        register_inbuilt_arguments({"another_tool": ["x"]})

        assert declared_arguments_for(SMS_TOOL_ID) == ["phone_number"]
        assert declared_arguments_for("another_tool") == ["x"]


class TestAZeroArgumentToolAcceptsNothing:
    """The distinction the mirror was missing, and which upstream's F2 fix drew.

    A registered empty list says the function takes no arguments. That is the case where the check has
    the most to say — every binding is invalid — and falsiness swallowed exactly it, so a binding on a
    zero-argument tool was accepted by both trees.
    """

    def test_a_known_zero_argument_tool_rejects_every_binding(self):
        register_inbuilt_arguments({"zero_argument_tool": []})

        with pytest.raises(ValidationError) as excinfo:
            _config("anything", tool_id="zero_argument_tool")

        message = str(excinfo.value)
        assert "anything" in message
        # The accepted set is empty, and saying so is the whole message: there is nothing to bind.
        assert "[]" in message

    def test_it_is_distinguishable_from_an_unknown_tool(self):
        register_inbuilt_arguments({"zero_argument_tool": []})

        assert declared_arguments_for("zero_argument_tool") == []
        assert declared_arguments_for("never_registered") is None
        # And the unknown one still constructs, because the mirror has nothing to say about it.
        assert _config("anything", tool_id="never_registered")

    def test_a_valid_config_survives_a_round_trip(self):
        """The read path: a validator here fires on load as well as construction."""
        register_inbuilt_arguments({SMS_TOOL_ID: ["message", "phone_number"]})
        original = _config("phone_number")

        assert InbuiltFunctionToolConfig.model_validate(original.model_dump()) == original


class TestWhatItSkipsRegardless:
    def test_no_bindings(self):
        register_inbuilt_arguments({SMS_TOOL_ID: ["message"]})

        assert InbuiltFunctionToolConfig(logical_id="t", tool_id=SMS_TOOL_ID).variable_arguments == []

    def test_no_tool_id(self):
        register_inbuilt_arguments({SMS_TOOL_ID: ["message"]})

        assert InbuiltFunctionToolConfig(
            logical_id="t",
            variable_arguments=[
                ToolVariableArgument(argument_name="anything", variable_path="p", expose_to_llm=False)
            ],
        ).tool_id is None
