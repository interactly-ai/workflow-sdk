
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class StartEndTimings(BaseModel):
    start: str = Field(..., description="Start time in HH:MM format", title="Start Time")
    end: str = Field(..., description="End time in HH:MM format", title="End Time")

class WorkingHours(BaseModel):
    monday: StartEndTimings = Field(..., description="Working hours for Monday")
    tuesday: StartEndTimings = Field(..., description="Working hours for Tuesday")
    wednesday: StartEndTimings = Field(..., description="Working hours for Wednesday")
    thursday: StartEndTimings = Field(..., description="Working hours for Thursday")
    friday: StartEndTimings = Field(..., description="Working hours for Friday")
    saturday: StartEndTimings = Field(..., description="Working hours for Saturday")
    sunday: StartEndTimings = Field(..., description="Working hours for Sunday")

class UseCase(str, Enum):
    APPOINTMENT_SCHEDULING = "appointment_scheduling"
    APPOINTMENT_CANCELLATION = "appointment_cancellation"
    APPOINTMENT_RESCHEDULING = "appointment_rescheduling"
    APPOINTMENT_SCHEDULING_WITH_WAITLIST = "appointment_scheduling_with_waitlist"
    MEDICATION_REFILL = "medication_refill"
    INVOICE_BILLING = "invoice_billing"

class AthenaCredentialsConfig(BaseModel):
    source_id: Optional[str] = Field(
        default=None,
        description="Source ID of the node",
        title="Source ID",
    )
    department_id: Optional[int] = Field(
        default=None,
        description="Department ID of the node",
        title="Department ID",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for the node",
        title="API Key",
    )
    timezone: Optional[str] = Field(
        default="America/New_York",
        description="Timezone in IANA format ex: 'America/New_York'",
        title="Timezone",
    )
    reminders: Optional[bool] = Field(
        default=False,
        description="Whether to send reminders for the node",
        title="Reminders",
    )
    slotfill_outreach: Optional[bool] = Field(
        default=False,
        description="Whether to enable slot fill outreach for the node",
        title="Slot Fill Outreach",
    )
    working_hours: Optional[WorkingHours] = Field(
        default=None,
        description="Working hours for the node",
        title="Working Hours",
    )
    use_cases: List[UseCase] = Field(
        default_factory=list,
        description="Use cases for the node",
        title="Use Cases",
    )
