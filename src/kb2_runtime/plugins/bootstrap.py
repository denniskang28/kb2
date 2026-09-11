"""Repository-owned Plugin allowlist shared by executor and fixed sidecar."""
from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from .contracts import PluginContext, PluginDescriptor, PluginInvocationResult, PluginOutput, RunnerType
from .registry import PluginRegistry


class SyntheticTransformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suffix: str = ""


class SyntheticTransform:
    """Deterministic contract plugin; it is not a production parser or model."""
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        suffix = context.invocation.validated_configuration["suffix"].encode("utf-8")
        return PluginInvocationResult(
            outputs=(PluginOutput(artifact_type="opaque.bytes", schema_revision="v1", content=source.content + suffix),),
            summary="synthetic transform completed",
        )


SYNTHETIC_TRANSFORM_DESCRIPTOR = PluginDescriptor(
    plugin_id="transform.synthetic@1",
    kind="transform",
    implementation_digest="a" * 64,
    runner=RunnerType.CONTAINER,
    configuration_schema=SyntheticTransformConfig.model_json_schema(),
    input_schemas=(("opaque.bytes", "v1"),),
    output_schemas=(("opaque.bytes", "v1"),),
    timeout_seconds=10,
)


def bootstrap_registry(
    capability_check: Callable[[str], bool] = lambda _: True,
    runner_ready: Callable[[RunnerType], bool] = lambda _: True,
) -> PluginRegistry:
    registry = PluginRegistry(capability_check, runner_ready)
    registry.register(SYNTHETIC_TRANSFORM_DESCRIPTOR, SyntheticTransform, SyntheticTransformConfig)
    return registry
