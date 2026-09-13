from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse

from kb2_runtime.config import CapabilityCatalog, Settings
from kb2_runtime.health.contracts import LivenessReport
from kb2_runtime.health.service import HealthService, UnknownCapabilityError
from kb2_runtime.workbench.service import WorkbenchOverviewService
from kb2_runtime.workbench.contracts import CompatibilityRequest, DryRunRequest, ProfileRequest
from kb2_runtime.workbench.studio import StudioService
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.storage import ArtifactStore
from kb2_runtime.trace.service import ArtifactService, RunService
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.query_engine import QueryEngine
from kb2_runtime.ingestion_engine import IngestionEngine
from kb2_runtime.workbench.documents import DocumentWorkbenchService
from kb2_runtime.workbench.query import QueryWorkbenchService
from kb2_runtime.workbench.evaluation import EvaluationWorkbenchService
from kb2_runtime.workbench.diagnosis import ComparisonWorkbenchService, RunHistoryWorkbenchService
from kb2_runtime.evaluation.datasets.repository import DatasetRepository
from uuid import UUID


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
    app.state.workbench_studio = None
    app.state.workbench_query_runner = None
    app.state.workbench_documents = None
    app.state.workbench_query = None
    app.state.workbench_evaluation = None
    app.state.workbench_diagnosis = None

    async def studio() -> StudioService:
        # The workspace value itself is durable in PostgreSQL; this cached
        # connection only avoids rebuilding the projection per browser action.
        if app.state.workbench_studio is None:
            repository = await TraceRepository.connect(**runtime_settings.connection_kwargs())
            runner = app.state.workbench_query_runner
            if runner is None:
                artifacts = ArtifactService(repository, ArtifactStore(runtime_settings.artifact_root))
                runs = RunService(repository)
                executor = PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
                runner = QueryEngine(executor, runs, artifacts)
            async def registry_readiness():
                report = await overview_health()
                capabilities = {item.id: item.status == "ready" for item in report.capabilities}
                runners = {RunnerType.CONTAINER: capabilities.get("runner.container", False)}
                return capabilities, runners
            app.state.workbench_studio = StudioService(repository=repository, query_runner=runner, readiness=registry_readiness)
        return app.state.workbench_studio

    async def documents() -> DocumentWorkbenchService:
        if app.state.workbench_documents is None:
            repository = await TraceRepository.connect(**runtime_settings.connection_kwargs())
            artifacts = ArtifactService(repository, ArtifactStore(runtime_settings.artifact_root))
            runs = RunService(repository)
            registry = bootstrap_registry()
            executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
            app.state.workbench_documents = DocumentWorkbenchService(
                await studio(), registry, IngestionEngine(registry, executor, runs, artifacts), runs, artifacts,
                external_capabilities=frozenset(item.id for item in runtime_catalog.capabilities if item.provider is not None),
            )
        return app.state.workbench_documents

    async def query_lab() -> QueryWorkbenchService:
        if app.state.workbench_query is None:
            repository = await TraceRepository.connect(**runtime_settings.connection_kwargs())
            artifacts = ArtifactService(repository, ArtifactStore(runtime_settings.artifact_root))
            runs = RunService(repository)
            registry = bootstrap_registry()
            executor = PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts)
            app.state.workbench_query = QueryWorkbenchService(
                await studio(), registry, QueryEngine(executor, runs, artifacts), runs, artifacts,
                external_capabilities=frozenset(item.id for item in runtime_catalog.capabilities if item.provider is not None),
            )
        return app.state.workbench_query

    async def evaluation() -> EvaluationWorkbenchService:
        if app.state.workbench_evaluation is None:
            traces = await TraceRepository.connect(**runtime_settings.connection_kwargs())
            datasets = await DatasetRepository.connect(**runtime_settings.connection_kwargs())
            app.state.workbench_evaluation = EvaluationWorkbenchService(datasets, traces, ArtifactService(traces, ArtifactStore(runtime_settings.artifact_root)))
        return app.state.workbench_evaluation

    async def diagnosis() -> tuple[ComparisonWorkbenchService, RunHistoryWorkbenchService]:
        if app.state.workbench_diagnosis is None:
            traces = await TraceRepository.connect(**runtime_settings.connection_kwargs())
            artifacts = ArtifactService(traces, ArtifactStore(runtime_settings.artifact_root))
            app.state.workbench_diagnosis = (ComparisonWorkbenchService(traces, artifacts), RunHistoryWorkbenchService(traces))
        return app.state.workbench_diagnosis

    def problem(code: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"contractVersion": "workbench-problem/v1", "code": code}, status_code=status)

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

    @app.get("/api/workbench/profiles")
    async def workbench_profiles(kind: str | None = Query(default=None, pattern="^(ingestion|query)$"), q: str = Query(default="", max_length=64)) -> JSONResponse:
        return JSONResponse([x.model_dump(mode="json") for x in await (await studio()).list_profiles(kind, q)])

    @app.get("/api/workbench/profiles/{profile_id}")
    async def workbench_profile(profile_id: str) -> JSONResponse:
        item = await (await studio()).get_profile(profile_id)
        return JSONResponse(item.model_dump(mode="json") if item else {"contractVersion": "workbench-problem/v1", "code": "PROFILE_NOT_FOUND"}, status_code=200 if item else 404)

    @app.put("/api/workbench/profiles/{profile_id}")
    async def save_workbench_profile(profile_id: str, request: ProfileRequest) -> JSONResponse:
        if not __import__("re").fullmatch(r"[a-z][a-z0-9_.-]{0,47}", profile_id):
            return problem("PROFILE_ID_INVALID")
        checked = await (await studio()).validate(request.kind, request.document, source=request.source, media_type=request.mediaType)
        result = checked if not checked.valid or checked.normalizedDocument is None else await (await studio()).save(profile_id, request.kind, checked.normalizedDocument)
        if hasattr(result, "valid"):
            return JSONResponse(result.model_dump(mode="json"), status_code=422)
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/api/workbench/profiles/{profile_id}/copy")
    async def copy_workbench_profile(profile_id: str, copy_id: str = Query(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")) -> JSONResponse:
        result = await (await studio()).copy(profile_id, copy_id)
        if result is None:
            return problem("PROFILE_COPY_UNAVAILABLE", 404)
        return JSONResponse(result.model_dump(mode="json"), status_code=201)

    @app.post("/api/workbench/profiles/validate")
    async def validate_workbench_profile(request: ProfileRequest) -> JSONResponse:
        result = await (await studio()).validate(request.kind, request.document, False, request.searchArtifact, request.source, request.mediaType)
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/api/workbench/profiles/compile")
    async def compile_workbench_profile(request: ProfileRequest) -> JSONResponse:
        result = await (await studio()).validate(request.kind, request.document, True, request.searchArtifact, request.source, request.mediaType)
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/api/workbench/profiles/{profile_id}/dry-run")
    async def dry_run_workbench_profile(profile_id: str, request: DryRunRequest) -> JSONResponse:
        result = await (await studio()).dry_run(profile_id, request.kind, request.questionArtifactId, request.searchArtifact)
        if hasattr(result, "valid"):
            return JSONResponse(result.model_dump(mode="json"), status_code=409)
        return JSONResponse(result.model_dump(mode="json"))

    @app.get("/api/workbench/plugins")
    async def workbench_plugins(kind: str | None = Query(default=None, max_length=48), runner: str | None = Query(default=None, pattern="^(in_process|container)$"), readiness: str | None = Query(default=None, pattern="^(available|unavailable)$"), q: str = Query(default="", max_length=64)) -> JSONResponse:
        return JSONResponse([x.model_dump(mode="json", exclude_none=True) for x in await (await studio()).list_plugins(kind, runner, readiness, q)])

    @app.get("/api/workbench/plugins/compatible")
    async def compatible_workbench_plugins(stageKind: str = Query(pattern=r"^[a-z][a-z0-9_.-]{0,47}$")) -> JSONResponse:
        return JSONResponse([item.model_dump(mode="json") for item in await (await studio()).compatible_plugins(stageKind)])

    @app.post("/api/workbench/plugins/compatible")
    async def document_compatible_workbench_plugins(request: CompatibilityRequest) -> JSONResponse:
        result = await (await studio()).compatible_for_document(request.kind, request.document, request.stageId, request.source, request.mediaType)
        if isinstance(result, tuple):
            return JSONResponse([item.model_dump(mode="json") for item in result])
        return JSONResponse(result.model_dump(mode="json"), status_code=422)

    @app.get("/api/workbench/plugins/{plugin_id}")
    async def workbench_plugin(plugin_id: str) -> JSONResponse:
        item = await (await studio()).plugin_detail(plugin_id)
        return JSONResponse(item.model_dump(mode="json", exclude_none=True) if item else {"contractVersion": "workbench-problem/v1", "code": "PLUGIN_NOT_FOUND"}, status_code=200 if item else 404)

    @app.get("/api/workbench/query-lab/options")
    async def query_options() -> JSONResponse:
        try:
            return JSONResponse(await (await query_lab()).options())
        except Exception:
            return problem("QUERY_OPTIONS_UNAVAILABLE", 503)

    @app.post("/api/workbench/query-lab/preflights")
    async def query_preflight(payload: dict[str, object]) -> JSONResponse:
        try:
            question, profile_id, index_id = payload.get("question"), payload.get("profileId"), payload.get("indexId")
            if not isinstance(question, str) or not isinstance(profile_id, str) or not isinstance(index_id, str):
                raise ValueError
            return JSONResponse(await (await query_lab()).preflight(question, profile_id, UUID(index_id)))
        except LookupError as exc:
            return problem(str(exc), 404)
        except Exception:
            return problem("QUERY_PREFLIGHT_INVALID", 422)

    @app.post("/api/workbench/query-lab/preflights/{token}/runs")
    async def query_submit(token: str, payload: dict[str, object]) -> JSONResponse:
        try:
            return JSONResponse(await (await query_lab()).submit(token, payload.get("acknowledgeExternal") is True), status_code=202)
        except LookupError as exc:
            return problem(str(exc), 404)
        except PermissionError as exc:
            return problem(str(exc), 409)
        except RuntimeError:
            return problem("QUERY_SUBMISSION_UNAVAILABLE", 503)
        except Exception:
            return problem("QUERY_SUBMISSION_INVALID", 422)

    @app.get("/api/workbench/query-runs/{run_id}")
    async def query_run(run_id: UUID) -> JSONResponse:
        result = await (await query_lab()).run(run_id)
        return JSONResponse(jsonable_encoder(result)) if result else problem("QUERY_RUN_NOT_FOUND", 404)

    @app.get("/api/workbench/evaluation-datasets")
    async def evaluation_datasets(q: str = Query(default="", max_length=64)) -> JSONResponse:
        try:
            return JSONResponse(await (await evaluation()).datasets(q))
        except Exception:
            return problem("EVALUATION_DATASETS_UNAVAILABLE", 503)

    @app.get("/api/workbench/evaluation-datasets/{dataset_id}")
    async def evaluation_dataset(dataset_id: UUID, revision: int | None = Query(default=None, ge=1)) -> JSONResponse:
        result = await (await evaluation()).dataset(dataset_id, revision)
        return JSONResponse(result) if result else problem("EVALUATION_DATASET_NOT_FOUND", 404)

    @app.put("/api/workbench/evaluation-datasets/{dataset_id}")
    async def edit_evaluation_dataset(dataset_id: UUID, payload: dict[str, object]) -> JSONResponse:
        result = await (await evaluation()).edit(dataset_id, payload)
        return JSONResponse(result, status_code=200 if result["valid"] else 422)

    @app.post("/api/workbench/evaluation-datasets/{dataset_id}/revisions/{revision}/cases/{case_id}/review")
    async def review_evaluation_case(dataset_id: UUID, revision: int, case_id: str, payload: dict[str, object]) -> JSONResponse:
        reviewer = payload.get("reviewer")
        result = await (await evaluation()).review(dataset_id, revision, case_id, reviewer if isinstance(reviewer, str) else "")
        return JSONResponse(result, status_code=200 if result["valid"] else 409)

    @app.get("/api/workbench/evaluation-runs")
    async def evaluation_runs() -> JSONResponse:
        try:
            return JSONResponse(await (await evaluation()).runs())
        except Exception:
            return problem("EVALUATION_RUNS_UNAVAILABLE", 503)

    @app.get("/api/workbench/evaluation-runs/{run_id}")
    async def evaluation_run(run_id: UUID) -> JSONResponse:
        result = await (await evaluation()).run(run_id)
        return JSONResponse(result) if result else problem("EVALUATION_RUN_NOT_FOUND", 404)

    @app.get("/api/workbench/comparisons/eligible")
    async def comparison_eligible() -> JSONResponse:
        return JSONResponse(await (await diagnosis())[0].eligible())

    @app.post("/api/workbench/comparisons")
    async def comparison_create(payload: dict[str, object]) -> JSONResponse:
        try:
            baseline, candidate = UUID(str(payload.get("baselineReportId"))), UUID(str(payload.get("candidateReportId")))
        except (ValueError, TypeError):
            return problem("COMPARISON_INCOMPATIBLE", 422)
        result = await (await diagnosis())[0].create(baseline, candidate)
        return JSONResponse(result, status_code=201 if result["valid"] else 409)

    @app.get("/api/workbench/comparisons/{artifact_id}")
    async def comparison_detail(artifact_id: UUID) -> JSONResponse:
        result = await (await diagnosis())[0].detail(artifact_id)
        return JSONResponse(result) if result else problem("COMPARISON_NOT_FOUND", 404)

    @app.get("/api/workbench/runs")
    async def run_history(runType: str = Query(default="", max_length=16), state: str = Query(default="", max_length=16), q: str = Query(default="", max_length=64)) -> JSONResponse:
        return JSONResponse(await (await diagnosis())[1].list(runType, state, q))

    @app.get("/api/workbench/runs/{run_id}")
    async def run_history_detail(run_id: UUID) -> JSONResponse:
        result = await (await diagnosis())[1].detail(run_id)
        # Recovery authority belongs to the owner workflow's live process map,
        # never to a persisted Run state inferred by the history projection.
        if result and result["type"] == "INGESTION":
            owner = await (await documents()).run(run_id)
            result["actions"] = owner["actions"] if owner else {}
        elif result and result["type"] == "QUERY":
            owner = await (await query_lab()).run(run_id)
            result["actions"] = owner["actions"] if owner else {}
        return JSONResponse(result) if result else problem("RUN_NOT_FOUND", 404)

    @app.post("/api/workbench/query-runs/{run_id}/stop")
    async def stop_query_run(run_id: UUID) -> JSONResponse:
        return JSONResponse({"stopped": True}) if await (await query_lab()).stop(run_id) else problem("QUERY_STOP_UNAVAILABLE", 409)

    @app.put("/api/workbench/documents/preflight")
    async def document_preflight(request: Request, profile_id: str = Header(alias="X-Profile-Id"), filename: str = Header(alias="X-Filename"), media_type: str = Header(default="application/octet-stream", alias="Content-Type")) -> JSONResponse:
        try:
            chunks: list[bytes] = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16 * 1024 * 1024:
                    raise ValueError("PREFLIGHT_INVALID")
                chunks.append(chunk)
            return JSONResponse(await (await documents()).preflight(b"".join(chunks), filename, media_type, profile_id))
        except LookupError as exc:
            return problem(str(exc), 404)
        except (ValueError, ProfileError):
            return problem("PREFLIGHT_INVALID", 422)

    @app.post("/api/workbench/documents/preflights/{token}/runs")
    async def document_submit(token: str, payload: dict[str, object]) -> JSONResponse:
        try:
            result = await (await documents()).submit(token, payload.get("profileId") if isinstance(payload.get("profileId"), str) else None, payload.get("acknowledgeExternal") is True)
            return JSONResponse(result, status_code=202)
        except LookupError as exc:
            return problem(str(exc), 404)
        except PermissionError as exc:
            return problem(str(exc), 409)
        except RuntimeError:
            return problem("INGESTION_SUBMISSION_UNAVAILABLE", 503)
        except (ValueError, ProfileError):
            return problem("INGESTION_SUBMISSION_INVALID", 422)

    @app.get("/api/workbench/ingestion-runs/{run_id}")
    async def ingestion_run(run_id: UUID) -> JSONResponse:
        result = await (await documents()).run(run_id)
        return JSONResponse(jsonable_encoder(result), status_code=200) if result else problem("INGESTION_RUN_NOT_FOUND", 404)

    @app.post("/api/workbench/ingestion-runs/{run_id}/stop")
    async def stop_ingestion_run(run_id: UUID) -> JSONResponse:
        return JSONResponse({"stopped": True}) if await (await documents()).stop(run_id) else problem("RUN_STOP_UNAVAILABLE", 409)

    @app.post("/api/workbench/ingestion-runs/{run_id}/rerun-preflight")
    async def rerun_ingestion_preflight(run_id: UUID, payload: dict[str, object]) -> JSONResponse:
        workspace_profile_id = payload.get("workspaceProfileId")
        if not isinstance(workspace_profile_id, str):
            return problem("WORKSPACE_PROFILE_REQUIRED", 422)
        try:
            return JSONResponse(await (await documents()).rerun_preflight(run_id, workspace_profile_id), status_code=201)
        except LookupError as exc:
            return problem(str(exc), 404)
        except (ValueError, ProfileError):
            return problem("RERUN_PREFLIGHT_INVALID", 422)

    @app.get("/api/workbench/artifacts/{artifact_id}")
    async def artifact_inspector(artifact_id: UUID) -> JSONResponse:
        result = await (await documents()).artifact(artifact_id)
        return JSONResponse(result) if result else problem("ARTIFACT_NOT_FOUND", 404)

    @app.get("/workbench/assets/{asset_name}")
    async def workbench_asset(asset_name: str) -> FileResponse:
        if asset_name not in {
            "workbench.css",
            "workbench.js",
            "artifact.css",
            "archivo-400.woff2",
            "archivo-600.woff2",
            "archivo-800.woff2",
        }:
            return FileResponse(static_root / "index.html", status_code=404)
        return FileResponse(static_root / asset_name)

    @app.get("/workbench/{path:path}")
    async def workbench_shell(path: str) -> FileResponse:
        return FileResponse(static_root / "index.html")

    return app


app = create_app()
