from __future__ import annotations

import hashlib
import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from kb2_runtime.trace.contracts import ArtifactInput, ArtifactManifest, ArtifactReference, DocumentSubmissionInput, EngineKind, IngestionEvidence, QualitySignal, SafeError, StageResult, metadata_contains_sensitive_text
from kb2_runtime.trace.errors import TraceError, TraceErrorCode
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.schemas import schema_is_supported
from kb2_runtime.trace.service import ArtifactService, plan_digest
from kb2_runtime.trace.storage import ArtifactStore


CANARY_SECRET = "CANARY-secret-value"
CANARY_PAYLOAD = "CANARY-provider-payload"


class CapturingCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.executions: list[tuple[str, tuple[Any, ...] | None]] = []

    async def __aenter__(self) -> "CapturingCursor":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: str, parameters: tuple[Any, ...] | None = None) -> None:
        self.executions.append((statement, parameters))

    async def fetchone(self) -> dict[str, Any]:
        return self.rows.pop(0)

    async def fetchall(self) -> list[dict[str, Any]]:
        return []


class CapturingConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_instance = CapturingCursor(rows)
        self.commits = 0

    def cursor(self) -> CapturingCursor:
        return self.cursor_instance

    async def commit(self) -> None:
        self.commits += 1


def manifest(content: bytes) -> ArtifactInput:
    return ArtifactInput(
        artifact_type="opaque.bytes",
        schema_revision="v1",
        content_digest=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        producing_plugin_id="test.plugin",
        configuration_digest=hashlib.sha256(b"config").hexdigest(),
    )


def test_artifact_contract_requires_digest_and_bounded_safe_metadata() -> None:
    content = b"private provider payload"
    item = manifest(content)
    assert item.content_digest == hashlib.sha256(content).hexdigest()
    with pytest.raises(ValidationError):
        ArtifactInput.model_validate({**item.model_dump(), "content_digest": "bad"})
    with pytest.raises(ValidationError):
        SafeError(code="ARTIFACT_DIGEST_MISMATCH", category="storage", message="x", details={"bad key!": "x"})


def test_trace_metadata_redacts_credential_and_provider_payload_canaries() -> None:
    item = manifest(b"x").model_copy(update={"summary": CANARY_PAYLOAD})
    # `model_copy` intentionally skips Pydantic validation; use a normal boundary construction.
    item = ArtifactInput.model_validate({**item.model_dump(), "summary": CANARY_PAYLOAD})
    error = SafeError(
        code="ARTIFACT_DIGEST_MISMATCH",
        category="storage",
        message=CANARY_SECRET,
        details={"provider": CANARY_PAYLOAD, "retry": "safe"},
    )
    assert item.summary == "[redacted]"
    assert error.message == "[redacted]"
    assert error.details == {"provider": "[redacted]", "retry": "safe"}
    serialized = {"artifact": item.model_dump(mode="json"), "error": error.model_dump(mode="json")}
    assert CANARY_SECRET not in str(serialized)
    assert CANARY_PAYLOAD not in str(serialized)


def test_document_submission_metadata_is_a_safe_bounded_leaf() -> None:
    safe = DocumentSubmissionInput(display_filename="  sample   report.pdf  ", media_type="Application/PDF")
    assert safe.display_filename == "sample report.pdf"
    assert safe.media_type == "application/pdf"
    assert DocumentSubmissionInput(display_filename=CANARY_SECRET + ".pdf", media_type="application/pdf").display_filename == "[redacted]"
    for filename in ("../secret.pdf", "folder\\secret.pdf", "line\nfeed.pdf"):
        with pytest.raises(ValidationError):
            DocumentSubmissionInput(display_filename=filename, media_type="application/pdf")
    with pytest.raises(ValidationError):
        DocumentSubmissionInput(display_filename="sample.pdf", media_type="not-a-mime")


