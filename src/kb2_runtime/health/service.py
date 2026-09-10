from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from kb2_runtime.config import CapabilityCatalog, CapabilityDefinition, ComponentDefinition, Settings
from kb2_runtime.health.contracts import HealthEntry, HealthReport
from kb2_runtime.health.probes import (
    artifact_probe,
    bounded_probe,
    deepseek_models,
    postgres_probe,
    worker_probe,
)


class UnknownCapabilityError(ValueError):
    def __init__(self, unknown: list[str]) -> None:
        super().__init__("UNKNOWN_CAPABILITY")
        self.unknown = unknown


class HealthService:
    def __init__(self, settings: Settings, catalog: CapabilityCatalog) -> None:
        self.settings = settings
        self.catalog = catalog

    async def report(
        self, requested: tuple[str, ...] = (), *, probe_external: bool = True
    ) -> HealthReport:
        known = {item.id for item in self.catalog.capabilities}
        unknown = sorted(set(requested) - known)
        if unknown:
            raise UnknownCapabilityError(unknown)
        required = set(requested)
        components, capabilities = await asyncio.gather(
            self._components(), self._capabilities(required, probe_external)
        )
        return HealthReport.create(self.settings.environment, components, capabilities)

    async def _components(self) -> list[HealthEntry]:
        return list(await asyncio.gather(*(self._component(item) for item in self.catalog.components)))

    async def _component(self, item: ComponentDefinition) -> HealthEntry:
        provider: str | None = None
        if item.probe == "self":
            return HealthEntry(id=item.id, required=item.required, status="ready", code="OK", latencyMs=0)
        probes: dict[str, tuple[Callable[[Settings], Awaitable[tuple[str, str]]], str | None]] = {
            "postgres": (postgres_probe, self.settings.postgres_provider),
            "artifact": (artifact_probe, self.settings.artifact_provider),
            "worker": (worker_probe, None),
        }
        probe, provider = probes[item.probe]
        status, code, latency = await bounded_probe(lambda: probe(self.settings), self.settings.probe_timeout_seconds)
        return HealthEntry(
            id=item.id,
            required=item.required,
            status=status,
            code=code,
            latencyMs=latency,
            provider=provider,
        )

    async def _capabilities(
        self, requested: set[str], probe_external: bool
    ) -> list[HealthEntry]:
        deepseek_items = [item for item in self.catalog.capabilities if item.probe == "deepseek-model"]
        models: set[str] = set()
        provider_status = "not_configured"
        provider_code = "NOT_CONFIGURED"
        provider_latency = 0
        api_key: str | None = None
        if deepseek_items:
            try:
                api_key = self.settings.deepseek_api_key()
            except Exception:
                provider_status = "unavailable"
                provider_code = "DEPENDENCY_UNAVAILABLE"
            if api_key is not None and not requested.intersection(
                item.id for item in deepseek_items
            ):
                provider_status = "not_probed"
                provider_code = "NOT_PROBED"
            elif api_key is not None and probe_external:
                discovered: dict[str, set[str]] = {}

                async def probe() -> tuple[str, str]:
                    discovered["models"] = await deepseek_models(self.settings, api_key)
                    return "ready", "OK"

                provider_status, provider_code, provider_latency = await bounded_probe(
                    probe, self.settings.probe_timeout_seconds
                )
                models = discovered.get("models", set())
        return [
            self._capability(
                item,
                requested,
                models,
                provider_status,
                provider_code,
                provider_latency,
            )
            for item in self.catalog.capabilities
        ]

    def _capability(
        self,
        item: CapabilityDefinition,
        requested: set[str],
        models: set[str],
        provider_status: str,
        provider_code: str,
        provider_latency: int,
    ) -> HealthEntry:
        required = item.required or item.id in requested
        if item.probe == "not-configured":
            return HealthEntry(
                id=item.id,
                required=required,
                status="not_configured",
                code="NOT_CONFIGURED",
                latencyMs=0,
                provider=item.provider,
                model=item.model,
            )
        if item.probe != "deepseek-model" or item.model is None:
            return HealthEntry(
                id=item.id,
                required=required,
                status="unavailable",
                code="PROBE_UNSUPPORTED",
                latencyMs=0,
                provider=item.provider,
                model=item.model,
            )
        if item.id not in requested and provider_status != "not_configured":
            return HealthEntry(
                id=item.id,
                required=required,
                status="not_probed",
                code="NOT_PROBED",
                latencyMs=0,
                provider=item.provider,
                model=item.model,
            )
        status = provider_status
        code = provider_code
        if status == "ready" and item.model not in models:
            status = "unavailable"
            code = "MODEL_NOT_AVAILABLE"
        return HealthEntry(
            id=item.id,
            required=required,
            status=status,
            code=code,
            latencyMs=provider_latency,
            provider=item.provider,
            model=item.model,
        )
