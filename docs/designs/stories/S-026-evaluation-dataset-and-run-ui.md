# Story Design: S-026 - Evaluation Dataset And Run UI

## Status

Approved for Story Pipeline parity repair.

## Story Contract Snapshot

- Story: `S-026`, confirmed 2026-09-11 and implemented 2026-09-13.
- Repair target: UI-reference parity with `docs/ui/kb_ui.zip` at UI-009,
  UI-010, and UI-013 while retaining engine-owned dataset, metric, gate, and
  immutable Artifact authority.
- Sources checked: current S-026 contract and design; exact adopted prototype
  regions; current dataset/evaluation contracts, workbench service/client,
  fixtures, and tests; S-024 inspector behavior; and S-027 downstream
  comparison/diagnosis compatibility.
- Material decisions requiring approval: None. The pipeline authorizes the
  additive safe projections and presentation/test repair below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Replace the raw whole-dataset-first surface with a dense dataset list, case list, and selected-case editor. The browser round-trips the complete existing `DatasetContent`; document/query fields, closed slices, provenance, validation, review state, and explicit review remain visible and engine-owned. Saving creates the existing draft revision and never mutates a reviewed snapshot. | Service/API tests retain complete schema round-trip, reference validation, immutable edit revision, and explicit review. Browser tests cover reviewed, generated/draft, invalid-reference, incomplete, empty, filter, edit, save, and review states. |
| 2 | Render the persisted Run lifecycle independently from a digest-verified, schema-validated immutable manifest/report/navigation projection. Invalid dataset, missing report, unavailable Artifact, and Judge calibration states are explicit and cannot be mistaken for a successful completed evaluation. | Projection/API fixtures cover running without report, completed report, invalid/unavailable manifest, corrupt schema/digest, and uncalibrated/ineligible Judge metrics while preserving immutable IDs/digests. |
| 3 | Present separate ruled owner bands for ingestion, retrieval, context, answer, citation, decision, judge, latency, and resources. Each metric uses only stored value/status, sample/count, slices, stage, method, and eligibility facts; `NOT_APPLICABLE` and `INSUFFICIENT_LABELS` remain first-class text states. | Typed projection and browser assertions cover every returned owner, value/missing status, applicability, sample counts, slice identity, and long narrow tables without any overall score or browser aggregation. |
| 4 | Keep every hard gate, insufficient-data result, and ineligible/advisory/drifted Judge row in a permanent gate/applicability region outside metric/slice filtering. Filters alter only metric and case working sets. | Browser tests change filters and prove failed/insufficient/ineligible rows remain visible. Contract tests prove exact returned gate state, reason, selector, threshold when configured, counts, and eligibility are unchanged. |
| 5 | Drive failed-case drilldown from exact returned navigation links. The detail rail exposes Run, gate, metric report/aggregate, ingestion/retrieval/fusion/rerank, Evidence, generation, verification, final response, and source IDs only when stored. Artifact/source commands reuse S-024; Query links preserve S-027 diagnosis context. | Browser tests select a failed case by click and keyboard, open every supported Artifact/source link, verify missing links are `不可用`, and assert inspector focus/locator/URL behavior. Service tests reject corrupt or lineage-invalid navigation. |
| 6 | Use UI-013 density and two stable work surfaces: dataset list/case/editor and evaluation manifest/layers/drilldown. Desktop is split; narrow content stacks or uses labelled scoped overflow without hiding controls, gates, applicability, or evidence. | Ten reviewed goldens cover the representative dataset editor plus running, completed-failure, passed-gate, and invalid/Judge-unavailable evaluation conditions at 1440 x 900 and 644 x 900. Geometry/accessibility checks cover remaining exceptional states. |

## Current Code Findings

- S-016 already defines the complete immutable `GoldenDataset`/
  `DatasetContent` schema, closed slice taxonomy, generated/manual/imported
  provenance, content-bound review events, engine validation, and draft-on-edit
  semantics. The workbench API returns the complete content and validation map.
