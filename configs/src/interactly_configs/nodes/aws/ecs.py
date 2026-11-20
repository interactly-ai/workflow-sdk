"""
The ECS nodes' configs: what task to run (the launch fields), how to wait for it (the wait fields), what counts as its
success (the success fields), and which tasks a node reads or stops (by ARN).

The launch fields become the job's launch parameters (``ecs_launch_params``), which workflow-service's ECS provider
validates and turns into a RunTask call. Their names match the provider's parameters one for one. Values are filled in
from the run's variables when the node runs, except ``{{NAME}}`` placeholders in environment values that name a secret
team variable: those are left for the provider, which puts the secret in only in the request it sends.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from interactly_configs.nodes.aws.base import BaseAwsNodeConfig
from interactly_configs.nodes.node import BaseNodeRunInput, BaseNodeRunOutput
from interactly_configs.pauses import PausableNodeConfig

#: The longest a task may run, and its longest wall-clock budget, including time the run spends paused.
MAX_RUNTIME_SECONDS = 24 * 3600
MAX_WALLTIME_DAYS = 30

#: The longest a launch may keep retrying when ECS is busy or out of capacity.
MAX_LAUNCH_RETRY_SECONDS = 300

#: The most tasks one node reads or stops: what one DescribeTasks call takes.
MAX_TASK_ARNS = 100

#: The longest a Wait for ECS tasks node waits, in days: a pause's own limit.
MAX_WAIT_DAYS = 30

#: The most log lines one Get ECS task logs node reads, and how long each line may be.
MAX_LOG_LINES = 1000
MAX_LOG_LINE_CHARS = 1000


class EcsNetworkConfig(BaseModel):
    """The task's awsvpc networking."""

    subnets: List[str] = Field(min_length=1, description="Subnet ids", title="Subnets")
    security_groups: List[str] = Field(default_factory=list, description="Security group ids", title="Security Groups")
    assign_public_ip: bool = Field(default=False, description="Give the task a public IP", title="Assign Public IP")


class EcsCapacityProviderConfig(BaseModel):
    """One entry of a capacity provider strategy."""

    capacity_provider: str = Field(min_length=1, description="The capacity provider's name, such as FARGATE_SPOT")
    weight: int = Field(default=0, ge=0, le=1000)
    base: int = Field(default=0, ge=0, le=100000)


class EcsContainerOverrideConfig(BaseModel):
    """What one container runs differently from its task definition."""

    name: str = Field(min_length=1, description="The container's name in the task definition")
    command: Optional[List[str]] = Field(
        default=None, description="The command to run instead, one argument per item. May use variables."
    )
    environment: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Environment variables to set. Values may use variables; '{{NAME}}' naming a secret team variable is "
            "filled in only in the request sent to AWS."
        ),
    )
    cpu: Optional[int] = Field(default=None, ge=0, description="CPU units for the container", title="CPU")
    memory: Optional[int] = Field(
        default=None, ge=1, description="Memory for the container, in MiB", title="Memory (MiB)"
    )


class EcsTaskOverrideConfig(BaseModel):
    """The task's size, when it should differ from its task definition."""

    cpu: Optional[str] = Field(default=None, description="Task CPU, such as '1024'", title="CPU")
    memory: Optional[str] = Field(default=None, description="Task memory, in MiB, such as '2048'", title="Memory (MiB)")
    ephemeral_storage_gib: Optional[int] = Field(
        default=None, ge=21, le=200, description="Ephemeral storage, in GiB", title="Ephemeral Storage (GiB)"
    )


class EcsTaskOutcome(BaseModel):
    """One task as a node's end event reports it, so that a run's view can show what the node found or did."""

    task_arn: str = Field(description="The task's ARN")
    status: Optional[str] = Field(
        default=None, description="How the task went once it stopped: succeeded, failed, cancelled or timed_out"
    )
    last_status: Optional[str] = Field(default=None, description="ECS's last status for the task while it runs")
    exit_code: Optional[int] = Field(default=None, description="The exit code that decided the task's status")
    result: Optional[str] = Field(
        default=None, description="What a Stop ECS task node did: stop_requested, already_ended or not_stopped"
    )
    error: Optional[str] = Field(default=None, description="Why the node couldn't read or act on the task")


