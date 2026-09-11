from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from kb2_runtime.trace.schemas import schema_is_supported

from .contracts import PluginAvailability, PluginDescriptor, PluginImplementation, RunnerType
from .errors import PluginError, PluginErrorCode


@dataclass(frozen=True)
class PluginRegistration:
    descriptor: PluginDescriptor
    factory: Callable[[], PluginImplementation]
    configuration_model: type[BaseModel]


class PluginRegistry:
    def __init__(self, capability_check: Callable[[str], bool], runner_ready: Callable[[RunnerType], bool]) -> None:
        self._capability_check, self._runner_ready = capability_check, runner_ready
        self._items: dict[str, PluginRegistration] = {}

    def register(self, descriptor: PluginDescriptor | object, factory: Callable[[], PluginImplementation], configuration_model: type[BaseModel]) -> None:
        try:
            descriptor = PluginDescriptor.model_validate(descriptor)
        except ValidationError as exc:
            raise PluginError(PluginErrorCode.DESCRIPTOR_INVALID) from exc
        if descriptor.plugin_id in self._items:
            raise PluginError(PluginErrorCode.ID_DUPLICATE)
        if not callable(factory) or not isinstance(configuration_model, type) or not issubclass(configuration_model, BaseModel):
            raise PluginError(PluginErrorCode.DESCRIPTOR_INVALID)
        if configuration_model.model_config.get("extra") != "forbid" or not configuration_model.model_config.get("frozen"):
            raise PluginError(PluginErrorCode.DESCRIPTOR_INVALID)
        expected = configuration_model.model_json_schema()
        if descriptor.configuration_schema != expected:
            raise PluginError(PluginErrorCode.DESCRIPTOR_INVALID)
        if any(not schema_is_supported(*schema) for schema in (*descriptor.input_schemas, *descriptor.output_schemas)):
            raise PluginError(PluginErrorCode.SCHEMA_INCOMPATIBLE)
        self._items[descriptor.plugin_id] = PluginRegistration(descriptor, factory, configuration_model)

    def get(self, plugin_id: str) -> PluginRegistration:
        try:
            return self._items[plugin_id]
        except KeyError as exc:
            raise PluginError(PluginErrorCode.NOT_REGISTERED) from exc

    def inspect(self, plugin_id: str | None = None) -> tuple[PluginAvailability, ...]:
        items = (self.get(plugin_id),) if plugin_id else tuple(self._items.values())
        return tuple(PluginAvailability(plugin_id=item.descriptor.plugin_id, runnable=self._runnable(item), reason=self._unavailable_reason(item)) for item in items)

    def _runnable(self, item: PluginRegistration) -> bool:
        return self._runner_ready(item.descriptor.runner) and all(self._capability_check(value) for value in item.descriptor.capabilities)

    def _unavailable_reason(self, item: PluginRegistration) -> str | None:
        if not self._runner_ready(item.descriptor.runner):
            return "RUNNER_UNAVAILABLE"
        if not all(self._capability_check(value) for value in item.descriptor.capabilities):
            return "CAPABILITY_UNAVAILABLE"
        return None