- The current dataset page puts the full JSON document in one textarea and then
  appends case rows. It lacks selected-row state, structured field hierarchy,
  stable pending/error regions, detailed validation placement, and deliberate
  review focus. It also uses `window.prompt` for reviewer input, which is not an
  accessible or deterministic workbench control.
- `EvaluationWorkbenchService.run()` digest-checks JSON objects and exposes raw
  manifest/report/navigation values. It does not validate those three payloads
  through `EvaluationManifest`, `LayeredReport`, and `NavigationIndex`, so an
  unrelated object can currently enter the primary UI as if authoritative.
- Its metric projection validates `MetricReport` but omits stored fields needed
  for the adopted UI: `method`, `direction`, `stageKind`, `sampleCount`,
  `caseId`, Judge `eligibility`, calibration Artifact identity, and associated
  measured/Evidence/generation/verification/final Artifact IDs. These are
  additive projection gaps; no evaluation computation or schema change is
  required.
- `LayeredReport` already separates ingestion, retrieval, answer, citation,
  decision, judge, latency, and resources; context is a metric owner displayed
  within retrieval/context diagnostic bands. Gate results already include
  subject, exact state/reason, selector-derived selected reports/cases, sample
  count, value, state counts, and optional aggregate ID. There is no overall
  score and no report-level invented calibration field.
- The current evaluation Run page renders most authority as raw `<pre>` JSON,
  maps context into retrieval implicitly, and gives no durable metric selection,
  slice filters, permanent gate/applicability region, or structured case chain.
- Existing browser tests make temporary screenshots only and assert a few text
  fragments. S-026 has no manifest-backed visual baseline.

## Proposed Approach

### Dataset List, Cases, And Editor

Keep the existing `/workbench/evaluation-dataset` route and endpoints. Render:

```text
main.evaluation-dataset-page
  header.title-row + search/status
  section.dataset-workspace
    aside.dataset-catalog
      revision rows with reviewed/total counts and digest
    section.dataset-detail
      immutable revision identity + validation summary + save status
      nav.dataset-case-list[aria-label]
      form.dataset-case-editor
        source/provenance/review
        annotation target + label OR query question/answerability/facts
        Evidence/citation fields
        eight closed slice dimensions
        save-draft and explicit-review controls
```

Selecting a dataset loads its latest requested revision and selects the first
invalid/incomplete case, otherwise the first unreviewed case, otherwise the
first case. Document annotations and query cases retain distinct type labels.
The list shows revision, reviewed/total, annotation/query counts, creation time,
and bounded digest; it does not imply a publication or version timeline.

The client holds one complete draft `DatasetContent`. Native fields edit the
selected case without dropping fields belonging to other cases or taxonomy.
Repeatable expected/forbidden facts, relevant Evidence IDs, required citation
keys, target fields, source identity/digest/schema/type, provenance, and all
eight slice dimensions are rendered from the actual schema. Dense bounded lists
may use one item per line controls, but no free-form executable configuration is
accepted. A collapsed advanced schema view may remain for complete inspection;
it is not the primary editor and must round-trip the same draft.

`验证并保存` submits the complete draft to the existing edit endpoint. Pending
state disables editor/review commands and is announced. Success selects the
returned new draft revision. Validation errors remain keyed by case/path and are
rendered both in the summary and beside the relevant case/field; they do not
erase edits. Generated, imported, edited, or otherwise unreviewed cases show
`待审核`. Review uses an inline labelled reviewer input plus `标记已审核`, is
disabled for invalid/incomplete/already-reviewed cases, and calls the existing
review endpoint deliberately. There is no auto-review or approval role.

Empty catalog, empty dataset, filtered-no-results, initial loading, load failure,
save validation failure, save dependency failure, and review failure each have
stable labelled regions. Recoverable failures preserve filter, selected
dataset/case, draft values, and reviewer input.

### Immutable Evaluation Run Header

Keep `/workbench/evaluation-run?run=<uuid>` and the existing run selector. The
header shows exact persisted Run state/terminal state, Run ID, plan digest,
created/start/end timestamps, and available actions (currently read-only).
Under it, an expandable but structured Manifest band shows manifest Artifact ID
and digest, schema, dataset snapshot/digest, taxonomy/input-catalog digests,
case/metric IDs, subject plan identities/bindings, configured gates, runtime,
and confidence policy. Values are displayed only after digest and typed schema
validation.