def test_all_trace_summary_and_signal_text_boundaries_redact_canaries() -> None:
    reference = ArtifactReference(
        id=uuid4(), artifact_type="opaque.bytes", schema_revision="v1",
        content_digest=hashlib.sha256(b"x").hexdigest(), byte_size=1, summary=CANARY_PAYLOAD,
    )
    signal = QualitySignal(name="quality", status="WARN", value=CANARY_SECRET, summary=CANARY_PAYLOAD)
    assert reference.summary == "[redacted]"
    assert signal.value == "[redacted]"
    assert signal.summary == "[redacted]"


def test_run_observations_use_the_same_bounded_metric_and_signal_contracts() -> None:
    signal = QualitySignal(name="run-quality", status="PASS", value=1, summary="local check")
    assert signal.name == "run-quality"
    with pytest.raises(ValidationError):
        QualitySignal(name="x" * 65, status="PASS")


def test_repository_persists_validated_ingestion_evidence_with_its_plan_digest() -> None:
    async def persist() -> CapturingConnection:
        run_id = uuid4()
        connection = CapturingConnection([{"id": run_id}])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        digest = plan_digest({"profile": "native", "stages": []})
        await repository.record_ingestion_evidence(
            run_id,
            IngestionEvidence(
                candidate_profile_ids=("native", "default"),
                evaluated_rules=({"rule_id": "native", "tier": "document_class", "matched": True},),
                observables={"document_class": "native", "is_scanned": False},
                selected_profile_id="native",
                selection_tier="document_class",
                plan_digest=digest,
            ),
        )
        return connection

    connection = asyncio.run(persist())
    statement, parameters = connection.cursor_instance.executions[-1]
    assert "INSERT INTO ingestion_run_evidence" in statement
    assert parameters is not None
    assert parameters[1].obj["plan_digest"] == plan_digest({"profile": "native", "stages": []})


def test_repository_rejects_sensitive_resolver_evidence_while_exempting_only_plan_digest() -> None:
    async def persist() -> CapturingConnection:
        run_id = uuid4()
        connection = CapturingConnection([])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        with pytest.raises(TraceError) as raised:
            await repository.record_ingestion_evidence(
                run_id,
                IngestionEvidence(
                    candidate_profile_ids=("native",),
                    evaluated_rules=(),
                    observables={"document_class": CANARY_SECRET},
                    selected_profile_id="native",
                    selection_tier="default",
                    plan_digest=plan_digest({"profile": "native", "stages": []}),
                ),
            )
        assert raised.value.code is TraceErrorCode.PLAN_SNAPSHOT_INVALID
        return connection

    connection = asyncio.run(persist())
    assert not connection.cursor_instance.executions


def test_repository_persists_failed_invalidation_of_a_published_output_attempt() -> None:
    async def invalidate() -> CapturingConnection:
        connection = CapturingConnection([{"state": "SUCCEEDED", "terminal_state": None}])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        await repository.invalidate_attempt(
            uuid4(),
            SafeError(
                code=TraceErrorCode.STAGE_OUTPUT_INVALID,
                category="validation",
                message="published output did not match the pinned contract",
            ),
        )
        return connection

    connection = asyncio.run(invalidate())
    update, parameters = connection.cursor_instance.executions[-1]
    assert "UPDATE stage_attempts SET state='FAILED', result='FAILED'" in update
    assert parameters is not None
    assert parameters[1].obj["code"] == TraceErrorCode.STAGE_OUTPUT_INVALID.value
    assert connection.commits == 1