class EcsLaunchRetryConfig(BaseModel):
    """How long a launch keeps retrying when ECS is busy or out of capacity."""

    max_attempts: int = Field(default=5, ge=1, le=10)
    max_total_seconds: int = Field(
        default=MAX_LAUNCH_RETRY_SECONDS, ge=1, le=MAX_LAUNCH_RETRY_SECONDS, title="Max Total Time (seconds)"
    )


class EcsLaunchFields(BaseModel):
    """The task to run."""

    task_definition: Optional[str] = Field(
        default=None,
        description=(
            "The task definition: a family, family:revision (recommended, for repeatable runs) or its ARN. Its "
            "family must be on the connection's allowlist. May use variables."
        ),
        title="Task Definition",
    )
    launch_type: Optional[Literal["FARGATE", "EC2", "EXTERNAL"]] = Field(
        default=None,
        description="FARGATE unless set, or unless a capacity provider strategy is given instead.",
        title="Launch Type",
    )
    capacity_provider_strategy: List[EcsCapacityProviderConfig] = Field(
        default_factory=list,
        description="Capacity providers to place the task with, instead of a launch type.",
        title="Capacity Provider Strategy",
    )
    network: Optional[EcsNetworkConfig] = Field(
        default=None,
        description="Subnets, security groups and public IP. Defaults to the connection's default network.",
        title="Network",
    )
    container_overrides: List[EcsContainerOverrideConfig] = Field(
        default_factory=list,
        description=(
            "Per container: a command and environment variables to use instead of the task definition's. The "
            "connection may restrict which environment variables can be set, and whether commands can be."
        ),
        title="Container Overrides",
    )
    task_overrides: Optional[EcsTaskOverrideConfig] = Field(
        default=None,
        description="Task CPU, memory and ephemeral storage, when they should differ from the task definition.",
        title="Task Overrides",
    )
    tags: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Extra tags for the task. Values may use variables. The 'interactly:' and 'aws:' prefixes are reserved; "
            "the run's, team's and job's ids are added when the connection allows tagging."
        ),
        title="Tags",
    )
    platform_version: Optional[str] = Field(
        default=None,
        description="The Fargate platform version, such as '1.4.0'. AWS's latest when unset.",
        title="Platform Version",
    )
    enable_execute_command: bool = Field(
        default=False,
        description="Allow ECS Exec into the task's containers.",
        title="Enable Execute Command",
    )
    launch_retry: EcsLaunchRetryConfig = Field(
        default_factory=EcsLaunchRetryConfig,
        description="How long to keep trying when ECS is busy or out of capacity: at most 10 attempts and 300 s.",
        title="Launch Retry",
    )

    @field_validator("network", mode="before")
    @classmethod
    def _untouched_network_is_unset(cls, value: Any) -> Any:
        """
        A network with no subnets, no security groups and no public IP is the form's untouched Network section, which
        the workflow editors send as ``{"assign_public_ip": false}``. It means no network of the node's own, so the
        connection's default applies. A network with anything else set but no subnets is still refused for them.
        """
        settings = ("subnets", "security_groups", "assign_public_ip")
        if isinstance(value, dict) and not any(value.get(key) for key in settings):
            return None
        return value

    @field_validator("task_overrides", mode="before")
    @classmethod
    def _empty_task_overrides_are_unset(cls, value: Any) -> Any:
        """
        The form's untouched Task Overrides section arrives with every value empty: no overrides. Keys the form adds for
        itself start with two underscores and don't count.
        """
        if not isinstance(value, dict):
            return value
        if all(item in (None, "") for key, item in value.items() if not key.startswith("__")):
            return None
        return value

    @model_validator(mode="after")
    def _one_way_to_place(self) -> "EcsLaunchFields":
        if self.launch_type and self.capacity_provider_strategy:
            raise ValueError("Set launch_type or capacity_provider_strategy, not both")
        return self


class EcsSuccessFields(BaseModel):
    """What counts as a task's success."""

    primary_container: Optional[str] = Field(
        default=None,
        description=(
            "The container whose exit code decides success. When unset, every container that reported an exit code "
            "must have exited with one of the success codes, so set it for a task with a sidecar that exits non-zero "
            "when the task stops."
        ),
        title="Primary Container",
    )
    success_exit_codes: List[int] = Field(
        default_factory=lambda: [0],
        min_length=1,
        description="The exit codes that count as success.",
        title="Success Exit Codes",
    )


