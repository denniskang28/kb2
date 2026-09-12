from __future__ import annotations

from collections.abc import Awaitable, Callable
import hashlib
import json
from typing import Any, Protocol

from kb2_runtime.health.contracts import HealthReport
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType

from .contracts import OverviewCapability, OverviewComparison, OverviewComponent, OverviewFailure, OverviewPlugin, OverviewRun, WorkbenchOverview


class OverviewReadRepository(Protocol):
    async def list_overview_runs(self, limit: int = 8): ...

    async def count_active_runs(self) -> int: ...

    async def list_workbench_comparisons(self, limit: int = 4): ...


class WorkbenchOverviewService:
    """Assembles a small safe projection; browser clients never derive readiness."""

    def __init__(self, health: Callable[[], Awaitable[HealthReport]], repository: OverviewReadRepository | None = None, read_artifact: Callable[[str, str], bytes] | None = None) -> None:
        self._health = health
        self._repository = repository
        self._read_artifact = read_artifact

    async def read(self) -> WorkbenchOverview:
        report = await self._health()
        capability_status = {entry.id: entry.status == "ready" for entry in report.capabilities}
        runner_status = {RunnerType.CONTAINER: capability_status.get("runner.container", False)}
        registry = bootstrap_registry(
            capability_check=lambda item: capability_status.get(item, False),
            runner_ready=lambda runner: runner is not RunnerType.CONTAINER or runner_status[RunnerType.CONTAINER],
        )
        plugins = tuple(OverviewPlugin(pluginId=item.plugin_id, runnable=item.runnable, reason=item.reason) for item in registry.inspect())
        runs: tuple[OverviewRun, ...] = ()
        active = 0
        comparisons: tuple[OverviewComparison, ...] = ()
        if self._repository is not None:
            runs = tuple(self._run(item) for item in await self._repository.list_workbench_runs(8))
            active = await self._repository.count_active_runs()
            if self._read_artifact is not None:
                comparisons = tuple(
                    item for item in (
                        self._comparison(row) for row in await self._repository.list_workbench_comparisons(4)
                    ) if item is not None
                )
        return WorkbenchOverview(
            checkedAt=report.checkedAt,
            coreStatus="ready" if all(item.status == "ready" for item in report.components if item.required) else "not_ready",
            core=tuple(OverviewComponent(id=item.id, status=item.status, code=item.code) for item in report.components),
            optionalCapabilities=tuple(OverviewCapability(id=item.id, status=item.status, code=item.code, provider=item.provider, model=item.model, latencyMs=item.latencyMs) for item in report.capabilities),
            plugins=plugins,
            activeRunCount=active,
            recentRuns=runs,
            recentComparisons=comparisons,
        )

    @staticmethod
    def _run(row: dict[str, Any]) -> OverviewRun:
        error = row.get("safe_error")
        failure = None
        if isinstance(error, dict) and isinstance(error.get("code"), str) and isinstance(error.get("retryable"), bool):
            failure = OverviewFailure(code=error["code"], retryable=error["retryable"])
        return OverviewRun(
            id=row["id"], engineKind=row["engine_kind"], state=row["state"], terminalState=row["terminal_state"],
            createdAt=row["created_at"], startedAt=row["started_at"], endedAt=row["ended_at"], planDigest=row["plan_digest"], failure=failure,
        )

    def _comparison(self, row: dict[str, Any]) -> OverviewComparison | None:
        try:
            content = self._read_artifact(row["content_digest"], row["storage_locator"]) if self._read_artifact else b""
            if hashlib.sha256(content).hexdigest() != row["content_digest"]:
                return None
            value = json.loads(content)
            if value.get("schema_version") != "EvaluationComparison/v1":
                return None
            return OverviewComparison(
                artifactId=row["id"], runId=row["producing_run_id"], createdAt=row["created_at"],
                mode=value["mode"], axis=value.get("axis"), recommendation=value["recommendation"],
            )
        except (AttributeError, KeyError, TypeError, ValueError, OSError):
            return None
