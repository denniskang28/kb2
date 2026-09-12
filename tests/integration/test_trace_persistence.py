from __future__ import annotations

import json
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from scripts.local_runtime import RuntimeOptions, ensure_state


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "local_runtime.py"
BASE_COMPOSE = ROOT / "deploy" / "local" / "compose.yaml"
TEST_OVERLAY = ROOT / "deploy" / "local" / "compose.test.yaml"


def docker_available() -> bool:
    return subprocess.run(
        ["docker", "info"], cwd=ROOT, capture_output=True, text=True, check=False
    ).returncode == 0


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def runtime_prefix(project: str, state: Path, port: int) -> list[str]:
    return [
        sys.executable,
        str(CLI),
        "--project",
        project,
        "--environment",
        "test",
        "--state-root",
        str(state),
        "--compose-file",
        str(BASE_COMPOSE),
        "--overlay",
        str(TEST_OVERLAY),
        "--api-port",
        str(port),
        "--timeout",
        "180",
    ]


def run(command: list[str], *, timeout: int = 480) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout
    )
    if result.returncode:
        raise AssertionError(
            f"command failed: exit={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def compose(project: str, state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "docker",
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(state / "compose.env"),
            "--file",
            str(BASE_COMPOSE),
            "--file",
            str(TEST_OVERLAY),
            *arguments,
        ]
    )