class EcsWaitFields(EcsSuccessFields):
    """How long the task may take, what counts as success, and when to try again."""

    max_runtime_seconds: int = Field(
        default=12 * 3600,
        ge=1,
        le=MAX_RUNTIME_SECONDS,
        description=(
            "How long the task may run, in seconds, not counting time the run spends paused by a person: at most 24 "
            "hours. A task still running then is stopped, and the node reports it timed out."
        ),
        title="Max Running Time (seconds)",
    )
    max_walltime_days: int = Field(
        default=7,
        ge=1,
        le=MAX_WALLTIME_DAYS,
        description=(
            "The task's wall-clock budget, in days, pauses included, counted from its first launch: at most 30. A "
            "task still running then is stopped, and the node reports it timed out."
        ),
        title="Max Wall-Clock Time (days)",
    )
    retry_on_infra_failure: int = Field(
        default=1,
        ge=0,
        le=5,
        description=(
            "How many times to launch the task again when it never ran properly (an image that couldn't be pulled, "
            "capacity taken back, and the like)."
        ),
        title="Retries After An Infrastructure Failure",
    )
    retry_on_task_failure: int = Field(
        default=0,
        ge=0,
        le=5,
        description="How many times to launch the task again when it exited with a failing code.",
        title="Retries After A Failed Exit",
    )
    stop_on_run_end: bool = Field(
        default=True,
        description="Stop the task if the run ends or is cancelled while it runs. Pausing the run never stops it.",
        title="Stop With The Run",
    )


class RunEcsTaskNodeConfig(PausableNodeConfig, EcsWaitFields, EcsLaunchFields, BaseAwsNodeConfig):
    """
    Runs an ECS task and waits for it to stop, then routes on how it ended. The run pauses while the task runs, so the
    node works in scheduled runs and re-runs; editor runs and voice calls route on an error without launching.
    """

    type: Literal["aws_ecs_run_task"] = Field(
        default="aws_ecs_run_task", description="Type of the node. Must be 'aws_ecs_run_task'"
    )


class RunEcsTaskNodeRunInput(BaseNodeRunInput):
    type: Literal["aws_ecs_run_task"] = Field(
        default="aws_ecs_run_task", description="Discriminator field which must always be 'aws_ecs_run_task'"
    )


class RunEcsTaskNodeRunOutput(BaseNodeRunOutput):
    type: Literal["aws_ecs_run_task"] = Field(
        default="aws_ecs_run_task", description="Discriminator field which must always be 'aws_ecs_run_task'"
    )
    success: bool = Field(default=False, description="Whether the task succeeded")
    error_message: Optional[str] = Field(default=None, description="Why it did not, when it did not")
    task_arn: Optional[str] = Field(default=None, description="The task it ran, once ECS started one")
    status: Optional[str] = Field(default=None, description="How the task went: succeeded, failed, cancelled, …")
    exit_code: Optional[int] = Field(default=None, description="The exit code that decided the task's status")


class EcsByArnFields(BaseModel):
    """For a node naming tasks by ARN: the ARN says where each task is, so region and cluster are hidden."""

    region: Optional[str] = Field(
        default=None,
        description="Taken from each task's ARN.",
        title="Region",
    )
    cluster: Optional[str] = Field(
        default=None,
        description="Taken from each task's ARN.",
        title="Cluster",
    )


class EcsTaskArnsFields(EcsByArnFields):
    """The tasks a node reads, stops or waits for, by ARN."""

    task_arns: List[str] = Field(
        default_factory=list,
        description=(
            "The tasks, by ARN in the format that names the cluster: "
            "arn:aws:ecs:<region>:<account>:task/<cluster>/<task id>. Each entry is an ARN, or a variable holding one "
            f"or a list of them, such as [[start_task_task_arn]]; at most {MAX_TASK_ARNS} tasks in all. The cluster "
            "must be on the connection's allowlist."
        ),
        title="Task ARNs",
    )


