# Story Design: S-019 - Answer, Citation, And Decision Metrics

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-019`, confirmed 2026-09-11.
- Sources checked: the confirmed Story; direct `REQ-013`, `REQ-015`,
  `DES-012`, `DES-014`, and `FD-009` anchors; delivered S-015, S-016, S-017,
  and S-018 designs and implementations; Generation, Evidence, Dataset,
  common metric, Plugin Registry/Executor, and trace contracts and tests.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes the bounded deterministic matcher, citation resolution, and
  decision-classification choices below. No semantic judge, threshold, or
  aggregate quality grade is introduced.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Register deterministic expected-fact coverage and forbidden-fact violation Plugins. Each reports reviewed labels, normalized exact-match outcome, and all original-answer character spans for matched facts, without copying answer text. | Contract fixtures assert full, partial, zero, overlapping, repeated, Unicode/whitespace-normalized, and absent-label outcomes, including exact spans and byte-identical reports. |
| 2 | Register separate citation precision and recall Plugins. They resolve every generated citation key and every required key against the reviewed EvidenceSet's exact `citation_key`, `evidence_id`, document, chunk, elements, and typed locators; invalid, missing, and unsupported citations remain individual bounded matches and stable verification facts. | Fixtures cover valid, forged, duplicate, missing-required, wrong-Evidence, wrong-locator, and unsupported-citation verification outcomes; tests prove precision and recall remain separate. |
| 3 | Register final-state decision Plugins for answerability and ambiguity handling. They compare reviewed `answerable`/`ambiguous`/`unanswerable` labels with the final response state using explicit one-vs-rest precision/recall descriptors, independently of fact and citation reports. | Parameterized answerable, ambiguous, and unanswerable final-state fixtures assert true/false positive/negative accounting, zero-valued observations, and no dependency on answer text content. |
| 4 | Use the existing closed `VALUE`, `NOT_APPLICABLE`, and `INSUFFICIENT_LABELS` report states. Missing reviewed labels and intentionally inapplicable dimensions are represented explicitly; no numeric default, absent report, or aggregate average can turn them into a pass. | Contract matrix covers absent expected/forbidden/citation labels, non-answered responses, malformed invocation bindings, empty answer text, and empty decision cohorts, distinguishing valid zero from each explicit state. |
| 5 | Publish each report with exact snapshot, final response, generated answer, verification, and reviewed/measured Evidence parents that exist for its metric family. Store bounded IDs, spans, citation/locator identity, final state, and verification codes only; trace parents provide the complete navigation path to query stages. | Integration invokes metrics through `PluginExecutor`, traverses a failed report through response, verifier, Evidence, retrieval/fusion/rerank/context parents, and asserts no answer/excerpt/provider payload is duplicated. |

## Current Code Findings

- S-015 publishes distinct `generated.answer/v1`, `verification.result/v1`,
  and `final.response/v1` Artifacts. `FinalResponse` already pins its Evidence,
  generated-answer, and verification Artifact IDs, while the verifier records
  resolved and missing citation keys and final states cannot hide invalid
  citations behind an `ANSWERED` result.
- S-016 query cases supply reviewed expected/forbidden facts, required citation
  keys, answerability, source/Evidence identity, slices, and immutable snapshot
  provenance. Snapshot eligibility already rejects contradictory answerability
  and broken reviewed Evidence references.
- S-017/S-018 already generalized `MetricReport/v1` and `MetricAggregate/v1`
  for query cases, explicit metric statuses, bounded `MetricMatch` evidence,
  report parent lineage, generic aggregation, and registered metric dispatch.
  The present owner/stage literals and match shape cover retrieval/context but
  not generation/final-state answer evaluation.
- `EvidenceItem` independently validates the citation key and evidence ID from
  the exact `(document_id, chunk_id, element_ids, locators)` tuple. This makes
  strict citation evaluation possible without text similarity or a model call.
- The Registry currently exposes schema-exact S-018 descriptors and its
  executor validates typed inputs before publishing outputs. It can support
  S-019 without an evaluation orchestrator switch or a new trace table.

## Proposed Approach

### Compatible Metric Contract Extension

Keep `kb2_runtime.evaluation.metrics` as the one common report, serializer,
aggregation, and publishing path. Add query metric owners `answer`, `citation`,
and `decision`, and allow their stage binding to be `generation`,
`verification`, or `final_state`; retain the current ingestion/retrieval/context
values and legacy ingestion byte omission unchanged.

Add an additive `answer_artifact_id`, `verification_artifact_id`, and
`final_response_artifact_id` binding to query reports. A metric family requires
only the artifact bindings it actually evaluates, but any present binding must
match the exact typed input Artifact and the cross-artifact IDs declared by
S-015. `MetricMatch` gains optional bounded `span_start`/`span_end`,
`citation_key`, `evidence_id`, and locator fingerprint fields; all are IDs or
positions, never answer text, excerpts, question text, provider payload, or
free-form diagnostics. Pydantic invariants require spans to be ordered, keys to
be revision-compatible, and a match to identify one source outcome.

Add `direction` value `lower_is_better` for the explicitly named forbidden
fact violation rate. Existing descriptors and ingestion bytes remain
`higher_is_better`; aggregation continues to compute a mean only and does not
interpret direction as a gate. This reports violations honestly rather than
renaming them into a concealed compliance score.

`MetricAggregate/v1` continues to group one descriptor/revision, owner,
metric-family, stage binding, and exact taxonomy selector. Its query uniqueness
key is extended with the answer/final Artifact identity when relevant, so one
case can retain separate answer attempt, citation-verification, and final-state
reports. Existing S-017/S-018 report bytes, schemas, Artifacts, and aggregate
behavior stay readable; no migration or backfill is required.

### Typed Evaluation Inputs And Plugin Families

Add `kb2_runtime/evaluation/answer/` for frozen configurations, deterministic
normalizers/matchers, Plugin adapters, and `AnswerMetricService`. The service
accepts a caller-selected registered descriptor and Artifact IDs, then delegates
to `PluginExecutor`; it must not switch on metric name, invoke a generator or
verifier, retrieve Evidence, alter a Dataset, or call a model.

All adapters begin with a `golden.dataset.snapshot/v1` and derive exactly one
reviewed `QueryCase` by `case_id`. They validate snapshot taxonomy, the case's
source/Evidence binding and digest, and every supplied Artifact's digest/schema
and S-015 cross-reference. Broken identity, an unreviewed/stale label binding,
or an impossible generation/verification/final chain is a safe invocation
failure with no metric report publication.

Register schema-exact descriptors, rather than a polymorphic union port:

| Family | Typed inputs after snapshot | Initial descriptor meaning |
|---|---|---|
| Answer facts | reviewed `evidence.set`, `generated.answer`, `verification.result`, `final.response` | Measure the produced answer attempt and preserve the terminal/verification linkage. |
| Citations | reviewed `evidence.set`, `generated.answer`, `verification.result`, `final.response` | Measure citation use and required-citation coverage against the reviewed Evidence contract. |
| Decisions | reviewed `evidence.set`, `final.response` | Measure final decision only; optional generation/verification parents are followed through final-response lineage, not invented as mandatory inputs for provider-failure states. |

The fact/citation adapters require the S-015 final response to point to exactly
the supplied generated/verification Artifacts. They may evaluate a repairable
generated answer even when the terminal final state is non-answered, which keeps
invalid citations and answer-attempt defects measurable rather than hiding them
behind the safe final state. Decision adapters intentionally inspect only the
reviewed label and terminal final response, keeping decision behavior separate
from answer prose quality.

### Deterministic Metric Semantics

Fact matching uses NFKC normalization, case folding, and collapsed whitespace
for comparison only. For each reviewed label, scan the original generated
answer left-to-right with a whitespace-tolerant exact normalized matcher and
record every non-overlapping original character span; a repeated expected fact
is counted once in the numerator, but all matching spans remain diagnostic.
There is no synonym, stemming, embedding, model, lexical-support inference, or
use of the deterministic answer field.

| Descriptor family | Applicability and value |
|---|---|
| `metric.answer.expected-fact-coverage@1` | For an answerable case with one or more expected facts: distinct expected facts with at least one exact span divided by expected-fact count. An answered attempt with no match is measured `0.0`. Non-answerable cases are `NOT_APPLICABLE`; an answerable case that lacks expected labels is `INSUFFICIENT_LABELS`. |
| `metric.answer.forbidden-fact-violation@1` | Where reviewed forbidden facts exist: distinct forbidden facts with an exact output span divided by forbidden-fact count, direction `lower_is_better`. No forbidden labels is `NOT_APPLICABLE`; a measured clean answer is `0.0`, never a missing/pass substitution. |
| `metric.citation.precision@1` | Valid, unique generated citation keys that resolve to the reviewed Evidence item's exact identity divided by all supplied citation keys. A citation absent from Evidence, duplicated, or contradicted by verification remains a non-matching diagnostic. No citations from an answer attempt is a measured `0.0` when citation labels exist. |
| `metric.citation.recall@1` | Distinct reviewed required citation keys present and exactly resolved in the generated answer divided by required-key count. Missing required keys are retained individually, including verifier missing-key facts. Missing required-citation labels is `INSUFFICIENT_LABELS`. |
| `metric.decision.answerability-precision@1` / `...-recall@1` | One-vs-rest `ANSWERED` prediction versus reviewed `answerable`; evaluate cases selected by a frozen cohort configuration. |
| `metric.decision.ambiguity-precision@1` / `...-recall@1` | One-vs-rest `CLARIFICATION_REQUIRED` prediction versus reviewed `ambiguous`; unanswerable cases remain negative examples. |
| `metric.decision.abstention-precision@1` / `...-recall@1` | One-vs-rest `ABSTAINED` prediction versus reviewed `unanswerable`; ambiguous cases remain negative examples. |

Precision decision reports are `NOT_APPLICABLE` when their predicted-positive
denominator is zero; recall reports are `INSUFFICIENT_LABELS` when the selected
cohort contains no reviewed positive labels. Case-level inputs carry `TP`,
`FP`, `TN`, or `FN` evidence; the common aggregate produces cohort precision or
recall from an explicit immutable set of per-case confusion outcomes, not an
average that changes the formula. Introduce a small deterministic cohort
reducer under the answer package to publish this result with sorted report
parents. It must preserve all status counts and cannot emit a score for an
empty denominator.

The first revision intentionally does not manufacture deterministic
correctness, semantic completeness, or groundedness scores from surface text.
Expected-fact coverage and forbidden-fact violations are transparent lexical
checks; verifier outcomes and citation identity give strict deterministic
grounding/citation evidence. S-020 owns calibrated semantic evaluation through
a new, explicitly revisioned interface and may consume these report contracts
without changing their historic meanings.

### Lineage, Aggregation, And Bounds

Each answer/citation report parents, in stable order: snapshot, reviewed
Evidence, generated answer, verification result, and final response. A decision
report parents snapshot, reviewed Evidence, and final response. Its final
response Artifact parents then navigate to available generated/verification
results, including a safe provider-failure route with no impossible placeholder
Artifact. Report matches are bounded by 64 facts, 100 citation keys, and the
existing output limits; fact spans are bounded by the `GeneratedAnswer` limit.

The report itself holds only stable IDs/spans/counts and selected verification
codes. Trace graph traversal resolves report -> final response -> verification
and generated answer -> Evidence -> context -> candidate/fusion/rerank/retrieval
stages. No unbounded answer, Evidence excerpt, full stage payload, provider
request/response, credential, or duplicated trace is published.

Metrics aggregate only like descriptors and exact slice selectors. Answer and
citation metrics aggregate normal `VALUE` reports under existing rules. Decision
cohorts aggregate explicit confusion counts to ratio numerators/denominators,
retain case/state/report counts, and never create a best profile, threshold,
gate, overall answer score, or comparison. Those outputs remain S-021 scope.

## Relevant Impacts

- **Data/compatibility:** Additive query report fields, match fields, registered
  descriptors, and bounded answer-evaluation Artifact payloads extend the
  existing v1 metric contract without changing legacy ingestion serialization
  or immutable Dataset/Generation/Evidence schemas. No database migration is
  required.
- **Algorithm/reproducibility:** Label selection, normalization, span scan
  order, citation/locator identity, final-state mapping, cohort membership,
  count order, and serialization are deterministic. There are no clocks,
  provider calls, semantic scores, hidden thresholds, or ground-truth edits.
- **Observability:** Reports expose facts/citations/confusion outcomes and
  direct typed parents sufficient to navigate a failed case across the query
  stages, while retaining only bounded IDs, spans, statuses, and counts.
- **Security:** All inputs are typed, allowlisted, digest-verified Artifacts;
  configuration is frozen data. Metric payloads exclude source prose, prompts,
  provider data, credentials, arbitrary metadata, and executable content.
- **API/UI/migration:** No FastAPI endpoint, UI, profile change, Dataset catalog
  mutation, trace schema/table change, or Artifact migration is part of this
  Story.

## Alternatives And Risks

- Using an LLM or fuzzy text matcher for fact coverage was rejected because it
  would make S-019's required checks non-deterministic and blur its boundary
  with S-020 semantic judging.
- Scoring only `ANSWERED` final responses was rejected because a repairable
  generated answer with forged/missing citations would disappear from evaluation.
  Measuring the typed attempt retains that defect while decision metrics judge
  the terminal state separately.
- Treating verifier `pass` as citation precision/recall was rejected: it loses
  missing, malformed, and unsupported citation identities and cannot provide
  separate precision and recall.
- Converting forbidden-fact violation into a positive compliance score was
  rejected because it obscures the explicitly requested violation dimension;
  a direction field keeps the metric semantically honest without adding a gate.
- Per-case averaging for precision/recall was rejected for decision cohorts
  because it changes the metric under mixed positives. Explicit confusion-count
  reduction preserves standard cohort semantics and visible empty denominators.

## Test Strategy

- Add `tests/contract/test_answer_metrics.py` for extended report/aggregate
  validators and legacy ingestion-byte compatibility; descriptor/port shape;
  configuration bounds; exact fact spans; NFKC/whitespace normalization;
  repeated/overlapping facts; forbidden violations; citation identity and
  verification consistency; all status combinations; deterministic bytes; and
  all three decision precision/recall confusion matrices.
- Build reviewed Dataset/Evidence/generation fixtures spanning answerable,
  ambiguous, unanswerable, valid answer, partial/zero fact coverage, forbidden
  content, forged/duplicate/missing citations, invalid citation verification,
  abstention, clarification, provider failure, and repair success/exhaustion.
- Add integration coverage through `PluginExecutor` and real trace Artifacts:
  evaluate each descriptor, assert exact parents/order and no source mutation,
  traverse a failed report to final/verification/generated/Evidence and its
  context/candidate stages, and assert metric payloads contain no answer or
  Evidence text.
- Exercise aggregation for mixed values, zeros, not-applicable, insufficient
  labels, slices, retry attempts, and decision cohorts. Assert exact numerator,
  denominator, state counts, and sorted report parent lineage; retain S-017 and
  S-018 aggregation regressions.
- Run focused answer-metric, generation, golden-dataset, retrieval-metric,
  evidence, Registry/Executor, and trace tests, then the full project suite.
  Run Docker-backed persistence when Compose starts; otherwise record the known
  Compose startup stall as environment-blocked.

## Implementation Checklist

- [ ] Extend common metric contracts/serialization/aggregation compatibly for
  answer, citation, decision, generation, verification, final-state bindings,
  bounded spans and citation/locator diagnostics, and lower-is-better violation
  direction while preserving legacy ingestion bytes.
- [ ] Add frozen answer-metric contracts, exact label/citation resolvers,
  deterministic fact/forbidden/citation/decision scorers, cohort reduction,
  service, and schema-exact registered descriptors.
- [ ] Publish metric reports and decision aggregates through existing typed
  Plugin/trace paths with stable parent order and no copied query payloads.
- [ ] Add contract and integration fixtures/tests for every AC, including
  cross-layer failed-case navigation and explicit missing-data behavior.
- [ ] Run focused and full regression verification, including available
  persistence/restart coverage, and document any unresolved Compose blocker.

## Open Questions

None. Deterministic lexical matching, strict citation identity, and final-state
cohort semantics are pinned above; semantic correctness/completeness,
groundedness calibration, thresholds, gates, comparisons, and UI remain out of
scope.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-019,
  its direct anchors and dependencies, and the delivered generation, dataset,
  common metric, retrieval/context metric, Registry, and trace contracts.
