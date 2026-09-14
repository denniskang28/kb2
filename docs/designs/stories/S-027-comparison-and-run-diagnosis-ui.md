# Story Design: S-027 - Comparison And Cross-Run Diagnosis UI

## Status

Approved for Story Pipeline parity repair.

## Story Contract Snapshot

- Story: `S-027`, confirmed 2026-09-11 and implemented 2026-09-13.
- Repair target: UI-reference parity with `docs/ui/kb_ui.zip` at UI-011,
  UI-012, and UI-013 without changing S-021 comparison policy or any owning
  Run workflow.
- Sources checked: S-027; exact adopted prototype regions; current comparison,
  history, repository, API, client, fixtures, and tests; S-021 comparison
  contracts; S-024 inspector/recovery; and repaired S-025/S-026 projections.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes the bounded additive projections and tests below. There is no
  durable schema, product behavior, or comparison-policy change.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Keep S-021 as compatibility authority. Add a server-owned baseline-relative compatibility projection by reusing one shared S-021 fixed-pin check. Disable known-incompatible candidates, show its bounded reason, and recheck on create. | Unit/API tests cover compatible, same-report, fixed-pin mismatch, corrupt/missing Artifact, stale eligibility, and create-time recheck. Browser tests prove safe reasons, retained retry state, and no failed comparison result. |
| 2 | Typed/digest-validate the complete `EvaluationComparison/v1`; render identity, quality, both statuses/values, deltas, samples/confidence, gates, failed cases, latency, resources, and recommendation as separate ruled regions. | Projection/browser tests cover `VALUE`, missing statuses, missing-side values, zero-baseline relative state, all Gate/confidence/operation states, navigation, and absence of raw JSON or an overall score. |
| 3 | Render `SINGLE_AXIS` only from stored mode/axis/changes. Render `MULTI_AXIS_NON_CAUSAL` with stored changes and no component attribution. Recommendation stays read-only. | Both modes have contract/browser fixtures; incomplete/unknown modes are unavailable. Multi-axis contains no causal or activation text/control. |
| 4 | Add safe stored Profile/Plugin/input identity and duration to bounded mixed history. Implement five-type filters, clear, stable selection/detail, request-version guards, and validated URL state preserved through routes, reload, and history navigation. | Tests cover five types plus `UNKNOWN`, filters/search/clear/empty, selection outside a filter, stale responses, refresh/back/forward, and cross-route context. |
| 5 | Render exact attempts, safe failures, typed Artifact outputs, Evidence/failed-case links, and returned destinations. Reuse S-024 Inspector and S-025/S-026 routes. Only owning live services supply Stop/rerun authority. | Tests verify locator/focus/Escape/return context, Artifact/Evidence/case navigation, active ingestion/query authority, owner loss, terminal read-only states, and explicit unavailable lineage. |
| 6 | Recompose Compare into selector/manifest plus dense independent bands, and Runs into filter plus table/detail split using UI-013. Narrow views stack with labelled table overflow only. | Six reviewed goldens cover single-axis, multi-axis, and mixed selected history at 1440x900 and 644x900. Geometry/accessibility checks cover exceptional states. |

## Current Code Findings

- S-021 already publishes immutable comparison Artifacts with paired quality,
  deltas, confidence, gates, failed cases, latency, resources, axis mode, and a
  bounded recommendation. `EvaluationService.compare()` owns fixed-pin and
  axis policy.
- `ComparisonWorkbenchService.eligible()` validates reports/manifests but
  exposes only IDs and two digests. `detail()` checks a small key subset then
  passes an arbitrary dictionary to the browser. There is no baseline-relative
  compatibility or complete manifest projection.
- Compare structurally renders only metric delta numbers. Confidence, gates,
  latency, and resources are raw `<pre>` JSON. It omits quality owner/subject/
  case/slice/status/sample facts, paired manifest identity, gate drilldown, and
  stable loading/error/empty states.
- History correctly classifies comparison/contract test only from allowlisted
  plan `kind` and delegates actions to ingestion/query owners. Its rows omit
  available Profile/Plugin/input/duration and typed destinations.
- Runs displays only type, state, ID, creation time, and Trace. Filters reach
  the URL only after detail loads; requests have no stale guard; selection,
  empty/error/loading, safe failures, and filtered-out states are unstable;
  rerun uses `window.prompt`; rows lack accessible selection.
- Existing S-027 screenshots are temporary and cover one multi-axis result and
  one Query Run. There is no manifest-backed S-027 baseline or single-axis
  visual, and fixtures omit much of the production shape.
