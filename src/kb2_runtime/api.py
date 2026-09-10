from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from kb2_runtime.config import CapabilityCatalog, Settings
from kb2_runtime.health.contracts import LivenessReport
from kb2_runtime.health.service import HealthService, UnknownCapabilityError


def create_app(settings: Settings | None = None, catalog: CapabilityCatalog | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    runtime_catalog = catalog or CapabilityCatalog.load(runtime_settings.capabilities_path)
    health = HealthService(runtime_settings, runtime_catalog)
    app = FastAPI(title="Knowledge Engine Lite Runtime", docs_url=None, redoc_url=None)

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

    return app


app = create_app()
