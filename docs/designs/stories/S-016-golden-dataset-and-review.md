# Story Design: S-016 - Golden Dataset And Human Review

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-016`, confirmed 2026-09-11.
- Sources checked: the Story contract; `REQ-012`, `REQ-015`; `DES-013`;
  `FD-008`; the FEAT-004 routing manifest; and the delivered S-002, S-005,
  and S-014 contracts, trace implementation, and direct tests.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes the storage and contract decisions below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add versioned Dataset contracts for taxonomy, document annotations, query cases, source/Evidence bindings, provenance, review records, canonical export, and deterministic snapshot bytes. | Contract round-trip fixtures assert exact UUID/digest, typed locator/citation identity, allowed slices, reviewer record, schema revision, and canonical export/import behavior. |
| 2 | Validate all draft revisions against declared taxonomy and their pinned CanonicalDocument/EvidenceSet Artifacts; gate snapshot creation on valid, reviewed cases only. | Parameterized failures cover required-fact omissions, source/locator mismatch, contradictory answerability, unknown slice, missing or forged Evidence, and prove no snapshot output is published. |
| 3 | Model authorship origin and an append-only explicit review event. Create/import/generated edits start unreviewed; editing a reviewed revision creates a new draft revision. | State-transition tests prove that neither a draft nor a generated case becomes eligible without `mark_reviewed`, and that review provenance records reviewer, timestamp, input revision, and operation. |
| 4 | Persist immutable dataset revisions and publish an immutable `golden.dataset.snapshot/v1` Artifact through an evaluation Run. Snapshot content pins eligible case revisions and every referenced Artifact identity. | Integration replay edits a reviewed case after snapshot A, creates snapshot B, and proves A bytes/content and a Run pinned to A remain unchanged. |
| 5 | Add bounded fixture datasets for reviewed, draft, generated, invalid, answerable, ambiguous, unanswerable, and representative text/structure/table document annotations. | Focused contract tests load every fixture; integration tests create and replay snapshot artifacts from the reviewed fixture. |

## Current Code Findings

- S-002 already persists generic content-addressed Artifacts and immutable plan
  snapshots. `ArtifactService.complete_with_outputs` verifies bytes/digests and
  links outputs to a Run/stage, while `EngineKind.EVALUATION` is already a
  supported run kind. A Golden Dataset snapshot should use this substrate,
  rather than a parallel blob store.
- `CanonicalDocument/v1` supplies stable document, element, table, cell, and
  discriminated locator contracts. Its provenance contains both the source
  Artifact UUID and source content digest, which is the required document
  annotation identity anchor.
- S-014's `EvidenceSet/v1` provides deterministic `evidence_id` and
  `citation_key` values with exact document/chunk/element/locator pairs and a
  bound Search Index Artifact. It is the direct evidence source for query
  labels; labels must not retype a locator or evidence identity loosely.
- Trace schema registration is closed and currently lacks a dataset snapshot
  schema. Existing migrations stop at trace input/evidence persistence. There
  is no evaluation-domain package, dataset persistence schema, or evaluation
  HTTP endpoint yet.

## Proposed Approach

### Dataset Contracts And Validation

Create `kb2_runtime/evaluation/datasets/` with frozen Pydantic contracts,
canonical JSON/identity helpers, validation service, persistence repository,
and public exports. Keep it independent of metric calculation, judges, gates,
or UI, which belong to later Stories.

Define the closed `GoldenDataset/v1` data family:

- a dataset has a schema revision, a declared controlled `SliceTaxonomy/v1`,
  and immutable content revisions;
- a document annotation binds one `canonical.document/v1` Artifact reference
  (`id`, content digest, schema revision) and labels typed targets for a text
  span, element/reading order, table/cell/span, source locator, or expected
  evidence coverage;
- a query case binds a question to one document source reference and labels
  expected/forbidden facts, relevant evidence IDs, required citation keys,
  answerability, optional deterministic answer, and controlled slices;
- provenance is bounded declarative data: case origin (`manual`, `generated`,
  or `imported`), creation/revision operation, and append-only review facts.
  It holds no credentials, source bodies, provider payloads, or arbitrary
  reviewer profile data.

The initial taxonomy is a repository-owned closed default with dimensions for
document format, processing class, native/OCR, structure, language, question
class, difficulty, and criticality. It includes the FD-008 values (for example
`prose`, `hierarchy`, `table`, `layout_rich`; `lookup`, `multi_evidence`,
`table`, `comparison`, `summary`, `ambiguous`, `unanswerable`) and bounded
neutral values such as `unknown` where a dimension does not apply. Dataset
creation may select from this taxonomy but may not silently introduce a new
dimension or value. Every annotation/case must carry the applicable controlled
labels, and snapshot validation rejects unknown or duplicate labels.

Validation receives an Artifact reader protocol, retrieves and revalidates
the referenced Artifact manifest/content, and compares it to the contract:

1. A document annotation's document ID, typed locator, element, table, and
   cell targets must exactly resolve in its pinned `CanonicalDocument/v1`.
   Text spans are bounded, use known target text, and cannot extend outside the
   addressed canonical element/cell text.
2. A query case's relevant evidence IDs and required citations must resolve in
   its pinned `EvidenceSet/v1`, with the same document identity as the case.
   Required citations are a non-empty unique subset of relevant evidence when
   answerability is `answerable`.
3. `answerable` requires at least one expected fact, relevant evidence, and a
   required citation. `ambiguous` and `unanswerable` cannot declare an expected
   fact, deterministic answer, relevant evidence, or required citation;
   `unanswerable` may carry bounded forbidden facts for later decision tests.
   Expected and forbidden fact sets must be non-empty strings, individually
   unique, and disjoint in normalized form.

These strict initial semantics make the three answerability states mutually
testable. Any richer partial-answer or ambiguity annotation needs a new Story
contract rather than a permissive catch-all field.

### Review, Revisions, And Persistence

Add an Alembic migration for a small evaluation catalog rather than placing
mutable authoring state in Artifact storage:

- `golden_datasets` stores the stable dataset UUID, immutable taxonomy JSON,
  and creation metadata;
- `golden_dataset_revisions` is append-only and stores a dataset UUID,
  monotonic revision number, parent revision UUID, canonical content JSON,
  content digest, operation, and timestamp; and
- `golden_dataset_reviews` is append-only, keyed to the exact case/annotation
  revision and recording the explicit `mark_reviewed` operation, a bounded
  reviewer label, timestamp, and reviewed content digest.

The repository writes revision and review rows transactionally. Operations are
service-level `create`, `edit`, `validate`, `mark_reviewed`, `export`,
`import`, and `create_snapshot`; no HTTP endpoint is added in this Story.
`edit` never overwrites stored content. Editing reviewed content creates a new
draft revision with review state cleared, so ground truth remains immutable and
the change must be reviewed again. Generated content always begins unreviewed.
Import preserves `reviewed` only when a valid explicit review record is part of
the import; otherwise it imports as draft. No user identity, authorization, or
approval workflow is added: the reviewer label is provenance, not access
control.

`validate` returns a typed bounded report per document annotation/query case
with `valid`, blocking error codes, source identities, and review eligibility.
It does not alter review state. `mark_reviewed` requires a currently valid
revision and records its explicit review event. This makes reviewer authority
an operation, not an editable boolean.

### Immutable Evaluation Snapshot

`create_snapshot` validates the selected dataset revision, selects only valid
reviewed document annotations and cases, and fails closed if any requested
case is invalid, draft, generated-unreviewed, or refers to unreadable source
Artifacts. It creates a short `EngineKind.EVALUATION` Run with a canonical
resolved plan containing the dataset/revision digest and taxonomy digest, then
publishes one `golden.dataset.snapshot/v1` Artifact at `dataset.snapshot`.

The snapshot payload contains its deterministic ID, source dataset/revision
identity, taxonomy, exact reviewed case/annotation revision content, their
review provenance, and every distinct canonical-document/EvidenceSet Artifact
reference. Canonical sorted ASCII JSON and SHA-256 are used for snapshot IDs,
content digests, exports, and reproducible import verification. The Artifact's
parent IDs are the unique pinned source Artifacts (with bounded dataset/source
limits enforced before publication), so existing trace lineage leads from an
evaluation Run back to source document and Evidence artifacts. Register
`golden.dataset.snapshot`/`v1` in the trace schema catalog. Later evaluation
Stories consume only this snapshot Artifact identity; they do not read the
editable dataset catalog.

No prior-run mutation operation is added. A later authoring edit creates a new
dataset revision and may produce a different snapshot Artifact, leaving
previous Artifact bytes and any Run plan/lineage unchanged.

## Relevant Impacts

- **Data/migration:** Adds immutable evaluation-catalog revision/review tables
  and `golden.dataset.snapshot/v1` to the existing generic Artifact schema
  catalog. Existing trace tables and prior Artifacts need no backfill.
- **API:** Adds internal typed dataset service/repository contracts only. It
  intentionally does not expose FastAPI/UI authoring endpoints; S-026 can
  bind to these operations when its workbench contract is delivered.
- **Reproducibility:** Dataset snapshots pin document and Evidence Artifact UUID
  plus digest, case/annotation revision content, taxonomy, and review event.
  They are canonical, content-addressed inputs for later evaluation Runs.
- **Security:** Imports/exports and provenance accept only closed, bounded JSON
  schema data. Artifact reads recheck identity/digest, and safe validation
  reports contain codes and bounded IDs rather than document bodies, provider
  payloads, secrets, or reviewer PII.
- **Compatibility:** CanonicalDocument and EvidenceSet are immutable read-only
  dependencies. The migration is additive and no existing ingestion/query
  plan or Plugin descriptor changes.

## Alternatives And Risks

- Storing editable drafts as generic Artifacts was rejected because it cannot
  express explicit review transitions or an authoring revision history without
  overloading Run/stage semantics. Artifacts remain the immutable execution
  boundary; the small catalog owns deliberate editing.
- A free-form slice map was rejected because it would permit unknown slices and
  weaken REQ-015 comparisons. The initial controlled taxonomy is closed and
  schema-versioned.
- Treating a `reviewed` boolean as sufficient was rejected: it would allow an
  import or edit to manufacture ground truth. Eligibility instead requires an
  append-only review operation over the exact content digest.
- Snapshot size must remain bounded by the existing Artifact/lineage contracts.
  Initial dataset limits should be explicit and tested; larger corpora require
  pagination/sharding design rather than silently omitting pinned parents.

## Test Strategy

- Add `tests/contract/test_golden_datasets.py` for contract shapes, closed
  taxonomy, canonical identity/bytes, imports/exports, typed document targets,
  evidence/citation validation, answerability contradictions, and review state
  transitions.
- Add reviewed/draft/generated/invalid and answerable/ambiguous/unanswerable
  dataset JSON fixtures, plus text, hierarchy, and table annotation fixtures
  derived from existing canonical/evidence fixture artifacts.
- Add an integration test against the trace/catalog services that creates a
  source CanonicalDocument/EvidenceSet, explicitly reviews a valid revision,
  publishes snapshot A, edits the case, re-reviews, publishes snapshot B, and
  verifies snapshot A's content/digest/Run lineage are unchanged.
- Assert invalid locators, stale/missing/forged Artifact manifests, unknown
  slices, missing facts, broken evidence, imports without review events, and
  attempts to snapshot draft/generated content produce safe failures and no
  Artifact output.
- Run focused dataset/trace/canonical/evidence tests and the full project suite;
  run the Docker-backed persistence/restart regression when the local Compose
  environment is available.

## Implementation Checklist

- [ ] Add evaluation dataset contracts, deterministic serialization, taxonomy,
  validation report/error codes, and Artifact reader boundary.
- [ ] Add additive catalog migration, repository, and revision/review service
  operations with transactional append-only writes.
- [ ] Add immutable snapshot publication through the existing evaluation Run /
  Artifact services and register the Artifact schema.
- [ ] Add representative contract fixtures and contract/integration coverage
  for every acceptance criterion and failure path.
- [ ] Run focused and full regression verification, including available
  persistence/restart coverage.

## Open Questions

None. Initial controlled taxonomy values and dataset-size bounds are technical
defaults that must remain explicit in contracts/tests; they do not invent
metric thresholds or an initial proprietary corpus.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-016
  and direct S-002/S-005/S-014 implementation contracts.