- S-024 owns inspector focus/locator behavior, S-025 owns Query/Evidence, and
  S-026 owns typed evaluation/gate/Judge/case diagnosis. S-027 must hand off to
  them, not fork them.

## Proposed Approach

### Comparison Authority And API

Keep the three endpoints. `GET /api/workbench/comparisons/eligible` remains
backward compatible and accepts optional `baselineReportId`. Every report and
manifest is type/revision/digest checked and parsed before projection.

Extract the fixed-input predicate embedded in `EvaluationService.compare()` as
a pure shared S-021 helper used by both create and the catalog. It compares only
the existing fixed fields: dataset snapshot ID/digest, taxonomy/input-catalog
digest, cases, metrics, gates, runtime, and confidence policy. Same-report and
unavailable content are rejected. This prevents a second workbench policy.

Add this safe catalog shape while retaining current top-level fields:

```json
{
  "reportId": "uuid",
  "runId": "uuid",
  "state": "SUCCEEDED",
  "manifest": {
    "artifactId": "uuid",
    "digest": "sha256",
    "datasetSnapshotId": "uuid",
    "datasetDigest": "sha256",
    "taxonomyDigest": "sha256",
    "inputCatalogDigest": "sha256",
    "caseCount": 12,
    "metricCount": 8
  },
  "compatibility": {
    "state": "BASELINE|COMPATIBLE|INCOMPATIBLE",
    "reason": "PINNED_INPUTS_NOT_EQUIVALENT|null"
  }
}
```

Compatibility is omitted without a baseline. Only finite safe codes are
exposed, never exceptions or mismatched values. `POST /comparisons` always
revalidates, so catalog state is not create authority.

Define strict workbench models for the entire stored comparison: report IDs,
mode/axis/changes, operation deltas, quality baseline/candidate/deltas,
confidence, layers/report IDs, gate pair, failed-case pair, latency, resources,
and recommendation. Validate UUIDs/enums/bounds/numeric-null states after
digest verification. Malformed content retains its Artifact identity and
returns `COMPARISON_ARTIFACT_UNAVAILABLE`, with no partial primary table.

Detail and successful create add `reports: {baseline, candidate}` using the
same safe catalog summaries. The stored comparison payload remains unchanged;
the browser receives no raw manifests and performs no join or policy inference.

### Compare Work Surface

Use this native-DOM hierarchy:

```text
main.comparison-page
  header.title-row
  section.comparison-controls
  section.comparison-identity
  section.comparison-workspace
    quality table
    confidence band
    gate band
    failed-case band
    latency band
    resources band
    recommendation note
```

Changing baseline increments a request version, disables create, reloads the
server compatibility projection, and ignores stale responses. Candidate stays
selected only if the latest response remains compatible. Create is disabled
for missing/same/incompatible/pending choices. A 409 shows the returned safe
reason beside controls, preserves retryable selections, and clears no previous
authority. Only success installs a new immutable result.

The identity band shows both report/Run/manifest IDs and digests, dataset,
taxonomy/input-catalog identity and counts. `SINGLE_AXIS` names exactly the
stored component/change. `MULTI_AXIS_NON_CAUSAL` is a prominent warning with
the complete stored change list and no cause, winner, or activation claim.

Quality rows use the stored baseline/candidate records and exact stored delta
key. Show subject, owner, metric, case/slice, both status/value facts,
sample/labelled/matched counts, absolute delta, and relative value or returned
missing/zero-baseline state. Missing sides remain `不可用`; no value, row,
threshold, ordering, or aggregate is synthesized.

Confidence shows state/reason/method/level/numerator/denominator/bounds when
present. Gates show side, gate, subject, state/reason, sample/value/state counts
and real drilldown. Failed cases retain side, case, gate, report/aggregate and
actual Artifact links. Latency and resources are independent paired bands;
resource availability, CPU, RSS, and I/O remain distinct. The stored
recommendation is text, never a mutation command. Raw JSON is not primary UI.

### Typed Mixed History

Keep the bounded newest-first repository read. Add only safe facts already in
typed plans, traces, or manifests:

```json
{
  "id": "uuid",
  "type": "INGESTION|QUERY|EVALUATION|COMPARISON|CONTRACT_TEST|UNKNOWN",
  "state": "PENDING|RUNNING|SUCCEEDED|FAILED",
  "terminalState": "SUCCEEDED|FAILED|null",
  "createdAt": "timestamp",
  "startedAt": "timestamp|null",
  "endedAt": "timestamp|null",
  "durationMs": 1234,
  "planDigest": "sha256",
  "profileId": "bounded-id|null",
  "pluginIds": ["allowlisted-id"],
  "input": {"kind": "artifact|dataset|reports|unavailable", "summary": "safe text"}
}
```

