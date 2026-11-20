"""
External jobs (an ECS task, for instance): what a node launches, what it watches, and how each one ended.

A node that starts long-running work outside the runtime pauses its thread until the work is terminal, and is
then resumed with one ``ExternalJobOutcome`` per job. Launching, watching, stopping and reading logs go through
``ports.external_jobs.ExternalJobPort``; the models here are what crosses that port.

They are provider-neutral on purpose. A provider's own reference is an opaque string and its launch parameters a
plain dict, so the framework never imports a cloud SDK and the same shapes serve any provider a job watcher
supports.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

# The longest free-text detail kept on an outcome. A provider's error text can run to pages, and an outcome is
# stored with the run's turn, so anything past this is cut rather than persisted.
MAX_OUTCOME_DETAIL_CHARS = 2000


class ExternalJobStatus(str, Enum):
    """How an external job ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INFRA_FAILED = "infra_failed"
    TIMED_OUT = "timed_out"
    STOPPED = "stopped"
    LOST = "lost"
    CANCELLED = "cancelled"
    LAUNCH_FAILED = "launch_failed"


#: Which limit a job passed when it was stopped as timed out: its running time, which excludes time the run spent
#: paused by a person, or its wall-clock time.
ExternalJobTimeoutKind = Literal["runtime", "walltime"]


class ExternalJobOutcome(BaseModel):
    """The terminal state of one external job, as delivered to the node that waited for it."""

    job_id: str = Field(min_length=1, description="The job's id within the run")
    provider: str = Field(min_length=1, description="Which job provider ran it, for example 'ecs'")
    external_ref: Optional[str] = Field(
        default=None, description="The provider's own reference for the job, for example an ECS task ARN"
    )
    status: ExternalJobStatus = Field(description="How the job ended")
    timeout_kind: Optional[ExternalJobTimeoutKind] = Field(
        default=None, description="For a job that timed out, which limit it passed; set only with that status"
    )
    attempt: int = Field(default=1, ge=1, description="Which launch attempt this outcome belongs to")
    exit_codes: Dict[str, Optional[int]] = Field(
        default_factory=dict, description="Exit code per container or step, where the provider reports one"
    )
    stop_code: Optional[str] = Field(default=None, description="The provider's stop code, if any")
    stopped_reason: Optional[str] = Field(default=None, description="The provider's stated reason for stopping")
    started_at: Optional[datetime] = Field(default=None, description="When the job started running")
    stopped_at: Optional[datetime] = Field(default=None, description="When the job stopped")
    log_location: Optional[Dict[str, str]] = Field(
        default=None, description="Where the job's logs are, for example a log group and stream"
    )
    detail: Optional[str] = Field(
        default=None,
        description=f"Free-text detail from the provider, cut to {MAX_OUTCOME_DETAIL_CHARS} characters",
    )

    @field_validator("detail")
    @classmethod
    def _cut_detail(cls, detail: Optional[str]) -> Optional[str]:
        if detail is not None and len(detail) > MAX_OUTCOME_DETAIL_CHARS:
            return detail[:MAX_OUTCOME_DETAIL_CHARS]
        return detail

    @model_validator(mode="after")
    def _timeout_kind_only_when_timed_out(self) -> "ExternalJobOutcome":
        if self.timeout_kind is not None and self.status != ExternalJobStatus.TIMED_OUT:
            raise ValueError(f"timeout_kind is set only on a timed-out job, not on one that {self.status.value}")
        return self


class ExternalJobOwnership(str, Enum):
    """Whether the run started the job."""

    #: Launched by this run. Stopped when the run ends or is cancelled, if its launch asked for that.
    OWNED = "owned"
    #: Started by something else and only watched. Stopped only by an explicit stop, never by the run ending.
    ADOPTED = "adopted"


class ExternalJobPhase(str, Enum):
    """Where a job is in its life, as last observed."""

    #: Accepted by the provider, not running yet.
    PENDING = "pending"
    RUNNING = "running"
    #: Asked to stop, or stopping on its own, and not terminal yet.
    STOPPING = "stopping"
    #: Ended. The job's ``ExternalJobOutcome`` says how.
    TERMINAL = "terminal"


class ExternalJobRef(BaseModel):
    """A job the run knows about, as wake conditions and later nodes refer to it."""

    job_id: str = Field(min_length=1, description="The job's id within the run; what an external-job wake names")
    provider: str = Field(min_length=1, description="Which job provider runs it, for example 'ecs'")
    external_ref: str = Field(min_length=1, description="The provider's own reference, for example an ECS task ARN")
    ownership: ExternalJobOwnership = Field(description="Whether the run launched the job or only watches it")


class ExternalJobSpec(BaseModel):
    """What to launch, and for which run and node."""

    run_id: str = Field(min_length=1, description="The run launching the job")
    thread_id: str = Field(min_length=1, description="The thread whose node launches it")
    node_logical_id: str = Field(min_length=1, description="The node launching it")
    provider: str = Field(min_length=1, description="Which job provider to launch through")
    connection_id: Optional[str] = Field(
        default=None, description="The integration connection the provider launches through, if it needs one"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Provider-specific launch parameters, validated by the provider. A provider may store them with the "
            "job, so they must never hold a resolved secret value."
        ),
    )
    secret_params: Dict[str, SecretStr] = Field(
        default_factory=dict,
        exclude=True,
        repr=False,
        description=(
            "Values of the secret team variables that {{NAME}} placeholders in params name. Only the provider reads "
            "them, inside the call that needs them; they are left out of every dump and repr, so they never reach "
            "the job's stored row, a log line or a run document."
        ),
    )
    stop_on_run_end: bool = Field(default=True, description="Stop the job if the run ends or is cancelled first")
    max_runtime_seconds: Optional[int] = Field(
        default=None, ge=1, description="Running time after which the job is stopped as timed out"
    )
    walltime_deadline_at: Optional[datetime] = Field(
        default=None, description="Wall-clock time after which the job is stopped as timed out"
    )


class ExternalJobState(BaseModel):
    """A job's state as last observed. ``outcome`` is set exactly when the job is terminal."""

    ref: ExternalJobRef = Field(description="The job")
    phase: ExternalJobPhase = Field(description="Where the job is in its life")
    provider_status: Optional[str] = Field(
        default=None, description="The provider's own status word, for example ECS's lastStatus"
    )
    outcome: Optional[ExternalJobOutcome] = Field(default=None, description="How the job ended, once terminal")

    @model_validator(mode="after")
    def _outcome_only_when_terminal(self) -> "ExternalJobState":
        terminal = self.phase == ExternalJobPhase.TERMINAL
        if terminal and self.outcome is None:
            raise ValueError("A terminal job state carries its outcome")
        if not terminal and self.outcome is not None:
            raise ValueError(f"A {self.phase.value} job has no outcome yet")
        if self.outcome is not None and self.outcome.job_id != self.ref.job_id:
            raise ValueError(f"Outcome for job {self.outcome.job_id} given for job {self.ref.job_id}")
        return self


class ExternalJobLogs(BaseModel):
    """Lines read from a job's logs."""

    lines: List[str] = Field(default_factory=list, description="The lines read, oldest first")
    truncated: bool = Field(default=False, description="Whether more lines matched than were returned")
    timestamps: List[datetime] = Field(
        default_factory=list,
        description="When each line was logged, in the order of ``lines``; empty where the provider doesn't say",
    )