def test_repository_normalizes_model_construct_values_before_persistence() -> None:
    async def persist() -> CapturingConnection:
        run_id, attempt_id = uuid4(), uuid4()
        connection = CapturingConnection([{"state": "RUNNING", "run_id": run_id, "terminal_state": None}, {"state": "RUNNING", "terminal_state": None}])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        raw_signal = QualitySignal.model_construct(
            name="quality", status="WARN", value=CANARY_SECRET, summary=CANARY_PAYLOAD
        )
        raw_manifest = ArtifactInput.model_construct(
            artifact_type="opaque.bytes", schema_revision="v1", content_digest=hashlib.sha256(b"x").hexdigest(),
            byte_size=1, producing_plugin_id="test.plugin", configuration_digest=hashlib.sha256(b"config").hexdigest(),
            summary=CANARY_PAYLOAD, parent_artifact_ids=(), metrics=(), quality_signals=(raw_signal,),
        )
        await repository.complete_outputs(attempt_id, run_id, [(uuid4(), raw_manifest, "sha256/aa/x")], CANARY_PAYLOAD, signals=(raw_signal,))
        raw_error = SafeError.model_construct(
            code=TraceErrorCode.ARTIFACT_DIGEST_MISMATCH, category="storage", message=CANARY_SECRET,
            retryable=False, details={"provider": CANARY_PAYLOAD},
        )
        await repository.finish_attempt(attempt_id, StageResult.FAILED, CANARY_PAYLOAD, raw_error, signals=(raw_signal,))
        return connection

    connection = asyncio.run(persist())
    persisted_parameters = str(connection.cursor_instance.executions)
    assert CANARY_SECRET not in persisted_parameters
    assert CANARY_PAYLOAD not in persisted_parameters
    assert "[redacted]" in persisted_parameters


def test_repository_registers_document_in_the_source_publication_transaction() -> None:
    async def persist() -> CapturingConnection:
        run_id, attempt_id = uuid4(), uuid4()
        connection = CapturingConnection([{
            "state": "RUNNING", "run_id": run_id, "terminal_state": None,
            "stage_key": "ingestion.source", "engine_kind": "ingestion",
        }])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        await repository.complete_outputs(
            attempt_id, run_id, [(uuid4(), manifest(b"source"), "sha256/aa/source")], "source",
            document_submission=DocumentSubmissionInput(display_filename="source.pdf", media_type="application/pdf"),
        )
        return connection

    connection = asyncio.run(persist())
    statements = [statement for statement, _ in connection.cursor_instance.executions]
    assert next(index for index, value in enumerate(statements) if "INSERT INTO artifacts" in value) < next(
        index for index, value in enumerate(statements) if "INSERT INTO document_submissions" in value
    )
    registration = next(parameters for statement, parameters in connection.cursor_instance.executions if "INSERT INTO document_submissions" in statement)
    assert registration is not None and registration[2:] == ("source.pdf", "application/pdf")
    assert connection.commits == 1


def test_repository_rejects_document_registration_from_non_source_stage() -> None:
    async def reject() -> CapturingConnection:
        run_id, attempt_id = uuid4(), uuid4()
        connection = CapturingConnection([{
            "state": "RUNNING", "run_id": run_id, "terminal_state": None,
            "stage_key": "extraction.parse", "engine_kind": "ingestion",
        }])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        with pytest.raises(TraceError) as raised:
            await repository.complete_outputs(
                attempt_id, run_id, [(uuid4(), manifest(b"source"), "sha256/aa/source")], "source",
                document_submission=DocumentSubmissionInput(display_filename="source.pdf", media_type="application/pdf"),
            )
        assert raised.value.code is TraceErrorCode.STAGE_OUTPUT_INVALID
        return connection

    connection = asyncio.run(reject())
    assert not any("INSERT INTO artifacts" in statement for statement, _ in connection.cursor_instance.executions)
    assert connection.commits == 0


def test_document_list_latest_output_requires_same_run_processing_attempt() -> None:
    async def capture_query() -> CapturingConnection:
        connection = CapturingConnection([])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        await repository.list_document_submissions(25)
        return connection

    connection = asyncio.run(capture_query())
    statement, _ = connection.cursor_instance.executions[-1]
    assert "candidate.producing_run_id=r.id" in statement
    assert "attempt.run_id=r.id" in statement
    assert "attempt.stage_key<>'ingestion.source'" in statement


