"""
How a workflow that ended itself says it ended.

A module of its own, with no imports from the rest of the framework, so a node config can name it: the run models
import every node config, and a node config importing them back would be circular.
"""

from typing import Literal

#: Each value names the terminal status a driver stores for the run. A run that ended by running out of nodes to run
#: carries none, and is completed.
WorkflowOutcome = Literal["completed", "failed", "cancelled"]

#: What made a node end the run: a Terminate workflow node, or a node that failed with ``on_failure: abort_workflow``.
#: Drivers store a different termination source for each.
WorkflowTerminationCause = Literal["terminate_node", "on_failure"]
