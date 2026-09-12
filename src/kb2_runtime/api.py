from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

from kb2_runtime.config import CapabilityCatalog, Settings
from kb2_runtime.health.contracts import LivenessReport
from kb2_runtime.health.service import HealthService, UnknownCapabilityError
from kb2_runtime.workbench.service import WorkbenchOverviewService
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.storage import ArtifactStore


def create_app(settings: Settings | None = None, catalog: CapabilityCatalog | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    runtime_catalog = catalog or CapabilityCatalog.load(runtime_settings.capabilities_path)
    health = HealthService(runtime_settings, runtime_catalog)
    app = FastAPI(title="Knowledge Engine Lite Runtime", docs_url=None, redoc_url=None)
    static_root = Path(__file__).parent / "workbench" / "static"

    async def overview_health():
        # The local runner is a workbench dependency; DeepSeek remains unprobed.
        return await health.report(("runner.container",), probe_external=False)

    app.state.workbench_overview = None

    @app.get("/health/live", response_model=LivenessReport)
    async def live() -> LivenessReport:
        return LivenessReport()

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        report = await health.report(probe_external=False)
        return JSONResponse(
            report.model_dump(mode="json", exclude_none=True),
            status_code=200 if report.status == "ready" else 503,
        )

    @app.get("/health/capabilities")
    async def capabilities(require: list[str] = Query(default=[])) -> JSONResponse:
        try:
            report = await health.report(tuple(require))
        except UnknownCapabilityError as exc:
            return JSONResponse(
                {"contractVersion": "health/v1", "code": "UNKNOWN_CAPABILITY", "unknown": exc.unknown},
                status_code=400,
            )
        return JSONResponse(
            report.model_dump(mode="json", exclude_none=True),
            status_code=200 if report.status == "ready" else 503,
        )

    @app.get("/api/workbench/overview")
    async def workbench_overview() -> JSONResponse:
        repository = None
        try:
            repository = await TraceRepository.connect(**runtime_settings.connection_kwargs())
            overview = app.state.workbench_overview or WorkbenchOverviewService(
                overview_health, repository, ArtifactStore(runtime_settings.artifact_root).read
            )
            result = await overview.read()
        except Exception:
            return JSONResponse({"contractVersion": "workbench-problem/v1", "code": "OVERVIEW_UNAVAILABLE"}, status_code=503)
        finally:
            if repository is not None:
                await repository.close()
        return JSONResponse(result.model_dump(mode="json", exclude_none=True))

    @app.get("/workbench/assets/{asset_name}")
    async def workbench_asset(asset_name: str) -> FileResponse:
        if asset_name not in {"workbench.css", "workbench.js"}:
            return FileResponse(static_root / "index.html", status_code=404)
        return FileResponse(static_root / asset_name)

    @app.get("/workbench/{path:path}")
    async def workbench_shell(path: str) -> FileResponse:
        return FileResponse(static_root / "index.html")

    return app


app = create_app()