Ingestion/query identity comes only from canonical plan fields. Evaluation uses
its manifest/dataset reference; comparison uses baseline/candidate report IDs;
contract test uses only explicitly stored safe identity. Unknown shapes remain
null/empty/unavailable. Duration is a non-negative persisted timestamp
difference or null. Exclude question/source bodies, paths, locators, raw plans,
configuration, credentials, prompts, provider content, and arbitrary errors.

Detail adds ordered attempts: stage, attempt, state/result, stored Plugin,
start/end/duration, safe failure code, and typed input/output Artifact summaries.
Return destinations only for actual identities: Documents/Inspector for
ingestion, Query/Evidence for query, Evaluation/case diagnosis for evaluation,
comparison Artifact/detail for comparisons, and actual Trace/Artifacts for
contract-test/unknown.

API composition continues replacing `actions` with the owning live Documents
or Query response. History never infers action authority from `RUNNING`.
Ingestion rerun uses an inline labelled Profile handoff to the existing
rerun-preflight/Documents flow, not `window.prompt`. Stop disables while pending,
re-reads detail, and disappears on owner loss. Add no generic recovery API.

### Runs State And Navigation

```text
main.run-history-page
  header.title-row
  form.run-filters
  section.run-history-workspace
    section.run-table-region
    aside.run-diagnostic-pane
```

Table columns are Run, type, Profile/Plugin, input, state, duration, start,
Trace, and recovery. Selection is keyboard operable and programmatically
selected; route/Artifact commands are distinct controls.

Parse only valid `runType`, `runState`, bounded `q`, and UUID `run`. Every
filter change updates the URL immediately, debounces list loading, and advances
a list request version. Selection updates `run` immediately and advances a
detail version. Late list/detail/action responses cannot overwrite later state.
Back/forward rehydrates controls/list/detail.

A selected Run outside the current filter remains addressable and is labelled
`当前筛选范围外`; Clear removes filters but retains valid selection. Explicit
detail close removes `run`. `diagnosisHref` preserves validated `workspace`,
`run`, `runType`, `runState`, and `q` through Compare, Query, Evaluation,
Documents, inspector, narrow drawer, and return navigation.

Initial/filter/detail loading, full/filtered empty, list/detail failure,
not-found, action pending/failure, stale retained detail, owner loss, and missing
Artifact each have stable status/alert/empty regions. Recoverable failure keeps
filters, selection, and last valid detail but marks it stale.

### Accessibility And Responsive Rules

- Pending states use persistent `role=status`/`aria-live=polite`; failures use
  `role=alert`. Compatibility, axis mode, Run status, and selection use text
  plus icon/rule, not color alone.
- Controls have labels and visible focus/hover/pressed/disabled states. Dense
  table wrappers are labelled and keyboard-scrollable. Detail focus changes
  only after explicit row activation.
- At 1440 px Compare is a full-width dense ruled surface; Runs uses roughly
  `minmax(680px,1.45fr) minmax(340px,.72fr)`. At 644 px controls and facts
  stack, table precedes detail, and only table wrappers scroll horizontally.
- Long IDs wrap in definitions or remain in scoped overflow. Reuse UI-013
  Archivo, flat neutral panes, zero radius, strong rules, semantic red/teal/
  blue/amber, and pinned Lucide icons. No cards, gradients, oversized type, or
  prototype scenario controls.

## Relevant Impacts

- **API:** Optional baseline query and additive manifest/compatibility report
  fields; paired report summaries on comparison detail/create; additive safe
  Run identity/input/duration/navigation. Existing routes/fields remain valid.
- **Engine:** One pure S-021 compatibility helper reused by compare and catalog;
  no new rule or public execution capability.
- **Data:** No migration, backfill, mutable comparison, saved filters, or new
  version model. Current Artifacts/plans/traces/live owner maps remain authority.
- **Security:** Validate identifiers, bounds, types, revisions, digests, and
  schemas. Render text nodes. Exclude raw plans/content/configuration, paths,
  locators, credentials, prompts, vectors, provider bodies, and unsafe errors.
- **Compatibility:** Preserve S-021 policy, S-022 shell, S-024 Inspector and
  recovery, S-025 Query/Evidence/final state, S-026 evaluation/gates/Judge/cases,
  and all existing routes. Add no metric, Gate state, threshold, causal claim,
  or recovery command.

## Deterministic Visual Contract

Create `tests/visual/baselines/s027/manifest.json` and six reviewed PNGs:

