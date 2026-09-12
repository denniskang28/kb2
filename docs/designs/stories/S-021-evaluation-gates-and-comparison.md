# Story Design: S-021 - Evaluation Gates And Reproducible Comparison

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-021`, confirmed 2026-09-11.
- Sources checked: the confirmed Story; `REQ-013` through `REQ-016`; `DES-014`
  through `DES-016`; `FD-010` and `FD-011`; the FEAT-004 routing manifest;
  and delivered S-010, S-015, S-016, S-017, S-018, S-019, and S-020 designs,
  contracts, services, trace substrate, and direct tests.
- Material decisions requiring approval: None. The `story-pipeline` invocation
  authorizes the bounded execution, reporting, and persistence choices below.
  Numeric thresholds and confidence settings are required caller-supplied
  manifest data, never repository defaults.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Introduce a canonical, immutable `EvaluationManifest/v1`, an input-catalog Artifact tree, and preflight validation that pins a reviewed Golden Dataset snapshot, exact input/output Artifact bindings, resolved plan payload/digests, plugin/model/prompt/configuration identities, metric/Judge definitions, taxonomy, gates, and sanitized runtime summary. | Contract and integration fixtures reject draft/untrusted dataset snapshots, missing/digest-forged inputs, incomplete pins, unregistered metrics, unsafe manifest fields, and conflicting plan/Artifact identities; valid manifests publish with complete deterministic lineage. |
| 2 | Add an evaluation orchestrator that dispatches registered ingestion, retrieval/context, answer/citation/decision, and eligible Judge metrics, aggregates each layer independently, samples elapsed and local resource facts, and publishes a layered report preserving every metric status. | Integration fixture produces all seven report sections with `VALUE`, `NOT_APPLICABLE`, and `INSUFFICIENT_LABELS` cases; asserts no aggregate score field, no missing-state coercion, and stable report bytes/parent order. |
| 3 | Add declarative slice-aware gate rules and fail-closed results. Gate evaluation selects exact report aggregates/cases, checks sample/calibration eligibility before threshold evaluation, and supports `any_failure` zero tolerance without allowing a global average to override a failed selected slice. | Parameterized gate matrix covers minimum sample failure, missing data, ineligible/drifted Judge result, threshold pass/fail, a hard critical slice hidden by a passing global slice, and invalid-citation/unsupported-fact `any_failure`. |
| 4 | Add immutable baseline/candidate bindings and a comparison service that requires identical pinned dataset/input identity, emits baseline/candidate values plus absolute/relative deltas, cases, gate outcomes, latency, and resources, and only returns a recommendation. | End-to-end comparison over two Profile result sets verifies pinned-equivalence rejection, complete layered output, zero-baseline relative-delta state, failed-case links, and that neither Profile source nor active selection is mutated. |
| 5 | Derive a deterministic axis-diff from the two resolved-plan payloads. Exactly one changed declared component axis is labelled with its axis and before/after identity; any other non-empty diff requires a caller-provided experiment name and is labelled `NON_CAUSAL`. | Single-axis ingestion/query fixtures identify the changed component; identical and unlabelled/mislabelled multi-axis manifests are rejected; named multi-axis output carries no causal attribution. |
| 6 | Publish report indexes that map each failed aggregate/gate selection to ordered metric report IDs and then validate/read existing Artifact parent lineage to expose source/ingestion, retrieval, Evidence, generation, verification, metric, and evaluation Run artifacts. | Cross-layer trace integration starts from a failed slice/case link and asserts exact Artifact IDs/digests at every available stage, including a final-state-only provider-failure path with explicit absent generation/verification fields. |
| 7 | Add replay from a trusted published manifest. It revalidates all pinned inputs and invokes the same evaluation plan; deterministic metric outputs are compared by digest, while external-generation/Judge changes are recorded as bounded environment/model nondeterminism observations rather than replay failure or byte-identical claims. | End-to-end replay proves unchanged pinned input reuse, stable deterministic replay, a simulated changed model/Judge output recorded as `MODEL_OUTPUT_CHANGED`, and a changed plugin/environment identity recorded as `ENVIRONMENT_CHANGED` without rewriting the original report. |

## Current Code Findings

- S-016 makes a reviewed `golden.dataset.snapshot/v1` the immutable evaluation
  input. It already pins controlled taxonomy, source/Evidence identities, and
  case review provenance; S-021 must consume the snapshot Artifact rather than
  mutable catalog revisions.
- S-017 through S-019 use common `MetricReport/v1` and `MetricAggregate/v1`.
  They preserve `VALUE`, `NOT_APPLICABLE`, and `INSUFFICIENT_LABELS`, metric
  owner/stage identity, slice labels, exact Artifact bindings, and navigable
  report parents. `MetricAggregator` currently averages compatible reports and
  has no gate or comparison model.
- S-020 supplies immutable Judge definitions, calibration reports, and metric
  eligibility. Only `ELIGIBLE` Judge reports may close a hard gate; advisory,
  ineligible, or drifted reports must remain visible.
- S-010 and S-015 persist resolved plan snapshots and ordered stage inputs/
  outputs in `RunTrace`. The ingestion and query engines execute compiled plans,
  but there is no evaluation-level orchestration, manifest, resource sampler,
  comparison service, or trace traversal index.
- Generic Artifacts permit at most 64 direct parents. A manifest can pin more
  than that, so direct parent lists alone cannot represent a full experiment
  input inventory. Trace schemas are closed and require explicit registration
  for every new Artifact type.

## Proposed Approach

### Immutable Experiment Manifest

Create `kb2_runtime/evaluation/runs/` with frozen Pydantic contracts,
canonical ASCII JSON helpers, validation/service modules, and public exports.
It owns evaluation orchestration and reporting only; it does not change dataset
authoring, Profile source data, Plugin descriptors, or metric algorithms.

`EvaluationManifest/v1` is a bounded declarative input with:

- one trusted `golden.dataset.snapshot/v1` reference and its taxonomy digest;
- sorted `EvaluationSubject` entries for baseline and candidate, each pinning
  source/question/search and the exact stage Artifact bindings used by its
  selected cases, plus the complete canonical resolved Ingestion/Query plan
  payloads and their SHA-256 digests;
- exact allowlisted metric IDs/configurations, optional Judge definition /
  calibration-policy/report bindings, and a closed list of evaluation cases;
- caller-supplied gate definitions, comparison name/mode, and a closed runtime
  environment summary (runtime/package implementation digests, OS family,
  architecture, and resource-sampler version). It excludes environment values,
  paths, endpoints, credentials, raw prompts, model/provider bodies, source
  text, and arbitrary executable content.

The service reads every referenced Artifact manifest/content where required,
rechecks UUID/type/revision/digest and cross-case identity, validates that
dataset cases are reviewed, and validates each embedded resolved-plan payload
with `plan_digest`. It rejects a plan digest that does not equal its canonical
payload, missing required artifact role, duplicate role/case binding, unknown
metric or gate definition, unregistered schema, or a subject whose declared
plan/Plugin/model identity conflicts with the bound artifacts. It never
silently fills omitted identity fields.

To preserve full lineage beyond 64 parents, publish deterministic
`evaluation.input.catalog/v1` leaf Artifacts containing at most 64 sorted
`ArtifactBinding`s. Internal catalog nodes reference up to 64 child catalog
Artifacts; the manifest parents only the root catalog(s), dataset snapshot,
and explicit policy/definition Artifacts. The manifest payload retains the
complete sorted binding inventory and catalog-root digest(s), so it remains
self-contained and a catalog traversal reaches every pinned input. Invalid or
incomplete input validation publishes no manifest.

### Evaluation Run And Layered Report

`EvaluationOrchestrator` takes only a trusted manifest Artifact and explicit
allowlisted metric services/Plugin Executor. It creates an
`EngineKind.EVALUATION` Run whose resolved plan includes the manifest ID/digest,
ordered case IDs, metric invocation identities, and runtime-summary digest. It
does not select or mutate a Profile. The manifest's supplied resolved plans and
bound Artifacts make the evaluated baseline/candidate result reproducible.

For every subject/case/declared metric, it dispatches the existing typed metric
services with the pinned Artifact ports. It publishes per-case reports through
the existing metric Plugins, then uses `MetricAggregator` only for compatible
metric identity/slice groups. A new report contract stores, separately and in
stable order:

```text
ingestion aggregates
retrieval aggregates
answer aggregates
citation aggregates
decision aggregates
judge aggregates
operations: latency and local resources
gate results and failed-case links
```

There is intentionally no `overall_score`, weighted total, ordinal rank, or
automatic Profile activation field. Existing status counts and values are
copied unchanged into the appropriate layer. Missing data stays explicit in
both aggregate and report outputs; it is not converted to zero, omitted, or
used as a passing value.

Operation measurements are collected around the evaluation Run with
`time.monotonic_ns()` and the standard-library process `resource.getrusage`
boundary. Reports retain elapsed milliseconds and bounded numeric local
resource deltas (CPU time, peak resident-set size where available, and I/O
values only when the platform supplies them), each with an availability state.
They remain operational observations, never gate-converted quality scores.

Publish `evaluation.report/v1` with parents in deterministic order: manifest,
metric report/aggregate Artifacts, gate report, and operation report. When the
direct parent limit would be exceeded, use bounded intermediate
`evaluation.report.catalog/v1` nodes following the same catalog pattern. Each
catalog payload gives case/metric/slice lookup facts without copied source or
answer bodies.

### Gates And Failed-Case Navigation

Add closed `QualityGate/v1` contracts. A gate names a metric ID/family and
owner, one taxonomy selector, a required aggregation (`mean`, `rate`, or
`any_failure`), minimum sample count, direction-aware threshold where relevant,
and severity (`hard` or `advisory`). No threshold, aggregation, or selector is
defaulted. `any_failure` is the only threshold-free rule and evaluates an
explicit bounded predicate (`unsupported_fact`, `invalid_citation`, or another
declared metric-match failure code) across every selected report; zero matching
failures pass and any matching failure fails.

The gate evaluator first selects reports by exact metric identity and slice,
then enforces sample/state eligibility. A `NOT_APPLICABLE`,
`INSUFFICIENT_LABELS`, absent report, empty selected slice, failed minimum
sample, or an advisory/ineligible/drifted Judge report yields a visible
`INSUFFICIENT`/`INELIGIBLE` result and prevents a hard-gate pass. Only a
threshold-bearing `VALUE` population with direction-compatible values reaches
comparison. Gate results retain selected report IDs, aggregate ID, matched case
IDs, state counts, and a bounded reason code. A failed hard slice is terminal
for that gate set even if a coarser aggregate passes.

`FailedCaseLink/v1` stores the exact case ID, subject, failed gate/metric,
report/aggregate IDs, and validated stage Artifact bindings. The builder walks
existing parents and `RunTrace` rather than duplicating content: source and
ingestion artifacts, retrieval/fusion/rerank, Evidence, generated answer when
present, verification when present, final response, metric report, aggregate,
and evaluation report/run. Absent terminal stages are explicit nullable states,
not invented links. Link construction rejects mismatched parent/digest lineage.

### Comparison, Confidence, And Replay

`ComparisonRequest/v1` references two trusted evaluation reports created from
the same dataset snapshot, input-catalog digest, case set, metric/Judge/gate
definitions, slice taxonomy, and runtime contract. The comparison service
rejects any mismatch rather than comparing superficially similar results. It
emits each layer and slice with baseline/candidate values/statuses, absolute
delta, relative delta, sample/state counts, failed-case links, gates, latency,
and resources. Relative delta is `UNDEFINED_BASELINE_ZERO` when the baseline
is zero; it is never represented as infinity.

Confidence is optional context, never a hidden gate or rank input. A manifest
may explicitly select a bounded `ConfidencePolicy/v1` (`none` or Wilson
interval with a caller-supplied confidence level) for a declared binary/rate
metric. The service reports it only when the chosen aggregate exposes a valid
numerator/denominator; means and unsupported report shapes are marked
`NOT_MEANINGFUL`. The repository supplies no confidence method, level, metric
threshold, or recommendation policy by default.

The service canonical-diffs the two pinned resolved plans after removing only
their stable subject labels. One changed declared component axis produces
`SINGLE_AXIS` with the axis name and before/after identity. More than one change
requires a non-empty caller experiment name and produces `MULTI_AXIS_NON_CAUSAL`;
it displays changes but makes no causal assertion. Zero changed axes are
rejected as a comparison candidate pair.

Recommendations are a deterministic, bounded summary of caller-selected gate
outcomes: `CANDIDATE_ELIGIBLE`, `BASELINE_RETAINED`, or `NO_RECOMMENDATION`.
They can state the exact hard-gate and operational tradeoffs, but do not write
Profile data, choose an active Profile, change registry state, or alter either
source execution plan.

`replay(manifest_id)` creates a new Evaluation Run after revalidating the
published manifest and every pinned Artifact/catalog binding. It reuses those
same inputs and metric/Judge configurations. Deterministic report content
digests are compared to the original. Where replay invokes an external model or
Judge through the supplied pinned execution adapter, a changed final/Judge
output is persisted as a new Artifact and recorded as
`MODEL_OUTPUT_CHANGED`; a changed declared runtime/provider/plugin identity is
`ENVIRONMENT_CHANGED`. These are observability outcomes, not false assertions
of byte-identical LLM generation and not mutation of the original report.

## Relevant Impacts

- **Data and compatibility:** Register `evaluation.input.catalog/v1`,
  `evaluation.manifest/v1`, `evaluation.gate.report/v1`,
  `evaluation.operation.report/v1`, `evaluation.report.catalog/v1`,
  `evaluation.report/v1`, and `evaluation.comparison/v1` in the closed trace
  schema catalog. All are additive generic Artifacts; no mutable catalog table,
  backfill, or change to S-016/S-020 persistence is required.
- **API:** Add internal typed orchestration, gate, report, comparison, replay,
  and failed-case navigation services. No FastAPI/UI endpoint is required in
  this Story; S-026/S-027 may consume the immutable report contracts later.
- **Reproducibility:** Canonical manifest/catalog bytes pin all input Artifact
  identities, plans, definitions, policies, slices, gates, and runtime facts.
  Replay creates new evidence and never overwrites historical artifacts.
- **Security:** All new inputs are closed, bounded declarative models. Reports
  store identifiers, digests, numbers, states, and safe reason codes only; they
  omit credentials, source/answer/prompt/provider bodies, arbitrary paths,
  commands, and process environment values.
- **Observability:** Evaluation Runs expose separately navigable layer, slice,
  gate, latency, resource, and replay-difference records. Existing stage
  timing/Artifact lineage remains authoritative for component diagnosis.

## Alternatives And Risks

- Directly making every pinned input a manifest parent was rejected because the
  existing Artifact contract caps direct parents at 64. The bounded catalog
  tree preserves complete deterministic inventory and traversable lineage.
- Applying a repository-wide default threshold, confidence interval, or gate
  was rejected: the confirmed Feature explicitly reserves numerical targets to
  representative datasets and calibration. Manifests therefore require these
  choices when a gate/confidence value is requested.
- Folding latency/resources into quality or using gate results to create one
  ordinal winner was rejected by the Story and `DES-014`/`DES-015`.
- Replaying cached answers only was rejected because it cannot surface model
  nondeterminism; claiming byte-identical provider output was rejected because
  it is unsupported. The replay records changed output/environment identities.
- `resource.getrusage` fields vary by platform. Every measurement has an
  availability state and is report-only; absent platform counters cannot affect
  quality or gates.

## Test Strategy

- Add `tests/contract/test_evaluation_runs.py` for manifest/catalog canonical
  bytes, trusted dataset validation, exact artifact/plan/definition pins,
  closed runtime summary, catalog fan-out bounds, and schema registration.
- Add `tests/contract/test_evaluation_gates.py` for every gate aggregation and
  state path: explicit threshold/direction, sample requirements, missing data,
  `any_failure`, hard critical slice precedence, and Judge eligibility.
- Add `tests/contract/test_evaluation_comparison.py` for pinned-equivalence,
  plan-axis classification, delta/zero baseline states, optional confidence
  applicability, non-causal multi-axis labeling, and non-mutating
  recommendation semantics.
- Add integration coverage that uses reviewed Golden Dataset fixtures and real
  metric/trace Artifacts to publish a layered report, traverse a failed case
  across ingestion/query/Evidence/final-state lineage, compare two candidates,
  and replay the manifest. Include a fake provider/Judge result change and a
  runtime identity change to assert bounded nondeterminism observations.
- Run focused evaluation, dataset, ingestion/retrieval/answer/Judge metric,
  generation, Registry/Executor, trace, and full regression suites. Run the
  Docker persistence/restart scenario when Compose starts; otherwise record the
  known Compose startup block as environment evidence rather than a product
  failure.

## Implementation Checklist

- [ ] Add frozen evaluation manifest, input binding/catalog, runtime summary,
  layer/report, gate, operation, comparison, confidence, replay, and
  failed-case contracts with canonical serialization.
- [ ] Register new Artifact schemas and implement trusted manifest/catalog
  publication and validation with bounded complete lineage.
- [ ] Implement metric orchestration, independent aggregation/report sections,
  local operation observation, hard/advisory gate evaluation, and failure-link
  traversal.
- [ ] Implement pinned baseline/candidate comparison, axis classification,
  optional confidence context, recommendation-only output, and replay
  difference recording.
- [ ] Add contract/integration fixtures for every AC and failure boundary; run
  focused/full regressions and available persistence verification.

## Open Questions

None. Thresholds, confidence policy, and gate selectors are explicit reviewed
experiment-manifest inputs; this Story deliberately supplies no default values.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-021,
  direct product/design anchors, and delivered S-010/S-015/S-016 through S-020
  executable contracts.
