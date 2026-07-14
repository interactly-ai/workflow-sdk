from typing import Literal, Optional

from pydantic import ConfigDict, Field

from interactly_configs.nodes.athena.athena_credentials import AthenaCredentialsConfig
from interactly_configs.nodes.athena.athena_input import AthenaBaseRunInput
from interactly_configs.nodes.athena.athena_output import AthenaBaseRunOutput
from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeCategory,
)

class AthenaPatientsSearchNodeConfig(AthenaCredentialsConfig, BaseNodeConfig):
    type: Literal["athena_patients_search"] = Field(
        default="athena_patients_search",
        description="Type of the node. Must be 'athena_patients_search'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default=NodeCategory.ATHENA.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.EHR_INTEGRATIONS.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="Phone number of the patient to create",
        title="Patient Phone Number ex: home",
    )
    full_name: Optional[str] = Field(
        default=None,
        description="Full name of the patient to retrieve",
        title="Patient Full Name",
    )
    birthdate: Optional[str] = Field(
        default=None,
        description="Birthdate of the patient to retrieve",
        title="Patient Birthdate",
    )

    model_config = ConfigDict(
        title="Athena Patients Search Node",
    )

class AthenaPatientsSearchNodeRunInput(AthenaBaseRunInput, BaseNodeRunInput):
    type: Literal["athena_patients_search"] = Field(
        default="athena_patients_search",
        description="Discriminator field which must always be 'athena_patients_search'",
    )

class AthenaPatientsSearchNodeRunOutput(AthenaBaseRunOutput, BaseNodeRunOutput):
    type: Literal["athena_patients_search"] = Field(
        default="athena_patients_search",
        description="Discriminator field which must always be 'athena_patients_search'",
    )
