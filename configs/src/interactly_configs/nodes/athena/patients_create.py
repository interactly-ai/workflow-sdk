from enum import Enum
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


class Gender(str, Enum):
    Empty: str = ""
    Female: str = "Female"
    Male: str = "Male"
    NonBinaryGenderIdentity: str = "Non-binary gender identity"
    Other: str = "Additional gender category or other"
    ChooseNotToDisclose: str = "Choose not to disclose"
    Genderqueer: str = "Genderqueer (neither exclusively male nor female)"
    Unknown: str = "Unknown"

class AthenaPatientsCreateNodeConfig(AthenaCredentialsConfig, BaseNodeConfig):
    type: Literal["athena_patients_create"] = Field(
        default="athena_patients_create",
        description="Type of the node. Must be 'athena_patients_create'",
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
    first_name: Optional[str] = Field(
        default=None,
        description="First name of the patient to create",
        title="Patient First Name",
    )
    last_name: Optional[str] = Field(
        default=None,
        description="Last name of the patient to create",
        title="Patient Last Name",
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="Phone number of the patient to create",
        title="Patient Phone Number ex: home",
    )
    birthdate: Optional[str] = Field(
        default=None,
        description="Birthdate of the patient to retrieve",
        title="Patient Birthdate",
    )
    gender: Optional[Gender] = Field(
        default=Gender.Male.value,
        description="Gender of the patient to create",
        title="Patient Gender",
    )
    email: Optional[str] = Field(
        default=None,
        description="Email of the patient to create",
        title="Patient Email",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about the patient to create",
        title="Patient Notes",
    )
    mobile_number: Optional[str] = Field(
        default=None,
        description="Mobile number of the patient to create",
        title="Patient Mobile Number ex: mobile",
    )

    model_config = ConfigDict(
        title="Athena Patients Create Node",
    )

class AthenaPatientsCreateNodeRunInput(AthenaBaseRunInput, BaseNodeRunInput):
    type: Literal["athena_patients_create"] = Field(
        default="athena_patients_create",
        description="Discriminator field which must always be 'athena_patients_create'",
    )

class AthenaPatientsCreateNodeRunOutput(AthenaBaseRunOutput, BaseNodeRunOutput):
    type: Literal["athena_patients_create"] = Field(
        default="athena_patients_create",
        description="Discriminator field which must always be 'athena_patients_create'",
    )
