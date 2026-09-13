from __future__ import annotations

from collections.abc import Awaitable, Callable
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileParser
from kb2_runtime.ingestion_profiles.errors import ProfileError
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.query_profiles import QueryArtifactBinding, QueryProfileCompiler, QueryProfileParser
from kb2_runtime.query_profiles.errors import QueryProfileError

from .contracts import (DryRunReceipt, ProfileValidation, RegistryPlugin, RegistryPluginDetail,
                        RegistryPort, StudioDiagnostic, WorkspaceProfile,
                        WorkspaceProfileSummary)


class ProfileWorkspaceRepository(Protocol):
    async def list_profile_workspaces(self, kind: str | None = None, query: str = "") -> tuple[dict[str, Any], ...]: ...
    async def get_profile_workspace(self, profile_id: str) -> dict[str, Any] | None: ...
    async def save_profile_workspace(self, profile_id: str, kind: str, document: dict[str, Any]) -> dict[str, Any]: ...
    async def list_plugin_workbench_runs(self, plugin_id: str, limit: int = 8) -> tuple[dict[str, Any], ...]: ...


class QueryDryRunner(Protocol):
    async def execute(self, plan: Any, question_artifact: UUID, search_artifact: UUID) -> Any: ...


class StudioService:
    """Bounded working-config and inspect-only Registry projection.

    The in-memory mapping is intentionally injectable for API tests. Production
    persistence is supplied by the small profile_workspaces table migration.
    """

    def __init__(self, readiness: Callable[[], Awaitable[tuple[dict[str, bool], dict[RunnerType, bool]]]] | None = None, repository: ProfileWorkspaceRepository | None = None, query_runner: QueryDryRunner | None = None) -> None:
        self._items: dict[str, WorkspaceProfile] = {}
        self._readiness = readiness
        self._repository = repository
        self._query_runner = query_runner

    async def dry_run(self, profile_id: str, kind: str, question_artifact_id: str | None, search_artifact: dict[str, Any] | None) -> DryRunReceipt | ProfileValidation:
        if kind == "ingestion":
            return self._invalid("INGESTION_DRY_RUN_UNSUPPORTED", "/kind")
        saved = await self.get_profile(profile_id)
        if saved is None or saved.kind != "query":
            return self._invalid("PROFILE_NOT_SAVED", "/profile_id")
        if question_artifact_id is None:
            return self._invalid("QUESTION_ARTIFACT_REQUIRED", "/questionArtifactId")
        compiled = await self.validate("query", saved.document, True, search_artifact)
        if not compiled.valid or compiled.resolvedPlan is None or compiled.planDigest is None:
            return compiled
        if self._query_runner is None:
            return self._invalid("QUERY_RUNTIME_UNAVAILABLE", "/")
        try:
            binding = QueryArtifactBinding.model_validate(search_artifact)
            parsed = QueryProfileParser.parse(__import__("json").dumps(saved.document), "application/json")
            plan = QueryProfileCompiler(await self._registry()).compile(parsed, binding).get(profile_id)
            receipt = await self._query_runner.execute(plan, UUID(question_artifact_id), UUID(binding.artifact_id))
            return DryRunReceipt(runId=str(receipt.run_id), profileId=receipt.profile_id, planDigest=receipt.plan_digest)
        except (ValueError, TypeError):
            return self._invalid("QUERY_ARTIFACT_INVALID", "/questionArtifactId")

    async def _registry(self):
        capabilities: dict[str, bool] = {}
        runners: dict[RunnerType, bool] = {RunnerType.CONTAINER: True}
        if self._readiness:
            capabilities, runners = await self._readiness()
        return bootstrap_registry(
            capability_check=lambda value: capabilities.get(value, True),
            runner_ready=lambda value: runners.get(value, True),
        )

    async def list_profiles(self, kind: str | None = None, query: str = "") -> tuple[WorkspaceProfileSummary, ...]:
        if self._repository is not None:
            return tuple(WorkspaceProfileSummary(profileId=x["profile_id"], kind=x["profile_kind"], updatedAt=x["updated_at"])
                         for x in await self._repository.list_profile_workspaces(kind, query))
        query = query.lower()
        return tuple(
            WorkspaceProfileSummary(profileId=item.profileId, kind=item.kind, updatedAt=item.updatedAt)
            for item in sorted(self._items.values(), key=lambda x: (x.kind, x.profileId))
            if (kind is None or item.kind == kind) and query in item.profileId.lower()
        )[:64]

    async def get_profile(self, profile_id: str) -> WorkspaceProfile | None:
        if self._repository is not None:
            row = await self._repository.get_profile_workspace(profile_id)
            return WorkspaceProfile(profileId=row["profile_id"], kind=row["profile_kind"], document=row["source_document"], updatedAt=row["updated_at"]) if row else None
        return self._items.get(profile_id)

    async def validate(self, kind: str, document: dict[str, Any] | None, compile: bool = False, search_artifact: dict[str, Any] | None = None, source: str | None = None, media_type: str = "application/json") -> ProfileValidation:
        try:
            payload = source if source is not None else __import__("json").dumps(document)
            if kind == "ingestion":
                parsed = ProfileParser.parse(payload, media_type)  # type: ignore[arg-type]
                normalized = parsed.model_dump(mode="json", exclude_none=True)
                if not compile:
                    return ProfileValidation(valid=True, normalizedDocument=normalized)
                plan = ProfileCompiler(await self._registry()).compile(parsed).get(parsed.default_profile_id)
            else:
                parsed = QueryProfileParser.parse(payload, media_type)  # type: ignore[arg-type]
                normalized = parsed.model_dump(mode="json", exclude_none=True)
                if not compile:
                    return ProfileValidation(valid=True, normalizedDocument=normalized)
                if search_artifact is None:
                    return self._invalid("SCHEMA_INCOMPATIBLE", "/searchArtifact")
                binding = QueryArtifactBinding.model_validate(search_artifact)
                plan = QueryProfileCompiler(await self._registry()).compile(parsed, binding).get(parsed.default_profile_id)
            return ProfileValidation(valid=True, normalizedDocument=normalized, resolvedPlan=plan.canonical_payload, planDigest=plan.digest)
        except (ProfileError, QueryProfileError) as exc:
            return self._invalid(exc.code.value, exc.location)
        except (ValueError, TypeError):
            return self._invalid("PARSE_INVALID", "/")

    @staticmethod
    def _invalid(code: str, location: str = "/") -> ProfileValidation:
        return ProfileValidation(valid=False, diagnostics=(StudioDiagnostic(code=code, location=location or "/"),))

    async def save(self, profile_id: str, kind: str, document: dict[str, Any]) -> WorkspaceProfile | ProfileValidation:
        checked = await self.validate(kind, document)
        if not checked.valid or checked.normalizedDocument is None:
            return checked
        body_id = checked.normalizedDocument.get("default_profile_id")
        if body_id != profile_id:
            return self._invalid("PROFILE_ID_MISMATCH", "/default_profile_id")
        value = WorkspaceProfile(profileId=profile_id, kind=kind, document=checked.normalizedDocument, updatedAt=datetime.now(timezone.utc))
        if self._repository is not None:
            row = await self._repository.save_profile_workspace(profile_id, kind, checked.normalizedDocument)
            return WorkspaceProfile(profileId=row["profile_id"], kind=row["profile_kind"], document=row["source_document"], updatedAt=row["updated_at"])
        self._items[profile_id] = value
        return value

    async def copy(self, profile_id: str, copy_id: str) -> WorkspaceProfile | None:
        source = await self.get_profile(profile_id)
        if source is None or await self.get_profile(copy_id) is not None:
            return None
        document = __import__("copy").deepcopy(source.document)
        document["default_profile_id"] = copy_id
        for profile in document.get("profiles", []):
            if profile.get("profile_id") == profile_id:
                profile["profile_id"] = copy_id
        saved = await self.save(copy_id, source.kind, document)
        return saved if isinstance(saved, WorkspaceProfile) else None

    async def list_plugins(self, kind: str | None = None, runner: str | None = None, readiness: str | None = None, query: str = "") -> tuple[RegistryPlugin, ...]:
        registry = await self._registry()
        statuses = {x.plugin_id: x for x in registry.inspect()}
        result = []
        for plugin_id in sorted(statuses):
            descriptor = registry.get(plugin_id).descriptor
            status = statuses[plugin_id]
            if kind and descriptor.kind != kind or runner and descriptor.runner.value != runner:
                continue
            if readiness == "available" and not status.runnable or readiness == "unavailable" and status.runnable:
                continue
            if query.lower() not in plugin_id.lower() and query.lower() not in descriptor.kind.lower():
                continue
            result.append(RegistryPlugin(pluginId=plugin_id, kind=descriptor.kind, runner=descriptor.runner.value, runnable=status.runnable, reason=status.reason))
        return tuple(result[:128])

    async def compatible_plugins(self, stage_kind: str, available_schemas: tuple[tuple[str, str], ...] = ()) -> tuple[RegistryPlugin, ...]:
        """Server-owned selector: slot label plus every required named port must fit."""
        registry = await self._registry()
        result: list[RegistryPlugin] = []
        for status in registry.inspect():
            descriptor = registry.get(status.plugin_id).descriptor
            # Stage labels intentionally map to descriptor families here, not in
            # the browser. Registry ports remain the compatibility authority.
            family = {"retrieve": "retriever", "generate": "generator", "verify": "verifier", "rerank": "reranker"}.get(stage_kind, stage_kind)
            if not status.runnable or descriptor.kind != family:
                continue
            # Each named input port's cardinality is checked independently;
            # sharing one upstream schema cannot satisfy two required ports.
            required: Counter[tuple[str, str]] = Counter()
            for port in descriptor.input_ports:
                required[port.schema] += port.min_items
            available = Counter(available_schemas)
            if available_schemas and any(available[schema] < minimum for schema, minimum in required.items()):
                continue
            result.append(RegistryPlugin(pluginId=status.plugin_id, kind=descriptor.kind, runner=descriptor.runner.value, runnable=True))
        return tuple(sorted(result, key=lambda item: item.pluginId))

    async def compatible_for_document(self, kind: str, document: dict[str, Any] | None, stage_id: str, source: str | None = None, media_type: str = "application/json") -> tuple[RegistryPlugin, ...] | ProfileValidation:
        """Derive prior port schemas server-side from a strictly parsed draft."""
        try:
            raw = source if source is not None else __import__("json").dumps(document)
            parsed = (ProfileParser if kind == "ingestion" else QueryProfileParser).parse(raw, media_type)  # type: ignore[arg-type]
            registry = await self._registry()
            available: list[tuple[str, str]] = [("opaque.bytes", "v1"), ("search.index.result", "v1")]
            target_kind = stage_id.split(".")[0]
            profiles = parsed.profiles
            for profile in profiles:
                if kind == "query":
                    for stage in profile.stages:
                        if stage.stage_id == stage_id:
                            target_kind = stage.kind
                            return await self.compatible_plugins(target_kind, tuple(available))
                        descriptor = registry.get(stage.plugin_id).descriptor
                        available.extend(port.schema for port in descriptor.output_ports)
                else:
                    for axis, value in profile.axes.items():
                        for sub in value.normalized_sub_stages:
                            if f"{axis}.{sub.stage_id}" == stage_id:
                                return await self.compatible_plugins(axis, tuple(available))
                            for candidate in sub.candidates:
                                descriptor = registry.get(candidate.plugin_id).descriptor
                                available.extend(port.schema for port in descriptor.output_ports)
            return self._invalid("STAGE_NOT_FOUND", "/stageId")
        except (ProfileError, QueryProfileError):
            return self._invalid("PROFILE_PARSE_INVALID", "/")
        except Exception:
            return self._invalid("PROFILE_COMPATIBILITY_INVALID", "/")

    async def plugin_detail(self, plugin_id: str) -> RegistryPluginDetail | None:
        registry = await self._registry()
        try:
            descriptor = registry.get(plugin_id).descriptor
            status = registry.inspect(plugin_id)[0]
        except Exception:
            return None
        def port(value):
            return RegistryPort(name=value.name, artifactType=value.artifact_type, schemaRevision=value.schema_revision, minItems=value.min_items, maxItems=value.max_items)
        schema = descriptor.configuration_schema
        example = {key: value["default"] for key, value in schema.get("properties", {}).items() if isinstance(value, dict) and "default" in value}
        runs = () if self._repository is None else tuple(
            {"runId": str(row["id"]), "engineKind": row["engine_kind"], "state": row["state"], "terminalState": row["terminal_state"], "createdAt": row["created_at"].isoformat()}
            for row in await self._repository.list_plugin_workbench_runs(plugin_id)
        )
        tests = tuple(item for item in runs if item["engineKind"] == "evaluation")
        return RegistryPluginDetail(pluginId=plugin_id, kind=descriptor.kind, runner=descriptor.runner.value, runnable=status.runnable, reason=status.reason,
            implementationDigest=descriptor.implementation_digest, inputPorts=tuple(port(x) for x in descriptor.input_ports), outputPorts=tuple(port(x) for x in descriptor.output_ports),
            configurationSchema=schema, capabilities=descriptor.capabilities, resourceHints=descriptor.resource_hints.model_dump(mode="json"), timeoutSeconds=descriptor.timeout_seconds, safeExample=example, contractTests=tests, recentRuns=runs)
