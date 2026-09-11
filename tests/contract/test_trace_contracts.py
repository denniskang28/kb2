from __future__ import annotations

import hashlib
import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kb2_runtime.trace.contracts import ArtifactInput, ArtifactReference, EngineKind, QualitySignal, SafeError, StageResult
from kb2_runtime.trace.errors import TraceError, TraceErrorCode
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.schemas import schema_is_supported
from kb2_runtime.trace.service import plan_digest
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


def test_schema_catalog_is_closed_until_a_later_story_extends_it() -> None:
    assert schema_is_supported("opaque.bytes", "v1")
    assert not schema_is_supported("canonical.document", "v1")


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


def test_parent_lineage_contract_rejects_duplicates() -> None:
    content = b"x"
    parent = uuid4()
    with pytest.raises(ValidationError, match="unique"):
        ArtifactInput.model_validate(
            {**manifest(content).model_dump(), "parent_artifact_ids": (parent, parent)}
        )