class StartEcsTaskNodeConfig(PausableNodeConfig, EcsLaunchFields, BaseAwsNodeConfig):
    """
    Starts an ECS task and finishes as soon as ECS accepts it, without waiting for it to stop. Like Run ECS task, it
    works in scheduled runs and re-runs; editor runs and voice calls route on an error without launching.
    """

    type: Literal["aws_ecs_start_task"] = Field(
        default="aws_ecs_start_task", description="Type of the node. Must be 'aws_ecs_start_task'"
    )
    max_runtime_seconds: int = Field(
        default=12 * 3600,
        ge=1,
        le=MAX_RUNTIME_SECONDS,
        description=(
            "How long the task may run, in seconds, not counting time the run spends paused by a person: at most 24 "
            "hours. A task still running then is stopped, whether or not the run is still going."
        ),
        title="Max Running Time (seconds)",
    )
    max_walltime_days: int = Field(
        default=7,
        ge=1,
        le=MAX_WALLTIME_DAYS,
        description=(
            "The task's wall-clock budget, in days, pauses included, counted from its launch: at most 30. A task "
            "still running then is stopped, whether or not the run is still going."
        ),
        title="Max Wall-Clock Time (days)",
    )
    stop_on_run_end: bool = Field(
        default=True,
        description=(
            "Stop the task when the run ends or is cancelled. Leave it on when a later node of this run stops the task "
            "or waits for it; turn it off to leave the task running after the run (fire and forget), within its time "
            "limits. Pausing the run never stops it."
        ),
        title="Stop With The Run",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Base name for the variables this node writes: '<name>' (the task: its ARN, id, job id, cluster and ECS "
            "status), '<name>_success', '<name>_error' and '<name>_task_arn'. Defaults to the node's name in "
            "snake_case."
        ),
        title="Output Variable Name",
    )


class StartEcsTaskNodeRunInput(BaseNodeRunInput):
    type: Literal["aws_ecs_start_task"] = Field(
        default="aws_ecs_start_task", description="Discriminator field which must always be 'aws_ecs_start_task'"
    )


class StartEcsTaskNodeRunOutput(BaseNodeRunOutput):
    type: Literal["aws_ecs_start_task"] = Field(
        default="aws_ecs_start_task", description="Discriminator field which must always be 'aws_ecs_start_task'"
    )
    success: bool = Field(default=False, description="Whether ECS accepted the task")
    error_message: Optional[str] = Field(default=None, description="Why it did not, when it did not")
    task_arn: Optional[str] = Field(default=None, description="The task ECS started")


class GetEcsTaskStatusNodeConfig(EcsSuccessFields, EcsTaskArnsFields, BaseAwsNodeConfig):
    """
    Reads the state of ECS tasks named by ARN, as last observed, without waiting; a task that has stopped is judged by
    the node's primary container and success exit codes. Works in scheduled runs and re-runs; editor runs and voice
    calls route on an error.
    """

    type: Literal["aws_ecs_get_task_status"] = Field(
        default="aws_ecs_get_task_status", description="Type of the node. Must be 'aws_ecs_get_task_status'"
    )
    result_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Base name for the variables this node writes: '<name>' (one entry per task), '<name>_success' (every "
            "task was read), '<name>_error', '<name>_all_stopped' and '<name>_any_failed'. Defaults to the node's name "
            "in snake_case."
        ),
        title="Output Variable Name",
    )


class GetEcsTaskStatusNodeRunInput(BaseNodeRunInput):
    type: Literal["aws_ecs_get_task_status"] = Field(
        default="aws_ecs_get_task_status",
        description="Discriminator field which must always be 'aws_ecs_get_task_status'",
    )


class GetEcsTaskStatusNodeRunOutput(BaseNodeRunOutput):
    type: Literal["aws_ecs_get_task_status"] = Field(
        default="aws_ecs_get_task_status",
        description="Discriminator field which must always be 'aws_ecs_get_task_status'",
    )
    success: bool = Field(default=False, description="Whether every task was read")
    error_message: Optional[str] = Field(default=None, description="Why not, when not")
    tasks: List[EcsTaskOutcome] = Field(default_factory=list, description="Each task the node named, as it found it")


