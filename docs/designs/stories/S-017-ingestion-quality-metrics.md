# Story Design: S-017 - Ingestion Quality Metrics

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-017`, confirmed 2026-09-11.
- Sources checked: the confirmed Story; direct `FD-009` shared metric rules;
  the delivered S-007, S-008, S-010, and S-016 contracts and implementations;
  Plugin Registry/Executor contracts; trace Artifact/Run lineage; and direct
  canonical, chunking, dataset, and trace tests.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes the technical choices below. No quality threshold, combined score,
  or calibration target is introduced.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add immutable metric-definition/report contracts, a common deterministic plugin base, and eight registered ingestion Metric Plugins. Every per-document result records metric identity, owner `ingestion`, deterministic method, higher-is-better direction, required label kinds, declared slices, input Artifact bindings, elapsed time, and `VALUE`, `NOT_APPLICABLE`, or `INSUFFICIENT_LABELS` status. | Contract tests reject malformed definitions/results, missing required provenance, invalid state/value combinations, unknown report schema, or unregistered descriptor. Parameterized fixtures prove label/input validation and explicit missing-data states. |
| 2 | Implement deterministic CER, WER, element F1, reading-order accuracy, table-structure accuracy, table-cell accuracy, locator accuracy, and evidence-preservation metrics over reviewed snapshot annotations and typed CanonicalDocument/ChunkSet inputs. | Golden fixtures cover perfect, partial, failed (zero-valued), not-applicable, and insufficient-label results. Repeated invocation asserts byte-identical report payloads and values. |
| 3 | Require the snapshot, expected CanonicalDocument, and observed CanonicalDocument or ChunkSet as typed named plugin inputs. Publish `metric.report/v1` with all input Artifact identities as parents, preserving the existing Artifact-to-stage-to-ingestion-Run trace graph. | Integration scenario evaluates independent text/OCR, structure/order, table/cell, locator, and chunk-evidence failures and follows each report's parent Artifact to the responsible ingestion stage/run. |
| 4 | Add a generic report aggregation component which groups same-definition document reports by an exact declared slice selector and preserves total, scored, `NOT_APPLICABLE`, and `INSUFFICIENT_LABELS` counts separately. Only numeric `VALUE` results are averaged; a group without numeric observations has no value. | Unit/contract cases aggregate mixed perfect/partial/failed/missing reports, assert zero remains zero, counts remain exact, and an all-missing group remains non-passing with no numeric value. |
| 5 | Register every baseline metric through the existing Plugin Registry and make the generic evaluation service invoke a caller-selected registered metric descriptor without metric-name branching. Add one isolated fixture Metric Plugin to demonstrate extension. | Architecture regression registers and invokes an additional deterministic metric using only its descriptor/implementation/configuration and verifies no edit to evaluation orchestration is needed. |

## Current Code Findings

- The existing Plugin Registry validates revisioned descriptors, closed typed
  ports, frozen configurations, and supported Artifact schemas. The Executor
  already creates a stage attempt, validates each input Artifact, records
  output lineage, and publishes metrics/signals without an engine-specific
  execution path.
- Trace Artifacts already identify their producing Run and stage attempt. A
  metric report whose parents are the dataset snapshot and measured artifacts
  can therefore navigate exactly to the producing ingestion Run/stage without
  duplicating unbounded payloads or adding trace columns.
- S-016 supplies immutable, reviewed `golden.dataset.snapshot/v1` bytes with
  closed slice taxonomy, typed document annotations, source Artifact identity,
  and labels. It deliberately does not define metric formulas or execution.
- `CanonicalDocument/v1` provides stable elements, contiguous reading order,
  typed locators, and validated tables/cells. `ChunkSet/v1` provides element
  citations with typed locators. Those contracts are sufficient for the
  baseline deterministic comparisons; parser/OCR and profile implementations
  remain out of scope.
- The trace schema catalog is closed, and the bootstrap allowlist has no metric
  descriptors or evaluation report schemas. `kb2_runtime.evaluation` currently
  contains dataset support only.

## Proposed Approach

### Metric Contracts And Evidence

Create `kb2_runtime/evaluation/ingestion/` with frozen Pydantic contracts,
canonical serialization, deterministic metric implementations, a Plugin
adapter, aggregation, and a small generic evaluation service. Register
`metric.report/v1` and `metric.aggregate/v1` as supported trace Artifact
schemas. Both payloads use sorted ASCII JSON and SHA-256 through the existing
Plugin Executor publication path.

Define a closed per-document `MetricReport/v1` contract:

- `metric_id` is the revisioned registered Plugin ID; it carries the owner
  layer (`ingestion`), method (`deterministic`), direction
  (`higher_is_better`), and a fixed tuple of required annotation target kinds.
- One report evaluates one document for one metric. It includes the dataset
  snapshot binding, expected-source binding, observed-output binding, all eight
  controlled slice values, elapsed monotonic milliseconds, bounded evidence
  counts, and an optional numeric value in `[0, 1]`.
- Result status is exactly `VALUE`, `NOT_APPLICABLE`, or
  `INSUFFICIENT_LABELS`. `VALUE` requires a finite numeric value; the two
  missing-data statuses prohibit one. A value of `0.0` is a valid measured
  failure, never a missing state and never a passing state.
- The report never includes document text, OCR/provider bodies, credentials,
  arbitrary diagnostics, or copied trace payloads. Its typed input Artifact
  bindings and parent Artifact IDs supply bounded, exact attribution.

Each metric Plugin accepts named Artifact ports in this order:

1. `golden.dataset.snapshot/v1`;
2. expected `canonical.document/v1` whose ID/digest must exactly match the
   snapshot's reviewed annotation source; and
3. observed `canonical.document/v1`, except evidence preservation which takes
   an observed `chunk.set/v1`.

The plugin parses the snapshot, selects only annotations for the expected
source Artifact, verifies taxonomy/source/document identity, and fails closed
for broken snapshot/source/artifact combinations. A document with no target
kind required by a metric is `NOT_APPLICABLE`. Reading order with exactly one
labelled element is `INSUFFICIENT_LABELS` because it has no comparison pair;
two or more labels are sufficient. The other baseline target kinds require at
least one applicable reviewed annotation. Invalid artifacts and malformed
labels are invocation validation failures, not quality values.

`DocumentAnnotation.label` remains the reviewed expected string already owned
by S-016. Text/OCR metrics compare it against the addressed observed text
region. Structure, table, locator, and citation ground truth is derived from
the typed expected CanonicalDocument target already pinned by the annotation;
the label remains reviewer provenance and is not reinterpreted as executable
configuration. This avoids a second, free-form metric-label language and keeps
the S-016 dataset contract backward compatible.

### Baseline Formulas

Register one descriptor and implementation for each deterministic baseline
metric. All use normalized Unicode text with whitespace collapsed, preserve the
original artifacts for evidence, and make no language-model or provider call.

| Plugin ID | Required annotation kind | Value when applicable |
|---|---|---|
| `metric.ingestion.cer@1` | `text_span` | `max(0, 1 - character_edit_distance(expected, observed) / max(len(expected), 1))`, micro-averaged across labelled spans. |
| `metric.ingestion.wer@1` | `text_span` | Same form using deterministic whitespace-token edit distance, micro-averaged across labelled spans. |
| `metric.ingestion.element-f1@1` | `element` | F1 over labelled expected element locators/kinds and observed elements, where a match requires exact typed locator plus element kind. |
| `metric.ingestion.reading-order@1` | `reading_order` | Fraction of ordered pairs of labelled elements whose matched observed elements have the same relative order. Fewer than two labels is `INSUFFICIENT_LABELS`. |
| `metric.ingestion.table-structure@1` | `table` | Mean exact-match accuracy over labelled tables: table locator, dimensions, cell positions/spans, and header positions must all agree. |
| `metric.ingestion.table-cell@1` | `cell` | Micro accuracy over labelled cells: matched table locator, row/column/span, header flag, and normalized text must agree. |
| `metric.ingestion.locator-accuracy@1` | `locator` | Fraction of labelled typed locators present exactly on an observed element or table. |
| `metric.ingestion.evidence-preservation@1` | `evidence_coverage` | Fraction of labelled expected elements represented by at least one observed chunk citation with the same typed locator. |

For all set metrics, unmatched observed members contribute false positives only
within the labelled comparison universe; unlabelled document content is never
silently treated as a negative label. This makes partial and failed fixtures
meaningful without claiming complete-document annotation coverage. CER/WER use
the annotation label as expected text; a candidate element is located by the
expected target's exact locator. No OCR-specific threshold is inferred from an
OCR slice.

Every descriptor is `in_process`, has a frozen empty configuration, uses only
the typed ports above, declares `kind="metric"`, and is registered in
`plugins.bootstrap`. The generic service receives a registered `metric_id`,
the three Artifact IDs, and an evaluation Run/stage key; it delegates to
`PluginExecutor` without a metric-specific conditional. The descriptor remains
the allowlisted implementation boundary, so adding a metric means adding its
contracts/implementation/descriptor/tests, not changing orchestrator logic.

### Aggregation And Attribution

Add a generic `MetricAggregator` over decoded `MetricReport/v1` artifacts. It
accepts an exact slice selector containing one or more closed taxonomy
dimension/value pairs, a single metric identity, and reports from that same
definition/revision. It returns an immutable `MetricAggregate/v1` with:

- the exact selector and metric definition;
- `document_count`, `scored_count`, `not_applicable_count`, and
  `insufficient_labels_count`;
- an optional arithmetic mean of `VALUE` results only; and
- the sorted, bounded contributing report Artifact bindings.

The aggregator rejects mixed metric identities, conflicting taxonomies,
duplicate document/report identities, unknown slice values, and a selector
that does not exactly match each included report. It does not derive a pass/fail
state, apply a threshold, replace missing results with zero/one, or create an
overall score. It is reusable by later retrieval and answer metric Stories;
those Stories add their own Metric Plugins and report inputs, not a parallel
aggregation scheme.

Metric report parents are the snapshot, expected source, and observed output.
Existing Artifact manifest links then resolve report -> measured Artifact ->
producing ingestion stage -> ingestion Run, while the snapshot parent resolves
back to reviewed ground truth. Aggregation parents are the exact report
Artifacts. This preserves separate text/OCR, element/order, table/cell,
locator, and evidence failure paths without copying stage traces into reports.

## Relevant Impacts

- **Data/compatibility:** Adds only two additive Artifact schemas and new
  evaluation-domain payloads. It does not alter Golden Dataset tables,
  CanonicalDocument/ChunkSet schemas, historical Artifacts, profiles, or trace
  tables, so no migration/backfill is needed.
- **API:** Adds internal evaluation service/contracts only. No FastAPI/UI
  endpoint, gate, profile mutation, or public configuration surface is added.
- **Algorithm/reproducibility:** Formulas, normalization, ordering, report
  serialization, selectors, and aggregation order are deterministic. Inputs
  are immutable Artifact IDs/digests; no provider, model, clock-derived value,
  or hidden threshold affects a quality result.
- **Observability:** Per-document reports carry bounded timing/evidence counts
  and preserve parent Artifact lineage. Aggregate counts make missing data
  visible rather than allowing it to vanish into an average.
- **Security:** Metric configuration is empty and frozen. The registry
  allowlist, bounded schemas, canonical artifact reads, and safe metadata rules
  remain in force; reports contain identities and counts rather than document
  bodies, credentials, or provider payloads.

## Alternatives And Risks

- Extending `DocumentAnnotation` with a free-form JSON formula/label language
  was rejected. It would undermine reviewed data semantics and introduce an
  unbounded executable interpretation surface. Existing typed targets plus
  expected source artifacts define the necessary structure.
- Encoding metric values directly in trace `Metric` rows was rejected because
  those rows cannot express status, labels, slices, evidence bindings, or
  report-level lineage. They remain suitable for small operational counters;
  the typed Artifact is the evaluation result contract.
- A single ingestion-score Plugin was rejected because it would conflate the
  owner-layer failures that the Story requires to remain separately
  attributable. Individual plugin identities remain independently versioned.
- Full-document precision for element/table detection is intentionally not
  claimed from partial annotations. The selected labelled-universe semantics
  prevent unreviewed content from becoming a fabricated negative label. A
  future complete-coverage annotation contract can add a revisioned metric.
- Exact locator matching is deliberately strict and may score equivalent but
  non-identical locators as failures. Relaxed geometry/path matching requires
  a separately reviewed metric revision and calibration evidence.

## Test Strategy

- Add `tests/contract/test_ingestion_metrics.py` for contracts, each descriptor
  and port shape, input/source/snapshot validation, closed statuses, exact
  formulas, deterministic serialized report bytes, and generic aggregation.
- Add bounded ingestion metric fixtures derived from existing OCR, hierarchy,
  table, and chunk fixtures. Include perfect, partial, zero-valued failure,
  no-applicable-target, and one-reading-order-label insufficient cases for all
  relevant metric families.
- Add an integration test using real Artifact/Run services: publish reviewed
  dataset snapshot, expected and deliberately degraded observed artifacts,
  execute each metric through `PluginExecutor`, and verify report parent
  lineage reaches the responsible ingestion Run/stage and each failure family
  stays separate.
- Add an architecture regression with a fixture-only registered deterministic
  Metric Plugin and confirm the generic service executes it and aggregation
  consumes its report without any service/orchestration edit.
- Run focused evaluation/plugin/dataset/canonical/chunking/trace tests, the
  project regression suite, and the existing Docker-backed trace persistence
  scenario when Compose can start. Report the known Compose startup block if it
  remains unavailable rather than treating it as a passing persistence test.

## Implementation Checklist

- [ ] Add evaluation ingestion contracts, canonical serializers, report/aggregate
  Artifact schema registrations, and public package exports.
- [ ] Implement the eight deterministic baseline Metric Plugins and register
  descriptors in the existing allowlist.
- [ ] Add generic registered-metric invocation and slice aggregation with no
  metric-name branches or threshold semantics.
- [ ] Add representative golden/missing/slice/lineage/extension fixtures and
  contract/integration tests covering every acceptance criterion.
- [ ] Run focused and full regressions, including available persistence/restart
  verification, and record any environment blocker precisely.

## Open Questions

None. Formula variants are explicitly fixed above as the initial deterministic
baseline; thresholds and any calibrated/semantic metric remain outside S-017.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-017,
  direct delivered dependency contracts, Plugin Registry/Executor, and trace
  lineage implementation.
