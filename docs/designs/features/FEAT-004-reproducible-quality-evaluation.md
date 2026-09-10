# Feature Design: FEAT-004 - Reproducible Quality Evaluation

## Status

Approved - 2026-09-10

## Bounded Design Purpose

Define the common ground-truth, metric, slice, judge-calibration, comparison,
and diagnosis model used by ingestion and query evaluation Stories.

## Source Anchors

- `docs/features/FEAT-004-reproducible-quality-evaluation.md`
- `docs/prd.md#REQ-012` through `REQ-016`
- `docs/core-design.md#DES-004`, `DES-005`, `DES-008` through `DES-016`

## Shared Design Records

### FD-008: Dataset, Annotation, And Slice Model

- **Status:** Confirmed
- **Applies To:** Ground-truth authoring, benchmark execution, and reporting

The Evaluation Dataset separates document annotations from query cases.
Document annotations may label canonical text spans, element types/order,
tables/cells/spans, source locators, and expected chunk evidence coverage.
Query cases label question, expected and forbidden facts, relevant evidence,
required citations, answerability, and optional deterministic answer.

Every document/case carries controlled slice labels. The initial taxonomy has:

- document format and processing class;
- native versus OCR;
- structure class such as prose, hierarchy, table, or layout-rich;
- language;
- question class such as lookup, multi-evidence, table, comparison, summary,
  ambiguous, or unanswerable;
- difficulty and criticality.

Annotations are human-reviewed. Synthetic generation can propose cases but
cannot mark them reviewed or overwrite source ground truth.

### FD-009: Layer-Owned Metrics And Failure Attribution

- **Status:** Confirmed
- **Applies To:** Metric plugins, case results, gates, and reports

Each metric identifies its owner layer, required ground truth, deterministic or
judge-based method, direction, applicable slices, and missing-data behavior.
Metrics are emitted per case/document before aggregation. A failed end-to-end
case retains links to the contributing ingestion run, retrieval candidate sets,
Evidence, generation output, verification result, and metric evidence.

The baseline metric families are:

| Layer | Baseline metrics |
|---|---|
| Ingestion | CER/WER where applicable, element F1, reading-order accuracy, table structure/cell accuracy, locator accuracy, evidence preservation |
| Retrieval | Recall@K, MRR, NDCG@K, evidence hit rate, context precision/recall |
| Answer | deterministic fact coverage/violations, correctness, completeness, groundedness, citation precision/recall |
| Decision | answer-versus-abstain precision/recall and ambiguity handling |
| Operations | per-stage latency and bounded local resource observations |

Undefined metrics remain `NOT_APPLICABLE` or `INSUFFICIENT_LABELS`; they do not
silently become zero or disappear from reports.

### FD-010: Judge Calibration And Quality Gates

- **Status:** Confirmed
- **Applies To:** Semantic answer metrics and candidate eligibility

Deterministic comparison is used whenever labels permit it. An LLM Judge has a
pinned provider/model/prompt/parameters and is evaluated against a reviewed
human-labeled calibration set. Reports include agreement and material
false-positive/false-negative rates by relevant slice; an uncalibrated or
drifted Judge cannot close a hard gate.

Gates can target a metric, slice, minimum sample count, aggregation rule, and
threshold. Critical unsupported facts or invalid citations can use an
`any_failure` zero-tolerance rule. Overall averages cannot override a failed
hard slice or an insufficient sample requirement.

### FD-011: Reproducible Comparison And Report Contract

- **Status:** Confirmed
- **Applies To:** Experiment execution, candidate comparison, and diagnosis UI

A comparison manifest pins:

```text
dataset snapshot
source and upstream Artifact digests
baseline and candidate execution-plan digests
Plugin/model/prompt/configuration identities
metric and Judge definitions
slice taxonomy and gate definitions
runtime environment summary
```

Default experiments vary one component axis. Reports show baseline, candidate,
absolute and relative delta, confidence/sample count where meaningful, failed
cases, gates, latency, and resource measures. Quality, latency, and resources
are never combined into one opaque rank. Reports may recommend a candidate but
do not mutate active Profiles automatically.

## Verification Direction

- Dataset schema fixtures cover reviewed, draft, invalid, answerable, ambiguous,
  and unanswerable cases.
- Metric unit fixtures include perfect, partial, failed, and not-applicable
  results.
- Calibration fixtures detect a deliberately biased or drifted Judge.
- Comparison replay proves identical manifests reuse the same inputs and expose
  environmental nondeterminism rather than claiming byte-identical LLM output.
- Failure reports navigate from an aggregate slice to a case and its exact
  stage Artifacts.

## Open Cross-Story Questions

None. Numerical thresholds require representative datasets and calibration;
they must not be invented during schema implementation.

## Change History

- **2026-09-10:** Created and approved FD-008 through FD-011.
