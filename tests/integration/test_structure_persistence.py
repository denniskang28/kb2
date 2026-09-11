from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.integration.test_trace_persistence import (
    BASE_COMPOSE,
    CLI,
    ROOT,
    TEST_OVERLAY,
    docker_available,
    free_port,
    runtime_prefix,
    run,
)
from scripts.local_runtime import RuntimeOptions, ensure_state


TABLE_FIXTURE = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_text(encoding="utf-8")


def create_script() -> str:
    return f'''
import asyncio, hashlib, json
from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.config import Settings
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactInput, EngineKind
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService, RunService
from kb2_runtime.trace.storage import ArtifactStore

async def main():
    settings = Settings.from_env()
    repository = await TraceRepository.connect(host=settings.database_host, port=settings.database_port, dbname=settings.database_name, user=settings.database_user, password=settings.database_password())
    runs, artifacts = RunService(repository), ArtifactService(repository, ArtifactStore(settings.artifact_root))
    content = {TABLE_FIXTURE!r}.encode("utf-8")
    CanonicalDocument.model_validate_json(content)
    run_id = await runs.create_run(EngineKind.INGESTION, {{"pipeline": "structure-persistence", "revision": "v1"}})
    source_attempt, _ = await runs.start_attempt(run_id, "canonical-source")
    source = ArtifactInput(artifact_type="canonical.document", schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), producing_plugin_id="normalizer.fixture@1", configuration_digest="a" * 64)
    source_id = (await artifacts.complete_with_outputs(run_id, source_attempt, [(source, content)]))[0]
    executor = PluginExecutor(bootstrap_registry(), {{RunnerType.IN_PROCESS: InProcessRunner()}}, runs, artifacts)
    structured_id = (await executor.invoke(run_id, "structure", "structure.canonical@1", {{"strategy": "table"}}, (source_id,)))[0]
    structured = CanonicalDocument.model_validate_json(await artifacts.read_content(structured_id))
    table = structured.tables[0]
    assert table.cells[0].column_span == 2 and table.caption_element_id and table.related_element_ids
    print(json.dumps({{"run_id": str(run_id), "structured_id": str(structured_id)}}))
    await repository.close()

asyncio.run(main())
'''


READBACK_SCRIPT = r'''
import asyncio, sys
from uuid import UUID
from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.config import Settings
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService
from kb2_runtime.trace.storage import ArtifactStore

async def main():
    settings = Settings.from_env()
    repository = await TraceRepository.connect(host=settings.database_host, port=settings.database_port, dbname=settings.database_name, user=settings.database_user, password=settings.database_password())
    artifacts = ArtifactService(repository, ArtifactStore(settings.artifact_root))
    artifact_id = UUID(sys.argv[1])
    document = CanonicalDocument.model_validate_json(await artifacts.read_content(artifact_id))
    table = document.tables[0]
    assert table.locator.kind == "spreadsheet"
    assert [(cell.row, cell.column, cell.row_span, cell.column_span) for cell in table.cells][0] == (0, 0, 1, 2)
    assert table.header_cell_ids and table.caption_element_id and table.related_element_ids
    print("STRUCTURE_TABLE_RESTART_READBACK_OK")
    await repository.close()

asyncio.run(main())
'''


@pytest.mark.integration
def test_table_structure_artifact_persists_and_restarts(tmp_path: Path) -> None:
    if not docker_available():
        pytest.skip("Docker daemon is unavailable")
    project = f"kb2-structure-{uuid.uuid4().hex[:8]}"
    state = tmp_path / project
    prefix = runtime_prefix(project, state, free_port())
    ensure_state(RuntimeOptions(project=project, environment="test", state_root=state, compose_files=(BASE_COMPOSE, TEST_OVERLAY), timeout=180, api_port=int(prefix[prefix.index("--api-port") + 1])))
    try:
        run([*prefix, "up"])
        created = json.loads(run(["docker", "compose", "--project-name", project, "--env-file", str(state / "compose.env"), "--file", str(BASE_COMPOSE), "--file", str(TEST_OVERLAY), "exec", "-T", "api", "python", "-c", create_script()]).stdout)
        run([*prefix, "stop"])
        run([*prefix, "up"])
        readback = run(["docker", "compose", "--project-name", project, "--env-file", str(state / "compose.env"), "--file", str(BASE_COMPOSE), "--file", str(TEST_OVERLAY), "exec", "-T", "api", "python", "-c", READBACK_SCRIPT, created["structured_id"]])
        assert readback.stdout.strip() == "STRUCTURE_TABLE_RESTART_READBACK_OK"
    finally:
        subprocess.run([*prefix, "clean", "--confirm", "kb2-local-data"], cwd=ROOT, capture_output=True, text=True, check=False, timeout=180)