Run lifecycle and evaluation outcome remain separate:

- a `PENDING`/`RUNNING` trace with no report shows an announced running state
  and any available immutable manifest, never placeholder metrics;
- a completed trace shows the stored report and independent gate summary;
- a failed/invalid manifest or dataset condition shows its safe persisted code
  or `EVALUATION_ARTIFACT_UNAVAILABLE`, with no metric/gate synthesis;
- unavailable report/navigation/metric Artifacts keep their identity and safe
  unavailable state without hiding other valid sections.

Labels such as passed/failed gates are summaries of returned `GateResult`
states, not replacements for the Run lifecycle.

### Layer Bands, Filters, And Applicability

Use a two-column desktop Run surface:

```text
section.evaluation-run-workspace
  section.evaluation-metric-pane
    slice + metric/owner filters
    ingestion
    retrieval / context
    answer
    citation
    decision
    judge
    latency
    resources
  aside.evaluation-diagnostic-pane
    permanent gate/applicability/Judge region
    failed-case table
    selected evidence chain
```

Every owner band is present in stable order. It contains only returned report
identities and typed metric projections. Metric rows show metric ID, owner/stage,
method/direction where present, exact `VALUE` or missing status, returned value,
labelled/matched/sample counts, exact slices, and Judge eligibility/calibration
identity where applicable. Values are printed as returned with bounded numeric
formatting only; bars/charts may be used only when a real `[0,1]` value exists
and must retain the numeric value and status. Empty layers say `无报告`.

Metric/owner and closed-taxonomy slice controls filter only layer rows and the
case list. The diagnostic pane is recomputed only as a view of returned rows:
it always contains every hard gate state (`PASS`, `FAIL`, `INSUFFICIENT`,
`INELIGIBLE`), reason, subject, samples/state counts, configured selector and
threshold/predicate when present, plus all Judge `ELIGIBLE`, `ADVISORY`,
`INELIGIBLE`, or `DRIFTED` facts. Thus filtering cannot conceal a failed hard
slice, insufficient sample result, `NOT_APPLICABLE`, `INSUFFICIENT_LABELS`, or
Judge ineligibility. No overall quality score or default threshold is created.

Latency and resources remain independent bands sourced from report operation/
supporting Artifact facts. They are not normalized into quality.

### Failed-Case Evidence Chain

The failed-case table shows exact case, subject, gate, metric result, and stored
navigation availability. Selection uses native buttons or keyboard-activatable
rows with `aria-selected`. The selected detail renders an ordered definition
list for Run, gate, metric report/aggregate, ingestion, retrieval, fusion,
rerank, Evidence, generation, verification, final response, and source.

Each actual Artifact ID is a button to the existing S-024 inspector. Source
selection passes a returned locator only when one exists; otherwise the
Inspector opens at its schema default without inventing a locator. A Query Lab
link uses existing route/diagnosis helpers and preserves S-027 `run`, `runType`,
`runState`, and bounded `q` context. Missing links render `不可用`, never a
disabled fake command. Opening/closing the inspector retains filters and
selected case and relies solely on S-024 focus trap/Escape/focus return.

### Accessibility And Responsive Rules

- Dataset and Run loading/save/review states use persistent `role=status` and
  `aria-live=polite`; scoped failures use `role=alert`.
- Dataset/case selection is conveyed with `aria-selected` or `aria-pressed` and
  a structural rule, not color alone. Form errors use programmatic labels and
  descriptions. Gate/applicability statuses include text and icon.
- At 1440 px, dataset layout uses catalog/case/editor tracks and Run layout uses
  roughly `minmax(560px,1.35fr) minmax(360px,.9fr)`. At 644 px, catalog, case
  list, editor, metrics, and diagnostic panes stack in that order. Dense tables
  have labelled scoped horizontal overflow; page width never exceeds viewport.
