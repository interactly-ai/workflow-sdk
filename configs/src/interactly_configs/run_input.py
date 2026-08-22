"""Run input base model and workflow command enum.

The concrete ``WorkflowRunInput`` lives in ``interactly_configs.workflow_run``
(which the package re-exports); this module only provides the shared
``BaseRunInput``.
"""

from typing import Dict

from pydantic import BaseModel, Field, SecretStr


class BaseRunInput(BaseModel):
    """Base class for run input to workflows or individual nodes.

    ``secret_variables`` is separate from ``dynamic_variables`` on purpose. A team's API token used to be
    resolved into ``dynamic_variables`` alongside ``now`` and ``date``, and from there it reached — in
    clear — the execute response body, the persisted run record and the service log. No single site was
    wrong; the value was simply in the bag that all of them print.

    So credentials travel in a field that structurally cannot be emitted: ``exclude=True`` keeps it out of
    ``model_dump`` and ``model_dump_json``, ``repr=False`` keeps it out of ``repr()`` and f-strings, and
    ``SecretStr`` renders ``**********`` anywhere it is stringified, so an unanticipated path fails safe
    rather than leaking.

    **The server populates this; a client does not.** Values come from the team's global variables marked
    secret. Because ``exclude=True`` also keeps the field out of a serialised request body, anything set
    here client-side is dropped before the request is sent — it is mirrored so that this package's models
    are shaped like the server's, not because there is a reason to fill it in.
    """

    dynamic_variables: dict = Field(
        default_factory=dict,
        description=(
            "Dynamic variable values that will replace the '{{...}}' placeholders "
            "in prompts, condition strings, tool signatures, etc."
        ),
        title="Dynamic Variables",
    )
    runtime_variables: dict = Field(
        default_factory=dict,
        description=(
            "Runtime variables that will replace the '[[...]]' placeholders "
            "in prompts, condition strings, tool signatures, etc."
        ),
        title="Runtime Variables",
    )
    secret_variables: Dict[str, SecretStr] = Field(
        default_factory=dict,
        exclude=True,
        repr=False,
        description=(
            "Credential-valued variables — every team global marked is_secret, plus the system "
            "interactly_api_token. Carried apart from dynamic_variables so that the value a run passes "
            "around is NOT the value it emits: see the class docstring."
        ),
        title="Secret Variables",
    )
    miscellaneous: dict = Field(
        default_factory=dict,
        description="Miscellaneous run-input data",
        title="Miscellaneous Run Input Data",
    )
