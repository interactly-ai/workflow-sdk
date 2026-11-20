"""
Node types, and node fields, a deployment must enable before authors can use them.

Until its flag is on, a gated type is left out of the node palette, its schema is not served, and a workflow that adds
one is refused when it is saved or imported. A gated field keeps its default: it is hidden in every node's form, and a
node that sets it is refused the same way. The flag gates authoring only: parsing a stored node never consults it, and
a workflow that already holds a gated node or field is never refused at run time, so turning a flag off breaks no run.

Upstream also decides, from the deployment's own flags, which types and fields are off, and words the refusal. Only
the server knows its flags, so those functions are not vendored: a client meets a refused save as the server's 400,
which names each offending node and the flag that is off. The maps below say which flag that would be.
"""

from typing import Dict

from interactly_configs.nodes.node import NodeType

#: Each gated node type, and the name of the server flag that enables it.
GATED_NODE_TYPES: Dict[NodeType, str] = {
    NodeType.PAUSE_WORKFLOW: "CONTROL_WAIT_NODES_ENABLED",
    NodeType.WAIT: "CONTROL_WAIT_NODES_ENABLED",
    NodeType.WAIT_FOR_SIGNAL: "CONTROL_WAIT_NODES_ENABLED",
    NodeType.TERMINATE_WORKFLOW: "CONTROL_WAIT_NODES_ENABLED",
    NodeType.AWS_ECS_RUN_TASK: "ECS_NODES_ENABLED",
    NodeType.AWS_ECS_START_TASK: "ECS_NODES_ENABLED",
    NodeType.AWS_ECS_GET_TASK_STATUS: "ECS_NODES_ENABLED",
    NodeType.AWS_ECS_STOP_TASK: "ECS_NODES_ENABLED",
    NodeType.AWS_ECS_WAIT_FOR_TASKS: "ECS_NODES_ENABLED",
    NodeType.AWS_ECS_GET_TASK_LOGS: "ECS_NODES_ENABLED",
}

#: Each gated field of every node config, and the name of the flag that enables it. ``on_failure``'s
#: ``abort_workflow`` ends a run as failed the way the Terminate workflow node does, so it is enabled with it.
GATED_NODE_FIELDS: Dict[str, str] = {
    "on_failure": "CONTROL_WAIT_NODES_ENABLED",
}


class NodeAuthoringRefusedError(ValueError):
    """A workflow cannot be saved with these nodes: a refusal of what the author asked for, not a failure."""


class NodeTypeNotEnabledError(NodeAuthoringRefusedError):
    """A workflow adds a node of a type this deployment has not enabled."""
