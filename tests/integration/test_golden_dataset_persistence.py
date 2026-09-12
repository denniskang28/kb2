from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from scripts.local_runtime import RuntimeOptions, ensure_state
from tests.integration.test_trace_persistence import BASE_COMPOSE, TEST_OVERLAY, compose, docker_available, free_port, run, runtime_prefix


CREATE = r'''
import asyncio, hashlib, json
from datetime import datetime, timezone
from uuid import uuid4
from kb2_runtime.config import Settings
from kb2_runtime.evaluation.datasets.contracts import AnnotationTarget, CaseOrigin, CaseProvenance, DatasetContent, DocumentAnnotation, SourceArtifactRef
from kb2_runtime.evaluation.datasets.repository import DatasetRepository
from kb2_runtime.evaluation.datasets.service import DatasetService
from kb2_runtime.trace.contracts import ArtifactInput, EngineKind
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService, RunService
from kb2_runtime.trace.storage import ArtifactStore

async def main():
  s=Settings.from_env(); kw=dict(host=s.database_host,port=s.database_port,dbname=s.database_name,user=s.database_user,password=s.database_password())
  tr=await TraceRepository.connect(**kw); catalog=await DatasetRepository.connect(**kw); runs=RunService(tr); artifacts=ArtifactService(tr,ArtifactStore(s.artifact_root)); source=b'{"schema_version":"CanonicalDocument/v1","document_id":"doc_0123456789abcdef","metadata":{},"provenance":{"source_artifact_id":"00000000-0000-0000-0000-000000000001","source_content_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","adapter_id":"fixture@1"},"elements":[{"id":"elm_0123456789abcdef","kind":"paragraph","reading_order":0,"locator":{"kind":"html","path":"/body/p[1]","anchor":"p1"},"text":"golden text"}],"tables":[],"quality_signals":[]}'
  run=await runs.create_run(EngineKind.INGESTION,{"fixture":"golden"}); attempt,_=await runs.start_attempt(run,"source"); digest=hashlib.sha256(source).hexdigest(); source_id=(await artifacts.complete_with_outputs(run,attempt,((ArtifactInput(artifact_type="canonical.document",schema_revision="v1",content_digest=digest,byte_size=len(source),producing_plugin_id="fixture@1",configuration_digest="a"*64),source),)))[0]; await runs.finish_run(run,True)
  ref=SourceArtifactRef(id=source_id,artifact_type="canonical.document",content_digest=digest); slices={"format":"html","processing_class":"native","native_ocr":"native","structure":"prose","language":"en","question_class":"lookup","difficulty":"low","criticality":"low"}; case=DocumentAnnotation(id="ann_0123456789abcdef",source=ref,slices=slices,provenance=CaseProvenance(origin=CaseOrigin.MANUAL,operation="create",created_at=datetime(2026,1,1,tzinfo=timezone.utc)),target=AnnotationTarget(kind="text_span",element_id="elm_0123456789abcdef",start=0,end=6),label="text")
  created=await catalog.create(DatasetContent(annotations=(case,))); service=DatasetService(artifacts)
  try: await catalog.edit(created.id, DatasetContent(taxonomy=DatasetContent().taxonomy.model_copy(update={"dimensions": {**DatasetContent().taxonomy.dimensions, "format": ("forged",)}}), annotations=(case,))); raise AssertionError("taxonomy change accepted")
  except ValueError: pass
  try: await catalog.create(DatasetContent(), operation="replace"); raise AssertionError("unknown operation accepted")
  except ValueError: pass
  reviewed=await service.mark_persisted_review(catalog,created.id,1,case.id,"reviewer"); snapshot_run,snapshot=await service.create_snapshot(catalog,created.id,1,runs,artifacts); before=await artifacts.read_content(snapshot)
  edited=await catalog.edit(created.id,reviewed.model_copy(update={"annotations":(reviewed.annotations[0].model_copy(update={"label":"changed"}),)})); await service.mark_persisted_review(catalog,created.id,2,case.id,"reviewer"); _,second=await service.create_snapshot(catalog,created.id,2,runs,artifacts)
  print(json.dumps({"dataset":str(created.id),"snapshot":str(snapshot),"run":str(snapshot_run),"bytes":before.decode(),"second":str(second)})); await catalog.close(); await tr.close()
asyncio.run(main())
'''

READBACK = r'''
import asyncio,json,sys
from uuid import UUID
from kb2_runtime.config import Settings
from kb2_runtime.evaluation.datasets.repository import DatasetRepository
from kb2_runtime.trace.repositories import TraceRepository
from kb2_runtime.trace.service import ArtifactService,RunService
from kb2_runtime.trace.storage import ArtifactStore
async def main():
 s=Settings.from_env(); kw=dict(host=s.database_host,port=s.database_port,dbname=s.database_name,user=s.database_user,password=s.database_password()); tr=await TraceRepository.connect(**kw); catalog=await DatasetRepository.connect(**kw); artifacts=ArtifactService(tr,ArtifactStore(s.artifact_root)); dataset,snapshot,run,expected=UUID(sys.argv[1]),UUID(sys.argv[2]),UUID(sys.argv[3]),sys.argv[4]; assert (await artifacts.read_content(snapshot)).decode()==expected; first=await catalog.get(dataset,1); second=await catalog.get(dataset,2); trace=await RunService(tr).get_run_trace(run); assert first.content.annotations[0].reviews and second.content.annotations[0].label=="changed" and trace and trace.terminal_state.value=="SUCCEEDED"; print("GOLDEN_RESTART_OK"); await catalog.close(); await tr.close()
asyncio.run(main())
'''


@pytest.mark.integration
def test_persisted_revision_review_and_snapshot_survive_restart(tmp_path: Path) -> None:
    if not docker_available():
        pytest.skip("Docker daemon is unavailable")
    project, state, port = f"kb2-golden-{uuid.uuid4().hex[:8]}", tmp_path / "state", free_port()
    prefix = runtime_prefix(project, state, port)
    ensure_state(RuntimeOptions(project=project, environment="test", state_root=state, compose_files=(BASE_COMPOSE, TEST_OVERLAY), timeout=180, api_port=port))
    try:
        run([*prefix, "up"])
        created = json.loads(compose(project, state, "exec", "-T", "api", "python", "-c", CREATE).stdout)
        run([*prefix, "stop"]); run([*prefix, "up"])
        readback = compose(project, state, "exec", "-T", "api", "python", "-c", READBACK, created["dataset"], created["snapshot"], created["run"], created["bytes"])
        assert readback.stdout.strip() == "GOLDEN_RESTART_OK" and created["snapshot"] != created["second"]
    finally:
        subprocess.run([*prefix, "clean", "--confirm", "kb2-local-data"], capture_output=True, text=True, check=False)