def test_exact_document_registration_lookup_is_empty_safe_deduplicated_and_bounded() -> None:
    async def capture() -> CapturingConnection:
        connection = CapturingConnection([])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        assert await repository.get_document_submissions_by_source_ids(()) == ()
        identifiers = [uuid4() for _ in range(70)]
        await repository.get_document_submissions_by_source_ids([identifiers[0], identifiers[0], *identifiers[1:]])
        return connection

    connection = asyncio.run(capture())
    assert len(connection.cursor_instance.executions) == 1
    statement, parameters = connection.cursor_instance.executions[0]
    assert "d.source_artifact_id=ANY(%s)" in statement
    assert parameters is not None and len(parameters[0]) == 64
    assert len(set(parameters[0])) == 64


def test_document_artifact_manifest_query_is_exact_run_scoped_and_success_only() -> None:
    async def capture() -> tuple[CapturingConnection, object, object]:
        source_id, run_id = uuid4(), uuid4()
        connection = CapturingConnection([])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        assert await repository.list_document_artifact_manifests(source_id, run_id, limit=999) == ()
        return connection, source_id, run_id

    connection, source_id, run_id = asyncio.run(capture())
    statement, parameters = connection.cursor_instance.executions[0]
    normalized = " ".join(statement.split())
    assert normalized.startswith("WITH RECURSIVE descendants AS")
    assert "d.source_artifact_id=%s AND d.run_id=%s" in normalized
    assert "a.producing_run_id=%s AND s.run_id=%s" in normalized
    assert "child.producing_run_id=%s AND s.run_id=%s" in normalized
    assert normalized.count("s.state='SUCCEEDED' AND s.result='SUCCEEDED'") == 2
    assert "JOIN artifact_lineage l ON l.parent_artifact_id=parent.id" in normalized
    assert "ORDER BY a.created_at, a.id LIMIT %s" in normalized
    assert "content_digest" not in normalized and "display_filename" not in normalized
    assert parameters == (source_id, run_id, run_id, run_id, run_id, run_id, 128)


def test_document_artifact_manifest_query_consumes_fetched_ids_and_filters_missing_rows() -> None:
    async def exercise() -> tuple[tuple[ArtifactManifest, ...], list[object]]:
        source_id, run_id, first_id, missing_id, second_id = (uuid4() for _ in range(5))

        class ResultsCursor(CapturingCursor):
            async def fetchall(self) -> list[dict[str, Any]]:
                return [{"id": first_id}, {"id": missing_id}, {"id": second_id}]

        connection = CapturingConnection([])
        connection.cursor_instance = ResultsCursor([])

        def projected(identifier: object) -> ArtifactManifest:
            return ArtifactManifest(
                id=identifier, artifact_type="opaque.bytes", schema_revision="v1",
                content_digest="a" * 64, byte_size=1, storage_locator=f"sha256/aa/{identifier}",
                producing_run_id=run_id, producing_stage_attempt_id=uuid4(),
                producing_plugin_id="fixture@1", configuration_digest="b" * 64, summary="fixture",
            )

        class Repository(TraceRepository):
            requested: list[object] = []

            async def get_artifact_manifest(self, artifact_id):
                self.requested.append(artifact_id)
                return None if artifact_id == missing_id else projected(artifact_id)

        repository = Repository(connection)  # type: ignore[arg-type]
        result = await repository.list_document_artifact_manifests(source_id, run_id)
        return result, repository.requested

    result, requested = asyncio.run(exercise())
    assert [item.id for item in result] == [requested[0], requested[2]]
    assert len(requested) == 3


