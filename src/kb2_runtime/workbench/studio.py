from __future__ import annotations

from collections.abc import Awaitable, Callable
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Protocol
from uuid import UUID

import yaml

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
    async def list_plugin_contract_test_summaries(self, plugin_ids: tuple[str, ...]) -> tuple[dict[str, Any], ...]: ...


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
            rows = await self._repository.list_profile_workspaces(kind, query)
            values = []
            for row in rows:
                hydrated = row if "source_document" in row else await self._repository.get_profile_workspace(row["profile_id"])
                document = hydrated["source_document"] if hydrated else {}
                values.append(self._summary(row["profile_id"], row["profile_kind"], document, row["updated_at"]))
            return tuple(values)
        query = query.lower()
        return tuple(
            self._summary(item.profileId, item.kind, item.document, item.updatedAt)
            for item in sorted(self._items.values(), key=lambda x: (x.kind, x.profileId))
            if (kind is None or item.kind == kind) and query in item.profileId.lower()
        )[:64]

    async def get_profile(self, profile_id: str) -> WorkspaceProfile | None:
        if self._repository is not None:
            row = await self._repository.get_profile_workspace(profile_id)
            return self._workspace(row["profile_id"], row["profile_kind"], row["source_document"], row["updated_at"]) if row else None
        return self._items.get(profile_id)

    @staticmethod
    def _canonical(document: dict[str, Any]) -> tuple[str, str]:
        raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        source = yaml.safe_dump(document, sort_keys=False, allow_unicode=False, default_flow_style=False)
        return source, hashlib.sha256(raw).hexdigest()

    @classmethod
    def _workspace(cls, profile_id: str, kind: str, document: dict[str, Any], updated_at: datetime) -> WorkspaceProfile:
        source, digest = cls._canonical(document)
        return WorkspaceProfile(profileId=profile_id, kind=kind, document=document, canonicalYaml=source,
                                documentDigest=digest, updatedAt=updated_at)  # type: ignore[arg-type]

    @classmethod
    def _summary(cls, profile_id: str, kind: str, document: dict[str, Any], updated_at: datetime) -> WorkspaceProfileSummary:
        checked_at = datetime.now(timezone.utc)
        source, digest = cls._canonical(document)
        del source
        try:
            parser = ProfileParser if kind == "ingestion" else QueryProfileParser
            parsed = parser.parse(json.dumps(document), "application/json")
            profile = next((item for item in parsed.profiles if item.profile_id == parsed.default_profile_id), parsed.profiles[0])
            if kind == "query":
                labels = [stage.kind for stage in profile.stages]
            else:
                labels = [f"{axis}.{sub.stage_id}" for axis, value in profile.axes.items() for sub in value.normalized_sub_stages]
            return WorkspaceProfileSummary(profileId=profile_id, kind=kind, stageCount=len(labels),
                stageSummary=" · ".join(labels)[:256] or None, documentDigest=digest,
                validationState="VALID", diagnosticCount=0, checkedAt=checked_at, updatedAt=updated_at)
        except (ProfileError, QueryProfileError, ValueError, TypeError):
            return WorkspaceProfileSummary(profileId=profile_id, kind=kind, stageCount=0,
                stageSummary=None, documentDigest=digest, validationState="INVALID", diagnosticCount=1,
                checkedAt=checked_at, updatedAt=updated_at)

    async def validate(self, kind: str, document: dict[str, Any] | None, compile: bool = False, search_artifact: dict[str, Any] | None = None, source: str | None = None, media_type: str = "application/json") -> ProfileValidation:
        try:
            payload = source if source is not None else __import__("json").dumps(document)
            if kind == "ingestion":
                parsed = ProfileParser.parse(payload, media_type)  # type: ignore[arg-type]
                normalized = parsed.model_dump(mode="json", exclude_none=True)
                canonical_yaml, document_digest = self._canonical(normalized)
                if not compile:
                    return ProfileValidation(valid=True, normalizedDocument=normalized, canonicalYaml=canonical_yaml, documentDigest=document_digest)
                plan = ProfileCompiler(await self._registry()).compile(parsed).get(parsed.default_profile_id)
            else:
                parsed = QueryProfileParser.parse(payload, media_type)  # type: ignore[arg-type]
                normalized = parsed.model_dump(mode="json", exclude_none=True)
                canonical_yaml, document_digest = self._canonical(normalized)
                if not compile:
                    return ProfileValidation(valid=True, normalizedDocument=normalized, canonicalYaml=canonical_yaml, documentDigest=document_digest)
                if search_artifact is None:
                    return self._invalid("SCHEMA_INCOMPATIBLE", "/searchArtifact")
                binding = QueryArtifactBinding.model_validate(search_artifact)
                plan = QueryProfileCompiler(await self._registry()).compile(parsed, binding).get(parsed.default_profile_id)
            return ProfileValidation(valid=True, normalizedDocument=normalized, canonicalYaml=canonical_yaml,
                                     documentDigest=document_digest, resolvedPlan=plan.canonical_payload, planDigest=plan.digest)
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
        value = self._workspace(profile_id, kind, checked.normalizedDocument, datetime.now(timezone.utc))
        if self._repository is not None:
            row = await self._repository.save_profile_workspace(profile_id, kind, checked.normalizedDocument)
            return self._workspace(row["profile_id"], row["profile_kind"], row["source_document"], row["updated_at"])
        self._items[profile_id] = value
        return value

    async def copy(self, profile_id: str, copy_id: str) -> WorkspaceProfile | None:
        source = await self.get_profile(profile_id)
        if source is None or await self.get_profile(copy_id) is not None:
            return None
        document = __import__("copy").deepcopy(source.document)
        if document.get("default_profile_id") == profile_id:
            document["default_profile_id"] = copy_id
        for profile in document.get("profiles", []):
            if profile.get("profile_id") == profile_id:
                profile["profile_id"] = copy_id
        reference_fields = {
            "ingestion": ("document_class_rules", "preflight_rules"),
            "query": ("selection_rules",),
        }
        for field in reference_fields.get(source.kind, ()):
            for rule in document.get(field, []):
                if rule.get("profile_id") == profile_id:
                    rule["profile_id"] = copy_id
        saved = await self.save(copy_id, source.kind, document)
        return saved if isinstance(saved, WorkspaceProfile) else None

    async def list_plugins(self, kind: str | None = None, runner: str | None = None, readiness: str | None = None, query: str = "") -> tuple[RegistryPlugin, ...]:
        registry = await self._registry()
        statuses = {x.plugin_id: x for x in registry.inspect()}
        candidates = []
        needle = query.casefold()
        for plugin_id in sorted(statuses):
            descriptor = registry.get(plugin_id).descriptor
            status = statuses[plugin_id]
            if kind and descriptor.kind != kind or runner and descriptor.runner.value != runner:
                continue
            if readiness == "available" and not status.runnable or readiness == "unavailable" and status.runnable:
                continue
            searchable = (plugin_id, descriptor.kind, *descriptor.capabilities)
            if needle and not any(needle in value.casefold() for value in searchable):
                continue
            candidates.append((descriptor, status))
        candidates = candidates[:128]
        tests: dict[str, dict[str, Any]] = {}
        if candidates and self._repository is not None and hasattr(self._repository, "list_plugin_contract_test_summaries"):
            rows = await self._repository.list_plugin_contract_test_summaries(tuple(item.plugin_id for item, _ in candidates))
            tests = {row["plugin_id"]: row for row in rows}
        result = []
        for descriptor, status in candidates:
            test = tests.get(descriptor.plugin_id)
            result.append(RegistryPlugin(
                pluginId=descriptor.plugin_id,
                kind=descriptor.kind,
                runner=descriptor.runner.value,
                runnable=status.runnable,
                reason=status.reason,
                implementationDigest=descriptor.implementation_digest,
                inputSchemas=tuple(f"{artifact_type}/{revision}" for artifact_type, revision in descriptor.input_schemas),
                outputSchemas=tuple(f"{artifact_type}/{revision}" for artifact_type, revision in descriptor.output_schemas),
                capabilities=descriptor.capabilities,
                contractTestState=(test["terminal_state"] or test["state"]) if test else None,
                contractTestRunId=str(test["id"]) if test else None,
            ))
        return tuple(result)

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
            result.append(RegistryPlugin(
                pluginId=status.plugin_id,
                kind=descriptor.kind,
                runner=descriptor.runner.value,
                runnable=True,
                implementationDigest=descriptor.implementation_digest,
                inputSchemas=tuple(f"{artifact_type}/{revision}" for artifact_type, revision in descriptor.input_schemas),
                outputSchemas=tuple(f"{artifact_type}/{revision}" for artifact_type, revision in descriptor.output_schemas),
                capabilities=descriptor.capabilities,
            ))
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
        latest_test = next((item for item in tests), None)
        return RegistryPluginDetail(pluginId=plugin_id, kind=descriptor.kind, runner=descriptor.runner.value, runnable=status.runnable, reason=status.reason,
            implementationDigest=descriptor.implementation_digest,
            inputSchemas=tuple(f"{artifact_type}/{revision}" for artifact_type, revision in descriptor.input_schemas),
            outputSchemas=tuple(f"{artifact_type}/{revision}" for artifact_type, revision in descriptor.output_schemas),
            capabilities=descriptor.capabilities,
            contractTestState=(latest_test["terminalState"] or latest_test["state"]) if latest_test else None,
            contractTestRunId=latest_test["runId"] if latest_test else None,
            inputPorts=tuple(port(x) for x in descriptor.input_ports), outputPorts=tuple(port(x) for x in descriptor.output_ports),
            configurationSchema=schema, resourceHints=descriptor.resource_hints.model_dump(mode="json"), timeoutSeconds=descriptor.timeout_seconds, safeExample=example, contractTests=tests, recentRuns=runs)
