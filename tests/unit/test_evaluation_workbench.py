import asyncio
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from kb2_runtime.evaluation.datasets.contracts import DatasetContent, GoldenDataset
from kb2_runtime.evaluation.runs.contracts import (
    ArtifactBinding,
    EvaluationManifest,
    EvaluationSubject,
    GateResult,
    LayeredReport,
    NavigationIndex,
    OperationReport,
    PlanIdentity,
    RuntimeSummary,
    digest,
)
from kb2_runtime.workbench.evaluation import EvaluationWorkbenchService


def _dataset() -> GoldenDataset:
    content = DatasetContent()
    return GoldenDataset(
        id=UUID(int=1), revision_id=UUID(int=2), revision=1, content=content,
        content_digest=hashlib.sha256(json.dumps(content.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        operation="create", created_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
    )


def test_dataset_catalog_and_edit_are_engine_owned() -> None:
    class Datasets:
        item = _dataset()
        async def list_latest(self, _query=""):
            return (self.item,)
        async def get(self, _id, _revision):
            return self.item
        async def edit(self, _id, content):
            self.item = self.item.model_copy(update={"revision": 2, "content": content})
            return self.item
    class Traces:
        async def list_evaluation_workbench_runs(self): return ()
    class Artifacts:
        async def get_artifact_manifest(self, _id): return None
    async def exercise():
        service = EvaluationWorkbenchService(Datasets(), Traces(), Artifacts())
        catalog = await service.datasets()
        assert catalog == [{"id": str(UUID(int=1)), "revision": 1, "revisionId": str(UUID(int=2)), "digest": _dataset().content_digest,
                            "createdAt": "2026-09-13T00:00:00+00:00", "annotationCount": 0, "queryCaseCount": 0, "reviewedCount": 0, "caseCount": 0}]
        changed = await service.edit(UUID(int=1), DatasetContent().model_dump(mode="json"))
        assert changed["valid"] and changed["dataset"]["revision"] == 2
    asyncio.run(exercise())


def test_run_projection_keeps_manifest_report_navigation_and_safe_unavailable_artifacts() -> None:
    run_id, manifest_id, report_id, navigation_id, broken_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    case_id, metric_id = "qcase_0123456789abcdef", "metric.answer.fixture@1"
    plan = {"plugin": "fixture.plugin@1"}
    binding = ArtifactBinding(role="evidence", artifact_id=uuid4(), artifact_type="evidence.set", content_digest="c" * 64, case_id=case_id)
    subject = lambda name: EvaluationSubject(
        subject=name, ingestion_plan=plan, ingestion_plan_digest=digest(plan), query_plan=plan,
        query_plan_digest=digest(plan), bindings=(binding,),
        declared_identities=(PlanIdentity(plugin_id="fixture.plugin@1", implementation_digest="d" * 64),),
    )
    manifest = EvaluationManifest(
        dataset_snapshot_id=uuid4(), dataset_snapshot_digest="a" * 64, taxonomy_digest="b" * 64,
        input_catalog_digest="e" * 64, case_ids=(case_id,), subjects=(subject("baseline"), subject("candidate")),
        metric_ids=(metric_id,), runtime=RuntimeSummary(runtime_digest="1" * 64, package_digest="2" * 64,
        implementation_digest="3" * 64, os_family="linux", architecture="x86_64", resource_sampler_version="fixture.v1"),
    )
    metric_artifact_id = uuid4()
    report = LayeredReport(
        manifest_artifact_id=manifest_id, manifest_digest="f" * 64, report_ids=(metric_artifact_id,),
        layers={name: ((metric_artifact_id,) if name == "answer" else ()) for name in ("ingestion", "retrieval", "answer", "citation", "decision", "judge", "latency", "resources")},
        gate_results=(GateResult(gate_id="gate.answer", state="FAIL", reason="fixture", selected_report_ids=(metric_artifact_id,), sample_count=1),),
        operation=OperationReport(elapsed_ms=1, availability="AVAILABLE"),
    )
    navigation = NavigationIndex(evaluation_report_id=report_id, evaluation_run_id=run_id)
    payloads = {
        manifest_id: manifest.model_dump(mode="json", exclude_none=True),
        report_id: report.model_dump(mode="json", exclude_none=True),
        navigation_id: navigation.model_dump(mode="json", exclude_none=True),
    }
    class Traces:
        async def list_evaluation_workbench_runs(self):
            return ({"id": run_id, "state": "FAILED", "terminal_state": "FAILED", "created_at": datetime(2026, 9, 13, tzinfo=timezone.utc), "started_at": None, "ended_at": None, "plan_digest": "b" * 64},)
        async def list_run_artifacts(self, _id):
            return tuple(SimpleNamespace(id=identifier, artifact_type=kind, content_digest=hashlib.sha256(json.dumps(payload).encode()).hexdigest()) for identifier, kind, payload in (
                (manifest_id, "evaluation.manifest", payloads[manifest_id]), (report_id, "evaluation.report", payloads[report_id]),
                (navigation_id, "evaluation.navigation.index", payloads[navigation_id]), (broken_id, "evaluation.gate.report", {"broken": True}),
            ))
    class Artifacts:
        async def read_content(self, identifier):
            if identifier == broken_id: return b"not-the-claimed-digest"
            return json.dumps(payloads[identifier]).encode()
    async def exercise():
        result = await EvaluationWorkbenchService(object(), Traces(), Artifacts()).run(run_id)
        assert result and result["manifest"]["value"]["schema_version"] == "EvaluationManifest/v1"
        assert result["report"]["value"]["gate_results"][0]["state"] == "FAIL"
        assert result["navigation"]["value"]["links"] == []
        assert result["unavailable"] == [{"artifactId": str(broken_id), "artifactType": "evaluation.gate.report", "code": "EVALUATION_ARTIFACT_UNAVAILABLE"}]
    asyncio.run(exercise())


def test_static_workbench_has_dataset_run_routes_and_no_browser_metric_calculation() -> None:
    source = open("src/kb2_runtime/workbench/static/workbench.js", encoding="utf-8").read()
    primary = source.split("const PRIMARY_DESTINATIONS=[", 1)[1].split("];", 1)[0]
    assert "{id:'evaluation-dataset',label:'评估数据集'" in primary
    assert "evaluation-run" not in primary
    assert "'evaluation-run':{label:'评估运行',parent:'evaluation-dataset'}" in source
    assert "/api/workbench/evaluation-datasets" in source and "/api/workbench/evaluation-runs" in source
    assert "标记已审核" in source and "质量门禁与适用性" in source and "Applicability / Judge" in source
    assert "overallScore" not in source and "Math.average" not in source