CREATE_FIXTURE = r'''
import asyncio, hashlib, json
from kb2_runtime.config import Settings
from kb2_runtime.trace.contracts import ArtifactInput, EngineKind, IngestionEvidence, Metric, QualitySignal, SafeError, StageResult
from kb2_runtime.trace.errors import TraceError, TraceErrorCode
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService, RunService, plan_digest
from kb2_runtime.trace.storage import ArtifactStore

async def main():
    settings = Settings.from_env()
    repository = await TraceRepository.connect(
        host=settings.database_host, port=settings.database_port,
        dbname=settings.database_name, user=settings.database_user,
        password=settings.database_password(),
    )
    runs = RunService(repository)
    artifacts = ArtifactService(repository, ArtifactStore(settings.artifact_root))
    plan = {"pipeline": "trace-integration", "revision": "v1"}
    try:
        await repository.create_plan("0" * 64, plan)
        raise AssertionError("mismatched digest was accepted")
    except TraceError as error:
        assert error.code is TraceErrorCode.PLAN_SNAPSHOT_INVALID
    synthetic_runs = []
    for engine_kind in (EngineKind.QUERY, EngineKind.EVALUATION):
        synthetic_run = await runs.create_run(engine_kind, plan)
        synthetic_attempt, _ = await runs.start_attempt(synthetic_run, "synthetic.stage")
        await runs.complete_attempt(synthetic_attempt, "generic stage")
        await runs.finish_run(synthetic_run, True)
        synthetic_trace = await runs.get_run_trace(synthetic_run)
        assert synthetic_trace and synthetic_trace.engine_kind is engine_kind
        assert len(synthetic_trace.stages) == 1
        assert synthetic_trace.stages[0].stage_key == "synthetic.stage"
        assert synthetic_trace.stages[0].outputs == ()
        synthetic_runs.append(str(synthetic_run))
    run_id = await runs.create_run(EngineKind.INGESTION, plan)
    await runs.record_ingestion_evidence(
        run_id,
        IngestionEvidence(
            candidate_profile_ids=("native", "default"),
            evaluated_rules=({"rule_id": "native", "tier": "document_class", "matched": True},),
            observables={"document_class": "native", "is_scanned": False},
            selected_profile_id="native",
            selection_tier="document_class",
            plan_digest=plan_digest(plan),
        ),
    )
    parent_attempt, _ = await runs.start_attempt(run_id, "parent")
    parent_content = b"parent-content"
    parent = ArtifactInput(
        artifact_type="opaque.bytes", schema_revision="v1",
        content_digest=hashlib.sha256(parent_content).hexdigest(), byte_size=len(parent_content),
        producing_plugin_id="test.parent", configuration_digest=hashlib.sha256(b"parent-config").hexdigest(),
        metrics=(Metric(name="z_metric", value=2.0), Metric(name="a_metric", value=1.0)),
        quality_signals=(QualitySignal(name="z_signal", status="PASS"), QualitySignal(name="a_signal", status="WARN")),
    )
    parent_id = (await artifacts.complete_with_outputs(run_id, parent_attempt, [(parent, parent_content)]))[0]
    child_attempt, _ = await runs.start_attempt(run_id, "child", (parent_id,))
    child_content = b"child-content"
    child = ArtifactInput(
        artifact_type="opaque.bytes", schema_revision="v1",
        content_digest=hashlib.sha256(child_content).hexdigest(), byte_size=len(child_content),
        producing_plugin_id="test.child", configuration_digest=hashlib.sha256(b"child-config").hexdigest(),
        parent_artifact_ids=(parent_id,),
    )
    child_id = (await artifacts.complete_with_outputs(run_id, child_attempt, [(child, child_content)]))[0]
    duplicate_input_attempt, _ = await runs.start_attempt(run_id, "duplicate-input", (parent_id, parent_id))
    await runs.complete_attempt(duplicate_input_attempt, "same artifact bound to two ports")
    manifest = await artifacts.get_artifact_manifest(parent_id)
    assert manifest and manifest.parent_artifact_ids == ()
    assert [metric.name for metric in manifest.metrics] == ["a_metric", "z_metric"]
    assert [signal.name for signal in manifest.quality_signals] == ["a_signal", "z_signal"]
    assert await artifacts.read_content(child_id) == child_content
    parent_path = settings.artifact_root / ArtifactStore(settings.artifact_root).locator(parent.content_digest)
    parent_path.write_bytes(b"tampered-parent")
    try:
        await artifacts.read_content(child_id)
        raise AssertionError("tampered ancestor remained eligible")
    except TraceError as error:
        assert error.code is TraceErrorCode.ARTIFACT_DIGEST_MISMATCH
    failed_retry, retry_number = await runs.start_attempt(run_id, "retry.stage")
    await runs.fail_attempt(
        failed_retry,
        SafeError(
            code=TraceErrorCode.STAGE_OUTPUT_INVALID,
            category="validation",
            message="retryable stage rejection",
            retryable=True,
        ),
    )
    recovered_retry, recovered_number = await runs.start_attempt(run_id, "retry.stage")
    await runs.complete_attempt(recovered_retry, "recovered")
    retry_trace = await runs.get_run_trace(run_id)
    retry_attempts = [stage for stage in retry_trace.stages if stage.stage_key == "retry.stage"]
    assert [stage.attempt_number for stage in retry_attempts] == [retry_number, recovered_number] == [1, 2]
    assert [stage.result.value for stage in retry_attempts] == ["FAILED", "SUCCEEDED"]
    assert retry_attempts[0].safe_error and retry_attempts[0].safe_error.retryable
    await runs.record_run_observations(
        run_id,
        metrics=(Metric(name="z_run_metric", value=2.0), Metric(name="a_run_metric", value=1.0)),
        quality_signals=(
            QualitySignal(name="z_run_signal", status="PASS"),
            QualitySignal(name="a_run_signal", status="WARN"),
        ),
    )
    blocked_attempt, _ = await runs.start_attempt(run_id, "blocked-output")
    await runs.finish_run(run_id, True)
    try:
        await runs.finish_run(run_id, True)
        raise AssertionError("terminal run accepted a second completion")
    except TraceError as error:
        assert error.code is TraceErrorCode.RUN_TRANSITION_INVALID
    artifact_count = await repository.connection.execute("SELECT COUNT(*) AS count FROM artifacts")
    count_before = (await artifact_count.fetchone())["count"]
    try:
        await artifacts.complete_with_outputs(run_id, blocked_attempt, [(child, child_content)])
        raise AssertionError("terminal run accepted an output commit")
    except TraceError as error:
        assert error.code is TraceErrorCode.STAGE_TRANSITION_INVALID
    artifact_count = await repository.connection.execute("SELECT COUNT(*) AS count FROM artifacts")
    assert (await artifact_count.fetchone())["count"] == count_before
    print(json.dumps({"run_id": str(run_id), "parent_id": str(parent_id), "child_id": str(child_id), "synthetic_runs": synthetic_runs, "plan_digest": plan_digest(plan)}))
    await repository.close()

asyncio.run(main())
'''