| File | Fixture state | Required visible evidence | Viewport |
|---|---|---|---|
| `comparison-single-axis-1440.png` | compatible `SINGLE_AXIS`, one query component change | compatibility, paired identity, exact axis, quality/status/sample/deltas, confidence, gates/case, latency/resources, read-only recommendation | 1440 x 900 |
| `comparison-single-axis-644.png` | same | stacked controls/facts, scoped table overflow, no page overflow | 644 x 900 |
| `comparison-multi-axis-1440.png` | compatible `MULTI_AXIS_NON_CAUSAL` | prominent non-causal changes, independent bands, no attribution/activation | 1440 x 900 |
| `comparison-multi-axis-644.png` | same | narrow non-causal hierarchy, readable controls, no overlap | 644 x 900 |
| `run-history-mixed-selected-1440.png` | all five types; active Query selected | filters, dense identity/input/time columns, selection, typed Evidence Artifact, owner Stop | 1440 x 900 |
| `run-history-mixed-selected-644.png` | same | stacked table/detail, scoped scroll, preserved controls/selection | 644 x 900 |

Fixtures flow through real workbench services, typed S-021 contracts and real
trace plan shapes, with S-024/S-025/S-026 helpers where applicable. In-memory
repositories are allowed; impossible flattened browser responses are not.
Prototype data is not copied as product defaults.

Incompatible pins, loading/errors/empty, stale list/detail/create, selection
outside filters, owner loss, rerun failure, unavailable Artifact, and URL round
trips receive deterministic DOM/interaction assertions without more goldens.

The manifest records S-027/UI anchors, prototype SHA-256
`a07df450d231d777cb814d3a6695d67553748beda5491ce12e529ec2dca32ea7`,
fixture revision, baseline hashes, and the exact S-022/S-024/S-025/S-026 capture
conditions: pinned Chrome/protocol/user agent/V8/Blink, headless-new, GPU off,
DPR 1, `zh-CN`, screen/light/no forced colors/no-preference reduced motion,
complete document, loaded local Archivo 400/600/800 timing, animations/
transitions off, transparent caret, and PNG. Use one CDP target/session.

RGBA comparison requires equal dimensions, per-channel tolerance 12, and at
most `0.005` differing pixels. Tests never update goldens. On mismatch, emit
current/diff diagnostics; refresh only after manual review and manifest rehash.

## Alternatives And Risks

- Browser compatibility, delta, confidence, gate, axis, or operation
  computation is rejected because it can diverge from S-021.
- Raw JSON primary views are rejected because they do not satisfy adopted dense
  diagnosis or accessible states.
- Generic retry/stop/replay is rejected: persisted state is not live ownership.
- Identity/type/recovery inference from labels, errors, or Artifact bodies is
  rejected; explicit unavailable is safer.
- Composite winner, overall score, synthetic threshold, or activation is
  rejected by DES-015 and S-027.

## Test Strategy

- Unit/service: typed comparison parsing, shared fixed pins, safe reasons,
  paired projections, every independent state, corrupt/unavailable content.
- Repository/API: five types plus unknown, allowlisted identities/input,
  duration, attempts/failures/navigation, filters, and owner-supplied actions.
- Browser: compatibility and async guards, both axis modes, independent bands,
  drilldowns, filters/clear/exceptional states, URL history, and owner loss.
- Compare six goldens after manifest readiness; at both widths assert no page
  overflow or incoherent overlap, positive controls, stable order, and scoped
  overflow only.
- Run focused S-021/S-027 tests, full workbench Chrome, and non-Docker
  regression. Explicitly rerun S-022 shell, S-024 inspector/recovery, S-025
  Query/Evidence/final-state, and S-026 manifest/gate/Judge/case coverage.
  Reproduce and classify any Docker residual against the S-027 diff.

## Implementation Checklist

- [ ] Reuse S-021 fixed-pin authority and add typed comparison projections.
- [ ] Replace Compare JSON with identity and independent diagnostic bands.
- [ ] Add safe mixed-history identity/navigation and robust URL/async state.
- [ ] Preserve S-024/S-025/S-026 inspector, context, and owner boundaries.
- [ ] Add UI-013 styles, S-027 manifest, six goldens, and regressions.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-027 `story-pipeline` parity-repair invocation on 2026-09-14;
no separate product, API, data, architecture, or verification decision is
required.

## Change History

- **2026-09-13:** Created the initial just-in-time design and delivered S-027.
- **2026-09-14:** Revised for UI-011/UI-012/UI-013 parity; audited current gaps,
  defined typed additive projections and URL/async authority, preserved direct
  dependency boundaries, and established six dual-viewport goldens.