- Long UUIDs/digests/metric IDs wrap in definition values or scroll within their
  table. Stable control dimensions prevent status/load changes from shifting the
  page. All controls have visible focus/hover/pressed/disabled states.
- Reuse UI-013 Archivo, neutral ground/white work panes, 1 px row rules, 2 px
  structural rules, zero radii, red commands, teal success, blue running/info,
  amber warning/inapplicable, red failure, and pinned Lucide icons. Do not add
  cards, gradients, marketing typography, or decorative imagery.

## Relevant Impacts

- **API:** Schema-validate `evaluation.manifest/v1`, `evaluation.report/v1`,
  and `evaluation.navigation.index/v1` before primary projection. Add only these
  existing `MetricReport` fields to each metric row when present: `method`,
  `direction`, `stageKind`, `sampleCount`, `caseId`, `eligibility`,
  `calibrationReportArtifactId`, `measuredArtifactId`, `labelEvidenceArtifactId`,
  `answerArtifactId`, `verificationArtifactId`, and
  `finalResponseArtifactId`. Preserve every existing endpoint and response
  field; malformed payloads continue through the existing safe `unavailable`
  collection. No launch, threshold, score, or generic Artifact endpoint is added.
- **Data/migration:** None. Dataset edits/reviews and evaluation Artifacts keep
  existing immutable repositories and schema revisions.
- **Security:** Typed/digest checks precede rendering. Use text nodes only and
  omit storage locators, credentials, provider/model bodies, private prompts,
  raw vectors, and unsafe exception text. Reviewer input remains bounded by the
  existing engine contract.
- **Compatibility:** Preserve S-016 review/content digest semantics, S-021
  manifest/report/gate/navigation authority, S-024 inspector signature/classes,
  and S-027 report eligibility, comparison fields, URL context, and Run
  diagnosis links. The additive metric fields cannot replace or rename current
  keys consumed downstream.

## Deterministic Visual Contract

Create `tests/visual/baselines/s026/manifest.json` and ten reviewed PNGs:

| File | Fixture state | Required visible evidence | Viewport |
|---|---|---|---|
| `evaluation-dataset-editor-1440.png` | selected generated/draft query case among reviewed, invalid-reference, and incomplete cases | catalog/case/editor hierarchy, all field groups, validation, slices, review control | 1440 x 900 |
| `evaluation-dataset-editor-644.png` | same | stacked hierarchy, preserved editor controls, no page overflow | 644 x 900 |
| `evaluation-run-running-1440.png` | real `RUNNING` Run with immutable manifest and no report yet | lifecycle, manifest identity, announced pending metrics | 1440 x 900 |
| `evaluation-run-running-644.png` | same | narrow manifest/loading hierarchy | 644 x 900 |
| `evaluation-run-failed-gates-1440.png` | completed report with failed/insufficient hard gates and uncalibrated/ineligible Judge metric | all owner bands, permanent diagnostics, failed cases, selected evidence chain | 1440 x 900 |
| `evaluation-run-failed-gates-644.png` | same | stacked bands/diagnostics and scoped table overflow | 644 x 900 |
| `evaluation-run-passed-gates-1440.png` | completed report whose returned gates pass | immutable manifest, independent layers, PASS rows, no overall score | 1440 x 900 |
| `evaluation-run-passed-gates-644.png` | same | narrow hierarchy and no overlap | 644 x 900 |
| `evaluation-run-invalid-dataset-1440.png` | failed validation/unavailable typed manifest or dataset snapshot with safe code | identity retained, explicit unavailable region, no synthetic metrics/gates | 1440 x 900 |
| `evaluation-run-invalid-dataset-644.png` | same | narrow error hierarchy and reachable run selector | 644 x 900 |

The dataset fixture uses contract-valid content; its invalid/incomplete states
come from authoritative reference validation, not malformed browser data. Run
fixtures use valid immutable contracts except the intentional unavailable case,
which must fail the same digest/schema boundary as production. Empty catalogs,
filtered-no-results, save/review pending/error, `NOT_APPLICABLE`,
`INSUFFICIENT_LABELS`, advisory/drifted Judge rows, filter persistence, and each
drilldown action receive DOM/interaction assertions without adding goldens.