READBACK_FIXTURE = r'''
import asyncio, json, sys
from uuid import UUID
from kb2_runtime.config import Settings
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService, RunService
from kb2_runtime.trace.storage import ArtifactStore

async def main():
    settings = Settings.from_env()
    repository = await TraceRepository.connect(
        host=settings.database_host, port=settings.database_port,
        dbname=settings.database_name, user=settings.database_user,
        password=settings.database_password(),
    )
    run_id, parent_id, child_id, query_run_id, evaluation_run_id = map(UUID, sys.argv[1:6])
    trace = await RunService(repository).get_run_trace(run_id)
    manifest = await ArtifactService(repository, ArtifactStore(settings.artifact_root)).get_artifact_manifest(parent_id)
    assert trace and trace.terminal_state.value == "SUCCEEDED" and len(trace.stages) == 6
    assert any(stage.stage_key == "blocked-output" and stage.result is None for stage in trace.stages)
    assert [metric.name for metric in trace.metrics] == ["a_run_metric", "z_run_metric"]
    assert [signal.name for signal in trace.quality_signals] == ["a_run_signal", "z_run_signal"]
    retry_attempts = [stage for stage in trace.stages if stage.stage_key == "retry.stage"]
    assert len(retry_attempts) == 2
    assert retry_attempts[0].safe_error and retry_attempts[0].safe_error.retryable
    assert retry_attempts[0].safe_error.code.value == "STAGE_OUTPUT_INVALID"
    assert manifest and [metric.name for metric in manifest.metrics] == ["a_metric", "z_metric"]
    assert [signal.name for signal in manifest.quality_signals] == ["a_signal", "z_signal"]
    assert child_id in {output.id for stage in trace.stages for output in stage.outputs}
    child_stage = next(stage for stage in trace.stages if stage.stage_key == "child")
    assert [item.id for item in child_stage.inputs] == [parent_id]
    duplicate_input_stage = next(stage for stage in trace.stages if stage.stage_key == "duplicate-input")
    assert [item.id for item in duplicate_input_stage.inputs] == [parent_id, parent_id]
    assert trace.ingestion_evidence
    assert trace.ingestion_evidence.selected_profile_id == "native"
    assert trace.ingestion_evidence.evaluated_rules[0]["matched"] is True
    synthetic_traces = [await RunService(repository).get_run_trace(run_id) for run_id in (query_run_id, evaluation_run_id)]
    assert all(trace and len(trace.stages) == 1 and trace.stages[0].outputs == () for trace in synthetic_traces)
    assert {trace.engine_kind.value for trace in synthetic_traces if trace} == {"query", "evaluation"}
    print("TRACE_RESTART_READBACK_OK")
    await repository.close()

asyncio.run(main())
'''


@pytest.mark.integration
def test_trace_migration_lifecycle_lineage_and_restart(tmp_path: Path) -> None:
    if not docker_available():
        pytest.skip("Docker daemon is unavailable")

    project = f"kb2-trace-{uuid.uuid4().hex[:8]}"
    state = tmp_path / project
    prefix = runtime_prefix(project, state, free_port())
    ensure_state(
        RuntimeOptions(
            project=project,
            environment="test",
            state_root=state,
            compose_files=(BASE_COMPOSE, TEST_OVERLAY),
            timeout=180,
            api_port=int(prefix[prefix.index("--api-port") + 1]),
        )
    )
    try:
        run([*prefix, "up"])
        created = json.loads(compose(project, state, "exec", "-T", "api", "python", "-c", CREATE_FIXTURE).stdout)
        run([*prefix, "stop"])
        run([*prefix, "up"])
        readback = compose(
            project,
            state,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            READBACK_FIXTURE,
            created["run_id"],
            created["parent_id"],
            created["child_id"],
            *created["synthetic_runs"],
        )
        assert readback.stdout.strip() == "TRACE_RESTART_READBACK_OK"
    finally:
        subprocess.run(
            [*prefix, "clean", "--confirm", "kb2-local-data"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
