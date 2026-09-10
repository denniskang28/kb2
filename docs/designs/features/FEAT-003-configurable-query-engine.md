# Feature Design: FEAT-003 - Configurable Query Engine

## Status

Approved - 2026-09-10

## Bounded Design Purpose

Define the common Query Profile, stage, Evidence, context, and final-state
behavior needed before query Stories select physical providers and APIs.

## Source Anchors

- `docs/features/FEAT-003-configurable-query-engine.md`
- `docs/prd.md#REQ-009` through `REQ-011`
- `docs/core-design.md#DES-002` through `DES-004`, `DES-009` through `DES-012`,
  `DES-014` through `DES-016`

## Shared Design Records

### FD-005: Typed Query Stage Model

- **Status:** Confirmed
- **Applies To:** Query Profile compiler, executor, adapters, and trace

A Query Profile expands into an ordered typed plan drawn from:

```text
Question
  -> Analyze / Rewrite / Route
  -> Retrieve[1..n]
  -> Fuse
  -> Rerank
  -> Context
  -> Generate
  -> Verify
  -> Repair[0..bounded]
  -> FinalState
```

Profiles can omit optional stages and can declare bounded branches by question
or document characteristics. They cannot introduce arbitrary code or bypass
Evidence and final-state validation. Each retrieval contributor retains its
own candidate list and metrics before fusion so experiments can attribute
changes.

A Query run snapshot pins the resolved Query plan and exact Search Artifact,
plugin, model, prompt, and parameter identities. Query trace payloads use
bounded inputs/outputs or Artifact references rather than unbounded prompts and
provider responses.

### FD-006: Evidence, Context, And Answer Validation

- **Status:** Confirmed
- **Applies To:** Retrieval, fusion, rerank, context, generation, verification

Retrievers return `RetrievalCandidateSet/v1`; fusion/reranking produces ranked
candidates; context assembly produces `EvidenceSet/v1`. Evidence items contain:

```text
evidence_id, citation_key, document_id, chunk_id,
canonical_element_ids, source_locator, excerpt,
contributing_retrievers, safe stage scores, metadata
```

Context assembly performs declared deduplication, optional parent/neighbor
expansion, source diversity, structural rules, and token/item bounds while
preserving citation mappings. Table-aware Evidence may include a bounded
rendered region plus exact sheet/range or table/cell identity.

Generation receives only the assembled Evidence and declared session/question
input. Verification checks required citation keys, evidence support, forbidden
content, and Profile-specific answerability rules. A repair receives the
verification failures and the same Evidence; it cannot retrieve silently or
widen context unless an explicit bounded loop exists in the resolved plan.

### FD-007: Baseline Query Profile Families

- **Status:** Confirmed
- **Applies To:** Initial retrieval/query Stories and evaluation slices

Initial families are configuration examples over shared plugins:

- `text-hybrid`: keyword and vector retrieval, fusion, optional rerank;
- `hierarchy-aware`: section/title candidates plus parent-child expansion;
- `table-aware`: table/row/column candidates plus structural context;
- `high-precision-fact`: stricter rerank, evidence threshold, verification, and
  abstention;
- `section-summary`: section-level retrieval with broader bounded context.

They are not separate query services. The same query can run against multiple
Profiles in an offline comparison. Automatic runtime Profile routing is limited
to deterministic declared question/document classification and always records
the selected plan; experimental calls may select a Profile explicitly.

## Verification Direction

- Query compiler tests reject incompatible stage and Artifact combinations.
- Golden retrieval fixtures verify candidate preservation through fusion,
  reranking, context, and citation mapping.
- Answer tests cover supported, insufficient, ambiguous, invalid-citation, and
  repair-exhausted states.
- The same fixed indexed Artifacts execute under at least two Query Profiles
  without code or index mutation.

## Open Cross-Story Questions

None. Exact algorithms, thresholds, prompt text, and providers are selected and
calibrated in Story design and FEAT-004 evaluation.

## Change History

- **2026-09-10:** Created and approved FD-005 through FD-007.
