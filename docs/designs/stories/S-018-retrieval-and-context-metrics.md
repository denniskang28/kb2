# Story Design: S-018 - Retrieval And Context Quality Metrics

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-018`, confirmed 2026-09-11.
- Sources checked: the confirmed Story; `REQ-013`, `REQ-015`; `DES-010`,
  `DES-011`, `DES-014`; `FD-009`; the delivered S-012, S-013, S-014, S-016,
  and S-017 contracts and implementations; Plugin Registry/Executor and trace
  Artifact contracts; and direct retrieval, fusion, evidence, dataset, and
  ingestion-metric tests.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes the bounded deterministic metric, compatibility, and fixture
  choices below. No quality threshold, aggregate grade, semantic judge, or
  relevance label is introduced.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add six deterministic metric definitions: binary Recall@K, MRR, binary NDCG@K, evidence hit rate, context precision, and context recall. Each report pins a reviewed query case, declared `K`, label Evidence, measured stage Artifact, inputs, slices, and bounded matching evidence. | Fixed ranked-list contract fixtures assert exact values at declared `K`, including a relevant result beyond `K`, first-hit rank, and binary DCG normalization. Repeated invocations assert canonical bytes. |
| 2 | Score `EvidenceSet/v1` independently from candidate ranking. Context reports derive selected items and every inclusion/exclusion/expansion decision from the EvidenceSet, then compare selected Evidence identities to the reviewed relevant identities. | Golden context fixtures assert precision/recall independently of a candidate report, selected irrelevant Evidence, excluded relevant candidates, expansion, and exact preserved decision attribution. |
| 3 | Register schema-exact adapters for each supported ranked source (`retrieval.candidate.set`, `fusion.candidate.set`, `rerank.candidate.set`) and for `evidence.set`; shared scoring normalizes their existing identity/attribution contracts without merging them. | Integration executes keyword, vector, hierarchy, table, fusion, and rerank stages from a shared index, evaluates each available Artifact, and proves report stage/contributor bindings remain distinct. |
| 4 | Use closed `VALUE`, `NOT_APPLICABLE`, and `INSUFFICIENT_LABELS` states. Reject broken snapshot/label/stage identity as an invocation failure; represent empty denominator or missing reviewed relevance explicitly, never as a zero or omitted report. | Contract matrix covers empty relevant labels, empty candidate/context applicable sets, incompatible case/Artifact identities, undeclared stage type, and invalid K. It distinguishes a measured zero from both missing states. |
| 5 | Reuse the generic aggregation/publishing path for query-case reports, grouping one metric/stage identity by exact taxonomy slices with case/sample/state counts and sorted report Artifact parents. Reports parent snapshot, reviewed Evidence, and the measured candidate or Evidence Artifact, so failed aggregates navigate to each query stage Artifact. | Multi-stage, multi-question integration aggregates mixed success/failure/missing reports, asserts counts and exact report links, and traverses report parents to candidate/Evidence/fusion/rerank producing attempts. |

## Current Code Findings

- S-017 already has canonical `MetricReport/v1` / `MetricAggregate/v1`,
  explicit result statuses, generic registered-metric dispatch, aggregation,
  supported Artifact schemas, and Plugin Executor publication. Those models
  currently hard-code `owner="ingestion"`, a document subject, and canonical
  expected/observed inputs, so they cannot represent a query case or a ranked
  stage without an additive compatible generalization.
- S-016's immutable snapshot contains reviewed `QueryCase` entries. A case
  pins an expected Evidence Artifact plus `relevant_evidence_ids` and
  `required_citation_keys`, controlled slices, and answerability. Its dataset
  validator already ensures the labels resolve in that pinned `EvidenceSet`.
- S-012 candidate sets retain document/chunk/element/locator identities,
  ranked order, and contributor IDs. S-013 fusion preserves all contributor
  candidates; rerank output preserves both selected candidates and complete
  inclusion/exclusion decisions. S-014 EvidenceSet retains selected Evidence
  and every context decision. These are sufficient for deterministic metric
  attribution without rerunning retrieval or copying source text.
- Candidate sets do not contain `EvidenceItem.evidence_id`. Relevance must
  therefore be resolved against the reviewed EvidenceSet using the exact
  source tuple `(document_id, chunk_id, ordered element_ids, locators)` and
  the Evidence item's derived ID/citation key. A loose text or score match
  would violate the citation-ready contract.
- Existing `MetricAggregator` already keeps scored, not-applicable, and
  insufficient-label counts distinct and uses report Artifact parents for
  aggregate lineage. It must be generalized from duplicate `document_id`
  detection to duplicate query case/stage report detection.

## Proposed Approach

### Shared Metric Contract Compatibility

Create `kb2_runtime/evaluation/metrics/` as the owner-neutral home for the
existing common report, status, serializer, aggregation, and generic service.
Keep `kb2_runtime.evaluation.ingestion` as a thin re-export/consumer so S-017
imports and persisted `MetricReport/v1` bytes remain valid. Do not create a
second report schema or a parallel aggregation path.

Generalize `MetricReport/v1` with a closed subject/stage shape while retaining
the S-017 fields and serialized defaults for ingestion reports:

- `owner` is exactly `ingestion`, `retrieval`, or `context`; `method` remains
  `deterministic` and direction remains `higher_is_better`.
- A report has either the existing `document_id` ingestion binding or a query
  binding: `case_id`, `question_source_artifact_id`, and `label_evidence_artifact_id`.
  Query reports require all three and prohibit an ingestion-only expected
  document binding.
- Query reports add `stage_kind` (`retrieval`, `fusion`, `rerank`, or
  `context`), `measured_artifact_id`, a declared `k` in `[1, 100]`, and a
  bounded ordered `MetricMatch` tuple. Each match carries only source IDs,
  rank, relevance, and contributor/decision IDs needed for diagnosis, never
  excerpts, query text, vectors, scores from a provider, or copied payloads.
- Query reports retain `metric_id` as the registered source-specific descriptor
  ID and add `metric_family_id` for the source-neutral formula identity. For
  S-017 ingestion reports, `metric_family_id` canonically defaults to
  `metric_id` and is omitted from legacy bytes.
- `sample_count` is the number of reviewed relevant labels for recall/ranking
  metrics, the selected Evidence count for context precision, and the relevant
  label count for context recall. `labelled_count` / `matched_count` remain for
  compatibility and are set consistently with the metric's denominator and
  successful exact matches.

`MetricAggregate/v1` gains the owner/stage identity and a bounded sorted tuple
of report Artifact IDs, but continues to average only `VALUE` results and to
report every status count. Its uniqueness key becomes
`(case_id, metric_id, stage_kind, measured_artifact_id)` for query reports and
the existing document key for ingestion reports. This permits one query case
to be evaluated at keyword, vector, fusion, rerank, and context stages without
collapse, while rejecting duplicate evaluation of the same stage output.

This is a backward-compatible payload extension: existing ingestion defaults
remain byte-compatible because the canonical serializer retains every legacy
field exactly as today and omits only absent query-only fields; existing
schemas retain `metric.report/v1` and `metric.aggregate/v1`, and no
trace/catalog migration or Artifact backfill is needed.

### Reviewed Label Resolution And Metric Inputs

Add `kb2_runtime/evaluation/retrieval/` with frozen metric configuration and
contracts, source normalization, deterministic scorer, Plugin adapters, and a
small `RetrievalMetricService` wrapper around the generic executor service.
The service accepts only a registered metric ID and Artifact IDs; it has no
metric-name switch and no call path to a retriever, fusion, reranker, context
assembler, model, or judge.

Every retrieval/ranking adapter has three named inputs:

1. `golden.dataset.snapshot/v1`;
2. reviewed `evidence.set/v1`, whose Artifact ID and digest must exactly match
   `QueryCase.evidence`; and
3. one measured source: `retrieval.candidate.set/v1`,
   `fusion.candidate.set/v1`, or `rerank.candidate.set/v1`.

Every context adapter has the first two inputs plus a measured
`evidence.set/v1`. A frozen configuration selects `case_id` and declared `k`.
The Plugin validates the snapshot taxonomy, finds exactly one reviewed query
case, checks that its source document agrees with both label Evidence and the
measured Artifact, and validates every label Evidence ID and citation key from
the expected EvidenceSet. Invalid or stale manifests/content, a mismatched
case/Evidence binding, malformed source locator, or non-resolving candidate is
a safe Plugin input failure with no report Artifact publication.

The source normalizer maps retrieval candidates directly, fused candidates
through every `CandidateContribution`, and reranked candidates plus every
`RerankDecision` into one bounded ranked inventory. Exact source matching uses
the tuple above and checks both expected `evidence_id` and `citation_key`; an
item is relevant only if it resolves to one of the case's reviewed relevant
Evidence identities. Fusion and rerank contributor IDs are preserved in each
`MetricMatch`; rerank's excluded decisions are retained as attribution, but
cannot count as ranked output. There is no inferred relevance from score,
retriever type, text overlap, raw query, or an unreviewed Evidence item.

The context normalizer uses selected `EvidenceSet.items` and all
`EvidenceSet.decisions`. It records selected items, their relevance, and every
inclusion/exclusion/expansion reason with source rank. Context precision and
recall use selected Evidence only; a candidate list's result cannot be reused
as a context metric. The measured Evidence Artifact parent still resolves
through its source candidate Artifact and index to the upstream query stage.

### Initial Deterministic Metric Semantics

The first revision uses binary reviewed relevance because S-016 supplies a
set of relevant Evidence identities, not graded relevance labels. This is an
explicit dataset-calibration choice, not a hidden conversion of answer facts
or citations into relevance.

| Plugin family | Applicable output | Formula when applicable |
|---|---|---|
| `metric.retrieval.recall@1` | any ranked candidate source | unique relevant labels represented in ranks `<= K` divided by reviewed relevant-label count |
| `metric.retrieval.mrr@1` | any ranked candidate source | reciprocal of the first rank `<= K` that resolves to relevant Evidence; `0.0` when the labelled set exists but no ranked relevant item is returned |
| `metric.retrieval.ndcg@1` | any ranked candidate source | binary `DCG@K / IDCG@K`, with `DCG = sum(1 / log2(rank + 1))` for relevant output and `IDCG` over `min(K, relevant-label-count)` ideal binary hits |
| `metric.retrieval.evidence-hit-rate@1` | any ranked candidate source | `1.0` when at least one reviewed relevant Evidence identity appears in ranks `<= K`, otherwise measured `0.0` |
| `metric.context.precision@1` | EvidenceSet selection | relevant selected Evidence count divided by selected Evidence count |
| `metric.context.recall@1` | EvidenceSet selection | unique relevant selected Evidence count divided by reviewed relevant-label count |

All numerators deduplicate by reviewed `evidence_id`, so a duplicate source
cannot increase a metric. Ranked metrics inspect only the first `K` ordered
output candidates, even where an upstream Artifact contains more. The report
captures K and the entire bounded relevant/non-relevant outcome inventory
needed to reproduce the result.

States are fixed as follows:

- A query case without reviewed relevant Evidence labels is
  `INSUFFICIENT_LABELS` for all six metrics. This includes deliberately
  ambiguous/unanswerable cases; they remain available to S-019 decision
  metrics, not fabricated retrieval negatives.
- A ranking source with no ranked outputs is a measured `VALUE` of `0.0` for
  retrieval metrics when the case has relevant labels; it is a failed retrieval
  observation, not missing data.
- Context recall with no selected Evidence is a measured `VALUE` of `0.0`
  when labels exist. Context precision with no selected Evidence is
  `NOT_APPLICABLE`, because its selected-set denominator is empty. An empty
  applicable context source is therefore visible without being converted to a
  passing or failed precision score.
- A requested strategy/stage absent from a plan produces no report. It is not
  represented as zero, a synthetic strategy row, or an aggregate omission;
  the caller evaluates only extant Artifact outputs. An unsupported measured
  schema is an invocation error.

Register a schema-exact descriptor for each metric/source pairing rather than
a union port: three ranked-source adapters for each of the four retrieval
metrics, and one EvidenceSet adapter for each context metric. Descriptors use
only the repository allowlist and closed configuration. Their IDs make source
stage explicit (for example `metric.retrieval.recall.from-fusion@1`), while
the report's canonical metric family identity remains
`metric.retrieval.recall@1`; aggregate identity includes `stage_kind` and the
registered descriptor ID to keep comparable sources separate. The report
stores the descriptor in `metric_id` and the displayed formula family in
`metric_family_id`.

### Attribution, Aggregation, And Boundaries

Each published query metric report has snapshot, label Evidence, and measured
stage Artifact as exact Artifact parents, in that order. Its trace links
resolve to the dataset review provenance and, respectively, to a retrieval
candidate set, Fusion/Rerank input chain, or EvidenceSet context decision
chain. Aggregates parent the sorted report Artifacts only. No query text,
Evidence excerpt, vector, provider response, full stage payload, or copied
trace is stored in a metric result.

Aggregation groups same metric family, descriptor/revision, owner/stage kind,
and exact slice selector. It exposes `case_count`, `sample_count`, scored,
not-applicable, and insufficient-label counts, optional mean, and report IDs.
It does not select a best strategy, establish a quality threshold, produce an
overall retrieval score, compare Profile versions, or add a UI/API endpoint;
those decisions belong to S-021 and later workbench Stories.

## Relevant Impacts

- **Data/compatibility:** Adds new evaluation packages, metric descriptors,
  fixture data, and compatible fields to the existing v1 report/aggregate
  contracts. Existing ingestion report defaults, supported Artifact schemas,
  and persisted Artifacts remain readable. No database migration is required.
- **Algorithm/reproducibility:** Input Artifact identity/digest, case ID,
  K, relevance resolution, binary formula, ranking order, normalized decision
  order, and serialization are deterministic. There are no provider calls,
  clocks, hidden relevance judges, thresholds, or aggregate grades.
- **Observability:** Bounded report matches show the relevant/irrelevant
  ranked or selected inventory, contributor/decision attribution, declared K,
  sample counts, status, and direct parents for failed-case navigation.
- **Security:** All inputs are typed, allowlisted, content-verified Artifacts;
  configuration is frozen data. Reports retain IDs/counts only and exclude
  question text, Evidence excerpts, provider data, credentials, and arbitrary
  metadata.
- **API/UI/migration:** No FastAPI endpoint, UI surface, dataset catalog
  mutation, Profile change, trace-table change, or Artifact migration is part
  of this Story.

## Alternatives And Risks

- Treating `relevant_evidence_ids` as candidate IDs was rejected because they
  name Evidence identities, and candidate IDs are strategy-specific. Exact
  citation-ready source resolution preserves comparability across retrieval,
  fusion, rerank, and context.
- Using a single polymorphic candidate port was rejected because it would
  weaken Registry port validation and obscure stage attribution. Bounded,
  schema-exact adapters mirror S-014's context boundary.
- Introducing graded NDCG labels was rejected because S-016 has reviewed
  binary relevance only. A later revision can add calibrated graded labels and
  `ndcg@2` without changing historical metric meaning.
- Dividing missing labels or empty precision denominators into zero was
  rejected because it would conflate unavailable ground truth with an observed
  retrieval failure. Explicit statuses preserve the S-017/FD-009 convention.
- Combining keyword/vector/fusion/rerank metrics into one result was rejected
  because it hides the stage that changed. Shared formulas do not justify
  shared stage identity.

## Test Strategy

- Add `tests/contract/test_retrieval_metrics.py` covering generalized report
  and aggregate validation/serialization, all descriptors and typed ports,
  binary source matching, each formula at several K values, deterministic
  bytes, contributor/decision attribution, and every missing-data state.
- Build reviewed snapshot/Evidence fixtures with binary relevant and
  non-relevant items plus fixed ranked candidate lists. Assert Recall@K, MRR,
  NDCG@K, and hit-rate perfect, partial, and zero-valued outcomes independently.
- Add context fixtures for selected relevant/irrelevant items, no selected
  items, excluded relevant candidates, deduplication, budget exclusion, and
  expansion. Assert precision/recall only read EvidenceSet selection and
  retain every decision as bounded report attribution.
- Add integration coverage through `PluginExecutor`: run keyword, vector,
  hierarchy, table, fusion, rerank, and context over existing indexed fixtures;
  evaluate each resulting Artifact against a reviewed query case; assert
  distinct descriptors, stage kinds, contributors, parent Artifact lineage,
  and no mutation of source Artifact bytes.
- Aggregate a mixed multi-case/multi-stage scenario and assert exact case and
  state counts, zero preservation, all-missing behavior, sorted report parent
  IDs, slice validation, and navigation to measured candidate/Evidence
  producing attempts. Retain S-017 ingestion aggregation regressions.
- Run focused retrieval-metric, ingestion-metric, dataset, retrieval, fusion,
  rerank, evidence, Plugin Registry/Executor, and trace tests, then the full
  project suite. Run the Docker-backed trace persistence scenario when Compose
  starts; otherwise record the known startup stall as environment-blocked.

## Implementation Checklist

- [ ] Extract compatible owner-neutral metric report/aggregate, serializer,
  generic dispatch, and aggregation contracts; preserve the S-017 public
  exports, legacy field inclusion, and fixture byte compatibility.
- [ ] Add retrieval/context metric contracts, exact source-label resolver,
  binary formulas, bounded attribution, explicit state rules, and registered
  schema-exact adapters.
- [ ] Add query-case evaluation service and trace publication using snapshot,
  label Evidence, and measured stage Artifact parents only.
- [ ] Add ranked/context/missing/slice/lineage/extension fixtures and contract
  plus integration coverage for every acceptance criterion.
- [ ] Run focused and full regression verification, including available
  persistence/restart coverage, and document an unresolved Compose blocker.

## Open Questions

None. Binary relevance and K are explicitly bound by the metric configuration
and reviewed Dataset labels; graded relevance, thresholds, comparisons, gates,
semantic judging, and UI are deferred by the Story boundary.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-018,
  its direct anchors, delivered S-012 through S-014 and S-016 through S-017
  contracts/implementation, and current Registry/Artifact tests.
