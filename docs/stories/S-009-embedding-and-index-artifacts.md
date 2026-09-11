# S-009: Embedding And Local Index Artifacts

- **Parent Feature:** FEAT-002
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-003, S-008

## Outcome

Turn validated Chunks into provider-neutral embedding and searchable local index
Artifacts without binding the engine to one future search provider.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-003`, `REQ-005`, `REQ-008` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-003`, `DES-004`, `DES-006`, `DES-016` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-002-configurable-ingestion-engine.md#FD-002`, `FD-003` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-002-configurable-ingestion-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Embedding and indexing are independent provider ports and Profile axes.
  `[DES-006][DES-016]`
- Embeddings reference Chunk IDs; search documents retain document, chunk,
  structure, language, metadata, and citation fields. `[FD-003]`
- Stages exchange immutable Artifacts and never embed provider-native search or
  model objects in engine contracts. `[DES-004]`
- The initial index is local; Azure adapters are later substitutions requiring
  their own conformance evidence. `[DES-016]`

## Scope

- Versioned embedding, search-document, and index-result Artifact contracts.
- At least one local embedding adapter decision and one local hybrid index path
  selected during Story design.
- Idempotent construction, replacement-safe index identity, trace metrics,
  capability readiness, and failure recovery.

## Non-goals

- Azure AI Search, embedding model administration, raw vector UI, distributed
  indexing, or claiming provider equivalence without evaluation.

## Acceptance Criteria

1. Embedding records bind model/implementation identity and dimensions to exact
   Chunk IDs without duplicating authoritative Chunk content.
2. Search documents preserve fields required for keyword, vector, hierarchy,
   table, metadata, and citation retrieval.
3. Replaying identical inputs/configuration produces traceable idempotent index
   results; changed inputs or providers receive distinct Artifact identity.
4. Dimension mismatch, unavailable optional provider, invalid records, partial
   write, cancellation, or locked segment cannot expose a successful index.
5. The local index can be queried through a provider-neutral contract and a
   synthetic replacement adapter passes the same contract tests.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-3 | Artifact and idempotency fixtures | Contract and integration |
| 4 | Failure/recovery matrix | Resilience |
| 5 | Provider-port conformance suite | Architecture regression |

## Open Questions

None. Initial embedding and local search technologies are Story-design choices.

## Relationships And Blocks

- Enables FEAT-003 retrieval and S-010 end-to-end ingestion.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-002 sources.
- **2026-09-11:** Story boundary confirmed by the user.
