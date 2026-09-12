"""Allowlisted plugin registration and execution contracts."""

from .contracts import PluginDescriptor, PluginInvocationReceipt, PluginInvocationResult, PluginOutput, PluginPort, RunnerType, StageInvocation
from .executor import PluginExecutor
from .registry import PluginRegistry


def bootstrap_registry(*args: object, **kwargs: object):
    """Load repository bootstrap lazily to avoid plugin implementation import cycles."""
    from .bootstrap import bootstrap_registry as _bootstrap_registry
    return _bootstrap_registry(*args, **kwargs)

__all__ = [
    "PluginDescriptor", "PluginExecutor", "PluginInvocationReceipt", "PluginInvocationResult", "PluginOutput", "PluginPort",
    "PluginRegistry", "RunnerType", "StageInvocation", "bootstrap_registry",
]
