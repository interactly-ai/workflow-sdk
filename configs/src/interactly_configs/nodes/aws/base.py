"""Shared base for the AWS nodes: the connection they act through, and where in AWS they act."""

from typing import Optional

from pydantic import Field

from interactly_configs.nodes.node import BaseNodeConfig, NodeCategory, SelfLoopConfig


class BaseAwsNodeConfig(BaseNodeConfig):
    """Files the node under AWS › ECS, and names the AWS connection, region and cluster it acts in."""

    primary_category: Optional[str] = Field(
        default=NodeCategory.AWS.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.ECS.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    self_loop_config: Optional[SelfLoopConfig] = Field(
        default=None,
        description="An AWS node runs once each time it is entered.",
        title="Self Loop",
    )
    connection_id: Optional[str] = Field(
        default=None,
        description=(
            "The team's AWS connection to act through (an integration of type 'aws'). It says which AWS account, "
            "role, clusters and task definitions the node may use."
        ),
        title="AWS Connection",
    )
    region: Optional[str] = Field(
        default=None,
        description="The AWS region, such as 'us-east-1'. Defaults to the connection's region. May use variables.",
        title="Region",
    )
    cluster: Optional[str] = Field(
        default=None,
        description="The ECS cluster's name or ARN, on the connection's cluster allowlist. May use variables.",
        title="Cluster",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default=None,
        description=(
            "Base name for the variables this node writes: '<name>' (a summary of the task), '<name>_success', "
            "'<name>_error', '<name>_status', '<name>_task_arn' and '<name>_exit_code'. Defaults to the node's name in "
            "snake_case."
        ),
        title="Output Variable Name",
    )