The manifest records S-026/UI anchors, prototype archive SHA-256, fixture
revision, baseline SHA-256 values, and the exact S-022/S-024 capture conditions:
pinned Chrome/protocol/user agent/V8/Blink, headless-new, GPU disabled, DPR 1,
`zh-CN`, screen/light/no forced colors/no-preference reduced motion, complete
document, loaded local Archivo 400/600/800 resource timing, animations/
transitions disabled, transparent caret, and PNG. Use one persistent CDP target/
session for environment setup, assertions, and screenshot.

RGBA comparison requires equal dimensions, per-channel tolerance 12, and a
maximum differing-pixel ratio of `0.005`. Tests never create or update a golden.
On mismatch only, emit current/diff PNG diagnostics with ratio, dimensions,
bounds, and paths. Refresh a baseline and manifest SHA only after manual visual
inspection.

## Alternatives And Risks

- Keeping one raw dataset JSON textarea as the primary editor was rejected: it
  does not express the adopted list/detail/review hierarchy and makes per-field
  validation inaccessible. The full draft remains round-tripped without adding
  new schemas.
- Browser parsing of arbitrary manifest/report dictionaries was rejected. Typed
  validation is a minimal trust-boundary repair and does not alter valid stored
  contracts.
- Browser aggregation, an overall score, synthetic thresholds, default Judge
  calibration, or hiding failed gates behind filters were rejected because they
  contradict S-021 and UI-010.
- Product scenario switches were rejected. Visual scenarios are selected by the
  fixture harness/Run URL, not exposed in the workbench.
- A new evaluation launch API is outside this parity repair. Existing immutable
  Runs are inspected; invalid dataset feedback remains engine/service-owned.

## Test Strategy

- Extend S-026 service/API tests for typed manifest/report/navigation validation,
  additive metric fields, all applicability/Judge states, exact gate facts,
  safe corrupt/missing Artifacts, and unchanged dataset edit/review behavior.
- Add dataset browser coverage for deterministic initial selection, type/filter,
  every schema field group, draft preservation, per-field validation, save
  revision, inline reviewer input/review, pending/error/empty states, and no
  automatic review.
- Add evaluation browser coverage for independent lifecycle/outcome, immutable
  manifest, every owner band, metric/slice filters, permanent gate/Judge/
  applicability visibility, selected failed-case chain, unavailable links, and
  S-024 inspector focus/URL preservation.
- Capture and compare all ten scenarios after exact viewport/font/resource/
  media/readiness checks. At each width assert no document overflow, positive-
  size visible controls, stable track/stack order, no incoherent overlap, and
  scrolling only inside labelled dense-table/inspector containers.
- Run focused S-016/S-021/S-026 tests, S-022/S-024 visual and inspector
  regressions, S-025 Query navigation, S-027 comparison/history compatibility,
  and the broader non-Docker workbench/evaluation suite.

## Implementation Checklist

- [ ] Add typed evaluation Artifact validation and backward-compatible metric
  projection fields.
- [ ] Replace dataset JSON-first layout with catalog/case/structured editor,
  inline validation, save, and deliberate review states.
- [ ] Build immutable Run header, independent owner bands, filters, permanent
  gates/applicability/Judge diagnostics, and failed-case evidence chain.
- [ ] Reuse S-024 Inspector and preserve S-027 URL/report compatibility.
- [ ] Add UI-013 responsive/accessibility styles, S-026 manifest, ten reviewed
  goldens, interaction/geometry assertions, and focused/downstream regressions.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-025/S-026 `story-pipeline` parity-repair invocation on
2026-09-13; no separate product, API, data, or architecture decision is needed.

## Change History

- **2026-09-13:** Created the initial just-in-time technical design and
  delivered the API-backed S-026 workflow.
- **2026-09-13:** Revised for UI-reference parity against UI-009, UI-010, and
  UI-013; specified structured dataset editing, immutable layered evaluation
  inspection, applicability/gate visibility, S-027 compatibility, and
  deterministic dual-viewport golden coverage.
