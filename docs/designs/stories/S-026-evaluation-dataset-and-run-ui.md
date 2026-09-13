# Story Design: S-026 - Evaluation Dataset And Run UI

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-026`, confirmed 2026-09-11.
- Sources checked: S-026; UI-009, UI-010, and UI-013; delivered evaluation
  dataset, metrics, calibration, gates, workbench, and Artifact-inspection
  contracts.
- Material decisions requiring approval: None. The `story-pipeline` invocation
  authorizes the bounded workbench projections and implementation below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add server-owned dataset list/detail/edit/review projections. The editor round-trips `DatasetContent` and uses the existing `DatasetService` for schema validation, reference checks, persistence, and explicit review events. | Service/API tests cover reviewed, draft/generated, invalid, incomplete, filter, edit, and reference-validation states. |
| 2 | Add evaluation-run catalog/detail projections over immutable manifest/report/navigation Artifacts and recorded Run lifecycle. | Projection/API tests cover running, invalid-dataset, completed, unavailable Judge, and immutable manifest identity. |
| 3 | Preserve the authoritative owner-layer bands and each metric status/count; no browser aggregate or fallback score is computed. | Tests cover ingestion, retrieval, answer, citation, decision, latency, resources, `NOT_APPLICABLE`, and `INSUFFICIENT_LABELS`. |
| 4 | Server projections return every failed hard gate, insufficient sample condition, and ineligible Judge metric independently of UI filters. | Tests and browser fixtures assert filters do not remove failure, sample, or eligibility bands. |
| 5 | Parse only digest-verified evaluation Artifacts and expose stored failed-case links to Run/stage/Artifact/Evidence/generation/verification/source controls, reusing the existing inspector. | Projection and browser tests cover full failed-case lineage and unavailable/corrupt Artifact handling. |
| 6 | Replace the evaluation-dataset placeholder and add an Evaluation Run page in the native-DOM workbench, retaining the existing dense responsive layout and keyboard semantics. | Fixture-backed Chrome screenshots at 1440x900 and 644x900, document overflow and overlap checks, and focused interactions. |

## Current Code Findings

- S-016 owns immutable Golden Dataset revisions, full typed annotation/case
  schemas, reference validation, and deliberate review provenance.
- S-017 through S-021 own metric reports, calibration eligibility, gate results,
  evaluation manifests, reports, and exact failed-case navigation. Their
  Artifact contracts are the only source for evaluation facts.
- S-022 through S-025 establish FastAPI workbench composition, native-DOM
  rendering, fixture-backed visual testing, and the shared Artifact inspector.
- The workbench has an evaluation-dataset navigation route but no evaluation
  data/run services or frontend implementation. The current navigation omits a
  dedicated evaluation-run route.

## Proposed Approach

Create `EvaluationWorkbenchService`, composed in `api.py` from the existing
repository, `DatasetService`, `RunService`, and `ArtifactService`. It provides
bounded catalog/detail/edit/review methods and safe projections; it does not
run metrics, alter dataset snapshots, calculate gates, or infer lifecycle.

Dataset editing accepts a complete typed content object, validates it through
the existing engine contract, and creates the next immutable dataset revision.
The review endpoint calls the existing explicit review operation with an
operator-supplied safe reviewer label. Generated/draft cases remain visibly
unreviewed until that operation succeeds. List/detail projections preserve all
schema fields, but never expose storage locations or credentials.

Evaluation-run projection locates actual evaluation runs and their immutable
manifest/report/navigation Artifacts by typed schema. It parses only
digest-verified content and returns manifest digests, subjects, metric layers,
gate outcomes, calibration eligibility, applicability/sample state, and exact
failed-case navigation IDs. Missing, malformed, or incompatible data maps to a
safe unavailable state without client-side synthesis. Gate rows and Judge
ineligibility are returned outside filters so they always remain visible.

Extend the static workbench routes with `evaluation-run`. The Dataset screen is
a dense list/detail editor with review, validation, filter, empty, invalid, and
incomplete states. The Run screen is a ruled manifest header, independent owner
layer bands, filter controls, permanent gate/eligibility bands, and failed-case
drilldown. Drilldown opens the existing Artifact inspector and presents linked
Run/stage/Evidence/generation/verification/source IDs. Tables receive scoped
horizontal scrolling below 900 px; no metric calculation, threshold default,
automatic review, overall score, or prototype scenario control is added.

## Relevant Impacts

- **API/data:** Add bounded workbench evaluation endpoints and repository reads
  for datasets/evaluation Artifacts. Reuse existing durable schema; no
  migration or browser-owned evaluation model.
- **Security:** Validate UUIDs/schema through typed contracts; projections omit
  raw storage paths, credentials, model/provider request bodies, and untrusted
  HTML. Native DOM uses text nodes.
- **Observability:** Preserve dataset revision/digest, review provenance,
  manifest identity, metrics, gate state, Judge calibration state, and stored
  failed-case lineage.
- **Compatibility:** Keep S-016 revision/review semantics, S-021 immutable
  report authority, and S-024 Artifact inspector behavior unchanged.

## Alternatives And Risks

- Browser-side metric aggregation, filtering that removes failed gates, and a
  synthetic overall score are rejected because they violate the evaluation
  contracts.
- Direct mutable editing of reviewed snapshots is rejected; every edit creates
  the existing engine-owned revision and requires a new deliberate review.
- Synthetic threshold, metric, or calibration defaults are rejected because
  representative calibration is not part of this Story.

## Test Strategy

- Add service/API tests for full schema round-trip, validation/reference
  errors, explicit review, list filters, immutable revisions, safe unavailable
  states, and all metric/gate/calibration projections.
- Add Artifact-lineage tests for failed-case drilldown and preserve absent or
  malformed evidence as safe unavailable data.
- Extend fixture-backed browser tests with dataset and evaluation-run states;
  capture desktop and narrow screenshots, test review/edit/filter/drilldown,
  and assert no overflow/overlap.
- Run focused workbench/evaluation tests followed by the full suite.

## Implementation Checklist

- [ ] Add bounded repository/service/API projections for datasets and runs.
- [ ] Implement dense responsive evaluation dataset/run interfaces and reuse
  the Artifact inspector for exact evidence navigation.
- [ ] Extend service/API/browser/visual tests and execute focused/full gates.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-026 `story-pipeline` invocation on 2026-09-13; no separate
product decision is required.

## Change History

- **2026-09-13:** Created just-in-time design from confirmed S-026 and direct
  evaluation/workbench dependency contracts.