@pytest.mark.parametrize(
    ("identifier_values", "missing_values", "expected_values"),
    (
        ((), (), ()),
        ((1,), (), (1,)),
        ((3, 2, 1), (), (3, 2, 1)),
        ((3, 2, 1), (2,), (3, 1)),
    ),
)
def test_artifact_manifest_catalog_hydrates_bounded_identifiers_sequentially(
    identifier_values: tuple[int, ...],
    missing_values: tuple[int, ...],
    expected_values: tuple[int, ...],
) -> None:
    async def exercise() -> tuple[tuple[ArtifactManifest, ...], list[object], CapturingConnection]:
        identifiers = tuple(UUID(int=value) for value in identifier_values)
        missing = {UUID(int=value) for value in missing_values}

        class ResultsCursor(CapturingCursor):
            open = False

            async def __aenter__(self) -> "ResultsCursor":
                self.open = True
                return self

            async def __aexit__(self, *args: object) -> None:
                self.open = False

            async def fetchall(self) -> list[dict[str, Any]]:
                return [{"id": identifier} for identifier in identifiers]

        connection = CapturingConnection([])
        cursor = ResultsCursor([])
        connection.cursor_instance = cursor
        producing_run_id, producing_stage_attempt_id = uuid4(), uuid4()

        class Repository(TraceRepository):
            requested: list[object] = []
            hydration_active = False

            async def get_artifact_manifest(self, artifact_id):
                assert not cursor.open
                assert not self.hydration_active
                self.hydration_active = True
                self.requested.append(artifact_id)
                await asyncio.sleep(0)
                self.hydration_active = False
                if artifact_id in missing:
                    return None
                return ArtifactManifest(
                    id=artifact_id,
                    artifact_type="search.index.result",
                    schema_revision="v1",
                    content_digest="a" * 64,
                    byte_size=1,
                    storage_locator=f"sha256/aa/{artifact_id}",
                    producing_run_id=producing_run_id,
                    producing_stage_attempt_id=producing_stage_attempt_id,
                    producing_plugin_id="index.fixture@1",
                    configuration_digest="b" * 64,
                    summary="fixture index",
                )

        repository = Repository(connection)  # type: ignore[arg-type]
        result = await repository.list_artifact_manifests("search.index.result", "v1", 17)
        return result, repository.requested, connection

    result, requested, connection = asyncio.run(exercise())
    assert isinstance(result, tuple)
    assert [item.id.int for item in result] == list(expected_values)
    assert [identifier.int for identifier in requested] == list(identifier_values)
    statement, parameters = connection.cursor_instance.executions[0]
    normalized = " ".join(statement.split())
    assert normalized == (
        "SELECT id FROM artifacts WHERE artifact_type=%s AND schema_revision=%s "
        "ORDER BY id DESC LIMIT %s"
    )
    assert parameters == ("search.index.result", "v1", 17)


def test_artifact_service_rolls_back_when_document_catalog_insert_fails() -> None:
    class Connection:
        rollbacks = 0

        async def rollback(self) -> None:
            self.rollbacks += 1

    class Repository:
        def __init__(self) -> None:
            self.connection = Connection()
            self.failures = []

        async def complete_outputs(self, *args, **kwargs) -> None:
            assert kwargs["document_submission"].display_filename == "duplicate.pdf"
            raise RuntimeError("document_submissions run_id unique violation")

        async def finish_attempt(self, attempt_id, result, summary, error) -> None:
            self.failures.append((attempt_id, result, summary, error))

    class Store:
        def publish(self, content, digest, size) -> str:
            assert len(content) == size and hashlib.sha256(content).hexdigest() == digest
            return "sha256/aa/source"

    async def publish() -> Repository:
        repository = Repository()
        service = ArtifactService(repository, Store())  # type: ignore[arg-type]
        with pytest.raises(TraceError) as raised:
            await service.complete_with_outputs(
                uuid4(), uuid4(), [(manifest(b"source"), b"source")],
                document_submission=DocumentSubmissionInput(display_filename="duplicate.pdf", media_type="application/pdf"),
            )
        assert raised.value.code is TraceErrorCode.TRACE_STORAGE_FAILURE
        return repository

    repository = asyncio.run(publish())
    assert repository.connection.rollbacks == 1
    assert len(repository.failures) == 1
    assert repository.failures[0][1] is StageResult.FAILED
    assert repository.failures[0][3].code is TraceErrorCode.TRACE_STORAGE_FAILURE


