"""Allowlisted plugin registration and execution contracts."""

from .contracts import PluginDescriptor, PluginInvocationResult, PluginOutput, RunnerType, StageInvocation
from .executor import PluginExecutor
from .registry import PluginRegistry
from .bootstrap import bootstrap_registry

__all__ = [
    "PluginDescriptor", "PluginExecutor", "PluginInvocationResult", "PluginOutput",
    "PluginRegistry", "RunnerType", "StageInvocation", "bootstrap_registry",
]
