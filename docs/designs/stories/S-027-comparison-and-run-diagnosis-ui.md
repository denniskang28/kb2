# Story Design: S-027 - Comparison And Cross-Run Diagnosis UI

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-027`, confirmed 2026-09-11.
- Sources checked: S-027; REQ-017; DES-008 and DES-015; FD-011; UI-011 through
  UI-013; delivered S-021, S-022, S-024, S-025, and S-026 designs, workbench
  code, evaluation comparison contracts, trace repository, and workbench tests.
- Material decisions requiring approval: None. The `story-pipeline` invocation
  authorizes the bounded server projections, comparison submission endpoint,
  and native-DOM UI described below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Server returns only digest-verified `evaluation.report/v1` candidates and calls S-021's `EvaluationService.compare` for a submitted baseline/candidate pair. Its existing pinned-equivalence validation is authoritative; rejected pairs return one safe engine-derived compatibility code/reason and no fabricated rows or comparison Artifact. | Service/API fixtures cover eligible reports, every incompatible pin category, corrupt/missing report Artifact, and successful immutable comparison publication. |
| 2 | Parse a digest-verified `evaluation.comparison/v1` Artifact into a read-only comparison projection. Render manifest identity, separate quality/slice rows, deltas and relative-delta state, confidence/sample context, gate outcomes, failed cases, latency, and local-resource bands without browser aggregation. | Projection/UI tests cover `VALUE`, `NOT_APPLICABLE`, `INSUFFICIENT_LABELS`, undefined zero-baseline relative delta, confidence unavailable, failed gates, and unavailable supporting Artifacts. |
| 3 | Display the stored `SINGLE_AXIS` axis/before-after changes only when supplied by the comparison Artifact. Display `MULTI_AXIS_NON_CAUSAL` prominently with its changed-axis list and without a component-attribution or causal recommendation. | Contract and browser fixtures assert single-axis labelling, multi-axis non-causal labelling, no causal text/field for the latter, and no client-side axis diff. |
| 4 | Add a bounded mixed Run-history projection that classifies persisted Run plans as ingestion, query, evaluation, comparison, or contract-test only from stored engine/plan facts. Server filters and paginates by safe type/state/text inputs. The client keeps the validated filters and selected Run ID in the workbench URL context while navigating to Compare, Runs, and existing inspection routes. | Repository/service/API/browser tests cover all five types, state/type/text filtering, unknown plan kind, empty result, selected row, back/forward, and cross-route context preservation. |
| 5 | Return actual ordered trace-stage and Artifact links plus owner-authorized action capabilities. Drilldowns delegate to S-024's Artifact inspector and S-025/S-026 views; recovery routes only to existing ingestion/query actions when their service says they are currently permitted. Evaluation/comparison and unowned/restarted Runs expose no synthetic retry/stop control. | Tests cover stage/Artifact/Evidence/failed-case links, locator handoff, active versus unowned cancellation, ingestion rerun preflight routing, terminal evaluation/comparison read-only state, and safe missing lineage. |
| 6 | Replace the Compare and Runs placeholders in the shared native-DOM shell with dense ruled tables and scoped scroll containers. At desktop retain manifest/filter/action columns; below 900 px preserve labels and reachable actions through stacked controls and table horizontal scrolling. | Fixture-backed Chrome screenshots at 1440x900 and 644x900 for single-axis, multi-axis, filtered mixed history, selection and unavailable states; assert focus behavior, no page overflow, and no overlapping boxes. |

## Current Code Findings

- S-021 already publishes immutable `evaluation.comparison/v1` Artifacts. Its
  `compare()` method proves pinned input equivalence, supplies independent
  quality/gate/case/latency/resource values, derives the axis classification,
  and only returns a recommendation. It is the comparison policy boundary.
- S-026 reads verified evaluation manifests/reports/navigation Artifacts, but
  it has no comparison catalog/detail projection. `EvaluationWorkbenchService`
  currently exposes only evaluation Runs.
- `TraceRepository` has bounded overview and evaluation-only reads. It has no
  mixed Run-history query or plan-kind projection. Persisted `engine_kind` is
  ingestion/query/evaluation; comparison is represented by an evaluation Run
  with a stored `kind: evaluation_comparison` plan fact.
- S-024 owns the generic Artifact inspector and ingestion stop/rerun semantics;
  S-025 owns query stop semantics; neither permits a generic Run retry API.
- The workbench already supplies the native-DOM shell, URL workspace context,
  inspector drawer, responsive tokens, evaluation Run route, and fixture-backed
  browser test harness. `/workbench/compare` is still a placeholder and
  `/workbench/runs` currently accepts one ingestion UUID only.

## Proposed Approach

Add `ComparisonWorkbenchService` and `RunHistoryWorkbenchService` under
`kb2_runtime.workbench`, composed in `api.py` with the existing trace,
Artifact, Run, document, query, and evaluation dependencies. They are
presentation facades: all Artifact reads are through `ArtifactService`, every
typed payload is SHA-256 checked against its manifest before parsing, and no
metric, confidence interval, gate, delta, plan diff, or lineage is recalculated
in the browser.

The comparison API has three bounded operations:

1. `GET /api/workbench/comparisons/eligible` returns up to a fixed limit of
   terminal evaluation-report summaries with their immutable manifest/dataset
   identity, never raw plans, storage locators, or metric bodies.
2. `POST /api/workbench/comparisons` accepts two UUID report IDs. The service
   verifies they are eligible and delegates to `EvaluationService.compare`.
   Success returns the new immutable comparison Artifact/Run IDs and projection;
   an incompatibility is a safe `COMPARISON_INCOMPATIBLE` response containing
   only the engine reason code. It cannot activate a Profile or mutate either
   report/plan.
3. `GET /api/workbench/comparisons/{artifact_id}` returns the verified stored
   comparison projection. Supporting missing/corrupt content is represented as
   a typed unavailable item, not guessed values.

The projection retains the stored baseline/candidate report and manifest IDs,
dataset/input catalog digests, comparison mode, axis/change list, quality rows
with sample/confidence context, gates, failed-case navigation, latency,
resources, and recommendation. It deliberately has separate `quality`,
`latency`, and `resources` sections and no overall score, rank, threshold, or
activation field. The comparison page selects only entries from `eligible`,
shows an engine rejection in place, and renders the returned/selected immutable
comparison detail. A single-axis banner states the one stored changed component.
The multi-axis banner uses the literal non-causal state and lists stored changes
without saying any component caused a result.

Add one repository query over `runs`, plan snapshots, attempts, and safe error
facts for a bounded mixed history. Its service classifies type from the stored
`engine_kind` plus allowlisted plan `kind` values (`evaluation_comparison` and
`contract_test`); unknown/malformed values remain `UNKNOWN`, rather than being
misreported as a contract test. Rows contain lifecycle timestamps, plan digest,
safe status/error, pinned Profile/Plugin identity when present in the actual
plan, and trace/Artifact/drilldown IDs. Filter predicates are finite type/state
sets plus a length-bounded identifier search, with stable newest-first ordering
and a bounded cursor/limit. The detail projection reads the authoritative trace
and presents its real ordered attempts and available links only.

Run recovery is delegated, never unified: an ingestion row can link to the
existing documents Run and its owner may expose stop/rerun-preflight; a query
row can expose its owner-authorized stop; evaluation, comparison, contract-test,
unknown, terminal, and process-unowned rows are read-only. Trace and Artifact
controls use existing S-024 inspector links. Failed-case links route to the
S-026 evaluation Run/detail and then invoke the same inspector for the exact
available Evidence/source/generation/verification Artifact; absent stages stay
explicitly unavailable.

Extend `workbench.js`/CSS rather than add a frontend framework. Compare uses a
compact selector, immutable manifest band, separate quality table, independent
operation bands, gate/case drilldown rows, and an accessible non-causal label.
Runs uses type/state/search filters, a selected row/detail split, safe stage
trace and action columns. Add a small shared URL-context helper that validates
and preserves `workspace`, `run`, `runType`, `runState`, and bounded `q` on
workbench links. This state is presentation-only, not a persisted workspace,
tenant selector, or query API; invalid values are ignored. At narrow widths
filters stack and table wrappers scroll horizontally with fixed headers/actions
remaining reachable. Preserve existing drawer/inspector focus trap, Escape,
focus return, native text-node rendering, and UI-013 semantic colors.

## Relevant Impacts

- **API/data:** Add bounded comparison eligibility/create/detail and mixed
  Run-history/list/detail endpoints, workbench contracts, and repository reads.
  Reuse S-021 immutable Artifacts and current Run/attempt persistence; no schema
  migration, backfill, mutable comparison catalog, or new user-facing version
  model is needed.
- **Security:** Parse only registered typed schema revisions after digest checks.
  Validate UUIDs/query filters and return safe codes/identities/timestamps and
  stored numeric facts only. Exclude Artifact storage locations, paths,
  credentials, provider bodies, prompts, source content, raw plan payloads,
  arbitrary errors, and executable configuration. Continue native DOM text-node
  rendering with no `innerHTML`.
- **Observability:** Preserve immutable manifest/report/comparison identities,
  plan digest, recorded attempts, safe errors, axis classification, gates,
  sample/confidence state, operation availability, and failed-case lineage.
  Browser load failures remain client errors, never Run outcomes.
- **Compatibility:** S-021 remains the only comparison/axis/delta policy owner;
  S-024 inspector and ingestion recovery, S-025 query cancellation, S-026
  evaluation views, and S-022 shell paths continue unchanged. Existing program
  APIs remain valid.

## Alternatives And Risks

- Computing compatibility, deltas, confidence, or axis changes from browser
  rows is rejected because it could diverge from pinned engine evidence.
- A generic replay/retry/stop endpoint is rejected because it would violate
  immutable plans and process-local action ownership. A permitted recovery is
  an explicit handoff to the existing owner workflow.
- A composite winner or quality/latency/resource score is rejected by DES-015
  and FD-011. The stored non-mutating recommendation is shown separately.
- Treating every evaluation Run as a comparison or inferring a contract test
  from labels is rejected. The list uses only stored allowlisted plan facts and
  surfaces unclassifiable records as unknown.

## Test Strategy

- Add unit/service tests for verified comparison candidate/catalog/detail
  parsing, compatibility rejection, successful S-021 delegation, independent
  report bands, zero-baseline delta state, confidence/sample state, single-axis
  and multi-axis non-causal rendering inputs, and safe unavailable Artifacts.
- Add repository/API tests for bounded mixed Run history, stored type mapping,
  filters/cursor order, selected Run detail, safe unknown plans, trace/Artifact
  links, and authoritative recovery capabilities. Verify no comparison mutation
  or browser-owned calculation endpoint exists.
- Extend workbench fixtures and browser tests for comparison creation/detail,
  compatibility error, filters/selected row URL persistence across routes,
  failed-case/Evidence/Artifact drilldown, owner-permitted actions, keyboard
  focus/Escape behavior, and unavailable state.
- Capture desktop and narrow comparison/history screenshot states and assert
  semantic labels, scoped table overflow, document width, and box non-overlap.
  Run focused workbench/evaluation/trace tests and then the full regression
  suite.

## Implementation Checklist

- [ ] Add comparison and mixed-run workbench contracts, repository reads, safe
  verified projections, and FastAPI composition/routes.
- [ ] Delegate comparison submission to S-021 and recovery/action decisions to
  existing owning services; implement URL-context-preserving drilldowns.
- [ ] Replace Compare/Runs placeholders with responsive native-DOM surfaces and
  extend service/API/browser/visual regression coverage.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-027 `story-pipeline` invocation on 2026-09-13; no separate
product decision is required.

## Change History

- **2026-09-13:** Created just-in-time design from confirmed S-027, its exact
  evaluation/UI anchors, and delivered workbench/evaluation dependency
  contracts.