class StopEcsTaskNodeConfig(EcsTaskArnsFields, BaseAwsNodeConfig):
    """
    Asks ECS to stop tasks named by ARN, without waiting for them to stop. Works in scheduled runs and re-runs; editor
    runs and voice calls route on an error.
    """

    type: Literal["aws_ecs_stop_task"] = Field(
        default="aws_ecs_stop_task", description="Type of the node. Must be 'aws_ecs_stop_task'"
    )
    reason: Optional[str] = Field(
        default=None,
        description=(
            "Why the tasks are stopped, which ECS records as each one's stopped reason. May use variables. Defaults to "
            "'Stopped by workflow node <name>'."
        ),
        title="Reason",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Base name for the variables this node writes: '<name>' (one entry per task), '<name>_success' (every "
            "task was asked to stop or had already stopped) and '<name>_error'. Defaults to the node's name in "
            "snake_case."
        ),
        title="Output Variable Name",
    )


class StopEcsTaskNodeRunInput(BaseNodeRunInput):
    type: Literal["aws_ecs_stop_task"] = Field(
        default="aws_ecs_stop_task", description="Discriminator field which must always be 'aws_ecs_stop_task'"
    )


class StopEcsTaskNodeRunOutput(BaseNodeRunOutput):
    type: Literal["aws_ecs_stop_task"] = Field(
        default="aws_ecs_stop_task", description="Discriminator field which must always be 'aws_ecs_stop_task'"
    )
    success: bool = Field(default=False, description="Whether every task was asked to stop or had already stopped")
    error_message: Optional[str] = Field(default=None, description="Why not, when not")
    tasks: List[EcsTaskOutcome] = Field(default_factory=list, description="Each task the node named, as it found it")


class WaitForEcsTasksNodeConfig(PausableNodeConfig, EcsSuccessFields, EcsTaskArnsFields, BaseAwsNodeConfig):
    """
    Waits until ECS tasks named by ARN have stopped (all of them, or the first), then routes on how they went. The run
    pauses while it waits, so the node works in scheduled runs and re-runs; editor runs and voice calls route on an
    error.
    """

    type: Literal["aws_ecs_wait_for_tasks"] = Field(
        default="aws_ecs_wait_for_tasks", description="Type of the node. Must be 'aws_ecs_wait_for_tasks'"
    )
    mode: Literal["all", "any"] = Field(
        default="all",
        description="Wait until every task has stopped (all), or until the first one has (any).",
        title="Wait For",
    )
    on_any_satisfied: Literal["leave_running", "stop_others"] = Field(
        default="leave_running",
        description=(
            "With 'any': whether to stop the tasks still running once one has stopped. Only tasks this run started "
            "are stopped; a task it didn't start is stopped only by a Stop ECS task node."
        ),
        title="When One Has Stopped",
    )
    wait_timeout_seconds: int = Field(
        default=7 * 86400,
        ge=1,
        le=MAX_WAIT_DAYS * 86400,
        description=(
            "How long to wait, in seconds: 604800 (7 days) unless set, and at most 2592000 (30 days). An hour is "
            "3600 and a day 86400. Then the node routes on with the tasks as they are, and '<name>_timed_out' true."
        ),
        title="Wait Timeout (seconds)",
    )
    stop_on_wait_timeout: bool = Field(
        default=False,
        description=(
            "Stop the tasks still running when the wait times out. Only tasks this run started are stopped; a task "
            "it didn't start is stopped only by a Stop ECS task node."
        ),
        title="Stop On Timeout",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Base name for the variables this node writes: '<name>' (one entry per task), '<name>_success' (every "
            "task succeeded, or with 'any' one did), '<name>_error', '<name>_timed_out' and "
            "'<name>_failed_task_arns'. Defaults to the node's name in snake_case."
        ),
        title="Output Variable Name",
    )


class WaitForEcsTasksNodeRunInput(BaseNodeRunInput):
    type: Literal["aws_ecs_wait_for_tasks"] = Field(
        default="aws_ecs_wait_for_tasks",
        description="Discriminator field which must always be 'aws_ecs_wait_for_tasks'",
    )


class WaitForEcsTasksNodeRunOutput(BaseNodeRunOutput):
    type: Literal["aws_ecs_wait_for_tasks"] = Field(
        default="aws_ecs_wait_for_tasks",
        description="Discriminator field which must always be 'aws_ecs_wait_for_tasks'",
    )
    success: bool = Field(default=False, description="Whether the tasks succeeded")
    error_message: Optional[str] = Field(default=None, description="Why not, when not")
    tasks: List[EcsTaskOutcome] = Field(default_factory=list, description="Each task the node named, as it found it")
    timed_out: Optional[bool] = Field(default=None, description="Whether the wait ended at its timeout")