def test_repository_rejects_output_commit_after_run_is_terminal() -> None:
    async def complete_after_terminal_run() -> CapturingConnection:
        run_id, attempt_id = uuid4(), uuid4()
        connection = CapturingConnection([{"state": "RUNNING", "run_id": run_id, "terminal_state": "SUCCEEDED"}])
        repository = TraceRepository(connection)  # type: ignore[arg-type]
        with pytest.raises(TraceError, match="STAGE_TRANSITION_INVALID"):
            await repository.complete_outputs(
                attempt_id, run_id, [(uuid4(), manifest(b"x"), "sha256/aa/x")], "completed"
            )
        return connection

    connection = asyncio.run(complete_after_terminal_run())
    assert len(connection.cursor_instance.executions) == 1
    assert "SELECT s.state, s.run_id, r.terminal_state" in connection.cursor_instance.executions[0][0]


def test_schema_catalog_includes_only_the_supported_trace_and_canonical_pairs() -> None:
    assert schema_is_supported("opaque.bytes", "v1")
    assert schema_is_supported("provider.parse-result-fixture", "v1")
    assert schema_is_supported("canonical.document", "v1")
    assert not schema_is_supported("provider.sdk-object", "v1")


def test_artifact_store_is_content_addressed_immutable_and_revalidates(tmp_path: Path) -> None:
    content = b"CANARY-raw-provider-payload"
    digest = hashlib.sha256(content).hexdigest()
    store = ArtifactStore(tmp_path)
    locator = store.publish(content, digest, len(content))
    assert store.read(digest, locator) == content
    assert "CANARY" not in locator
    with pytest.raises(TraceError, match="ARTIFACT_DIGEST_MISMATCH"):
        store.publish(b"changed", digest, len(b"changed"))
    (tmp_path / locator).write_bytes(b"tampered")
    with pytest.raises(TraceError, match="ARTIFACT_DIGEST_MISMATCH"):
        store.read(digest, locator)


def test_artifact_store_rejects_locator_traversal_and_missing_content(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    digest = hashlib.sha256(b"x").hexdigest()
    with pytest.raises(TraceError, match="ARTIFACT_CONTENT_MISSING"):
        store.read(digest, "../../outside")


def test_plan_digest_is_canonical_bounded_and_engine_types_are_closed() -> None:
    assert plan_digest({"b": 2, "a": 1}) == plan_digest({"a": 1, "b": 2})
    with pytest.raises(TraceError, match="PLAN_SNAPSHOT_INVALID"):
        plan_digest({"callable": lambda: None})
    assert {kind.value for kind in EngineKind} == {"ingestion", "query", "evaluation"}


def test_plan_metadata_allows_identity_digests_but_not_secrets() -> None:
    assert not metadata_contains_sensitive_text({"implementation_digest": "a" * 64})
    assert metadata_contains_sensitive_text({"configuration": {"api_key": CANARY_SECRET}})


def test_plan_metadata_allows_registered_provider_labels_only_for_plan_snapshots() -> None:
    plan = {
        "plugin_id": "generator.deepseek@1",
        "configuration": {"model": "deepseek-v4-flash"},
    }
    assert metadata_contains_sensitive_text(plan)
    assert not metadata_contains_sensitive_text(plan, allow_registered_provider_labels=True)
    assert metadata_contains_sensitive_text(
        {"configuration": {"provider_response": "deepseek response body"}},
        allow_registered_provider_labels=True,
    )


def test_repository_persists_plan_with_registered_provider_labels() -> None:
    async def persist() -> CapturingConnection:
        connection = CapturingConnection([None])  # type: ignore[list-item]
        plan = {
            "plugin_id": "generator.deepseek@1",
            "configuration": {"model": "deepseek-v4-flash"},
        }
        await TraceRepository(connection).create_plan(plan_digest(plan), plan)  # type: ignore[arg-type]
        return connection

    connection = asyncio.run(persist())
    assert any("INSERT INTO execution_plan_snapshots" in statement for statement, _ in connection.cursor_instance.executions)
    assert connection.commits == 1


def test_parent_lineage_contract_rejects_duplicates() -> None:
    content = b"x"
    parent = uuid4()
    with pytest.raises(ValidationError, match="unique"):
        ArtifactInput.model_validate(
            {**manifest(content).model_dump(), "parent_artifact_ids": (parent, parent)}
        )
