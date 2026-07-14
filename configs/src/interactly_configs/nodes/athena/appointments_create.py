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

class AthenaAppointmentsCreateNodeConfig(AthenaCredentialsConfig, BaseNodeConfig):
    type: Literal["athena_appointments_create"] = Field(
        default="athena_appointments_create",
        description="Type of the node. Must be 'athena_appointments_create'",
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

    title: Optional[str] = Field(
        default=None,
        description="Title of the appointment",
        title="Appointment Title",
    )
    patient_id: Optional[str] = Field(
        default=None,
        description="ID of the patient to create the appointment for",
        title="Patient ID",
    )
    practitioner_id: Optional[str] = Field(
        default=None,
        description="ID of the practitioner for the appointment",
        title="Practitioner ID",
    )
    start_time: Optional[str] = Field(
        default=None,
        description="Start time of the appointment",
        title="Start Time",
    )
    duration_in_minutes: Optional[int] = Field(
        default=15,
        description="Duration of the appointment in minutes",
        title="Duration in Minutes",
    )

    model_config = ConfigDict(
        title="Athena Appointments Create Node",
    )

class AthenaAppointmentsCreateNodeRunInput(AthenaBaseRunInput, BaseNodeRunInput):
    type: Literal["athena_appointments_create"] = Field(
        default="athena_appointments_create",
        description="Discriminator field which must always be 'athena_appointments_create'",
    )

class AthenaAppointmentsCreateNodeRunOutput(AthenaBaseRunOutput, BaseNodeRunOutput):
    type: Literal["athena_appointments_create"] = Field(
        default="athena_appointments_create",
        description="Discriminator field which must always be 'athena_appointments_create'",
    )