class GetEcsTaskLogsNodeConfig(EcsByArnFields, BaseAwsNodeConfig):
    """
    Reads an ECS task's logs from CloudWatch Logs, where its task definition sends them, into the run. Works in
    scheduled runs and re-runs; editor runs and voice calls route on an error.
    """

    type: Literal["aws_ecs_get_task_logs"] = Field(
        default="aws_ecs_get_task_logs", description="Type of the node. Must be 'aws_ecs_get_task_logs'"
    )
    task_arn: Optional[str] = Field(
        default=None,
        description=(
            "The task, by ARN in the format that names the cluster, or a variable holding one, such as "
            "[[start_task_task_arn]]. The lines read are copied into the run, so don't read a container that logs "
            "patient data unless the customer agrees; the AWS connection can turn log reads off."
        ),
        title="Task ARN",
    )
    container: Optional[str] = Field(
        default=None,
        description=(
            "The container whose logs to read. Defaults to the first essential container that logs to CloudWatch."
        ),
        title="Container",
    )
    max_lines: int = Field(
        default=100,
        ge=1,
        le=MAX_LOG_LINES,
        description=(
            f"How many lines to read: at most {MAX_LOG_LINES}. Each line is cut to {MAX_LOG_LINE_CHARS} characters."
        ),
        title="Max Lines",
    )
    read_from: Literal["tail", "head"] = Field(
        default="tail",
        description="Read the last lines (tail) or the first (head).",
        title="Read From",
    )
    filter_pattern: Optional[str] = Field(
        default=None,
        description="A CloudWatch Logs filter pattern, such as ERROR: only matching lines are read. May use variables.",
        title="Filter Pattern",
    )
    include_timestamps: bool = Field(
        default=False,
        description="Start each line with when it was logged.",
        title="Include Timestamps",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Base name for the variables this node writes: '<name>' (the lines read), '<name>_truncated', "
            "'<name>_success' and '<name>_error'. Defaults to the node's name in snake_case."
        ),
        title="Output Variable Name",
    )


class GetEcsTaskLogsNodeRunInput(BaseNodeRunInput):
    type: Literal["aws_ecs_get_task_logs"] = Field(
        default="aws_ecs_get_task_logs", description="Discriminator field which must always be 'aws_ecs_get_task_logs'"
    )


class GetEcsTaskLogsNodeRunOutput(BaseNodeRunOutput):
    type: Literal["aws_ecs_get_task_logs"] = Field(
        default="aws_ecs_get_task_logs", description="Discriminator field which must always be 'aws_ecs_get_task_logs'"
    )
    success: bool = Field(default=False, description="Whether the logs were read")
    error_message: Optional[str] = Field(default=None, description="Why not, when not")
    task_arn: Optional[str] = Field(default=None, description="The task whose logs it read")
    line_count: Optional[int] = Field(default=None, description="How many lines it read")
    truncated: Optional[bool] = Field(default=None, description="Whether more lines matched than it kept")


def ecs_launch_params(config: EcsLaunchFields, *, cluster: Optional[str], region: Optional[str]) -> Dict[str, Any]:
    """
    The job's launch parameters for the ECS provider, from a node's filled-in launch fields. Field names match the
    provider's one for one; a value left unset is left out, so the provider's defaults apply.
    """
    params: Dict[str, Any] = {"cluster": cluster, "task_definition": config.task_definition}
    if region:
        params["region"] = region
    if config.launch_type:
        params["launch_type"] = config.launch_type
    if config.capacity_provider_strategy:
        params["capacity_provider_strategy"] = [entry.model_dump() for entry in config.capacity_provider_strategy]
    if config.network is not None:
        params["network"] = config.network.model_dump()
    if config.container_overrides:
        params["container_overrides"] = [
            override.model_dump(exclude_none=True) for override in config.container_overrides
        ]
    if config.task_overrides is not None:
        task_overrides = config.task_overrides.model_dump(exclude_none=True)
        if task_overrides:
            params["task_overrides"] = task_overrides
    if config.tags:
        params["tags"] = dict(config.tags)
    if config.platform_version:
        params["platform_version"] = config.platform_version
    if config.enable_execute_command:
        params["enable_execute_command"] = True
    params["launch_retry"] = config.launch_retry.model_dump()
    return params
