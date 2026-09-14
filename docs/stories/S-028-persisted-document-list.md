# S-028: Persisted Document List

- **Parent Feature:** FEAT-005
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-002, S-010, S-022, S-024

## Outcome

Let engineers scan the documents already persisted by ingestion submissions and
continue Run or Artifact diagnosis directly from the Documents page.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-004`, `DES-005`, `DES-008` | Confirmed 2026-09-10 |
| UI | `docs/ui/reference.md#UI-003`, `UI-005`, `UI-013` | Confirmed 2026-09-11 |
| Feature | `docs/features/FEAT-005-knowledge-engine-experiment-workbench.md` | Mapped 2026-09-10 |
| Story | `docs/stories/S-024-document-ingestion-and-artifact-ui.md` | Implemented 2026-09-13 |

## Inherited Requirements And Constraints

- The Documents page consumes engine/control API projections and does not infer
  document, Run, Profile, or Artifact state in the browser. `[REQ-017][FEAT-005]`
- A list record represents one persistently registered source Artifact created
  by an ingestion submission. A file held only by an unconfirmed or expired
  preflight is not an uploaded document record. `[DES-004][S-024]`
- Repeated submissions remain separate records even when filenames or content
  digests match; the list does not introduce user-facing document versioning or
  deduplication. `[DES-004][DES-008]`
- Document identity, source metadata, resolved Profile, related Run, processing
  state, and Artifact actions come from persisted Run/Artifact evidence. Missing
  optional facts are shown as unavailable rather than synthesized. `[DES-004][DES-005][DES-008]`
- Document rows preserve the existing Run and Artifact diagnostic identifiers
  and reuse the S-024 inspector and immutable-plan recovery rules. `[UI-005][S-024]`
- The 2026-09-14 user-provided screenshot confirms a populated dense document
  list as the intended direction. Its example names, values, status labels, and
  icon actions are not production data or independently adopted behavior.

## Relevant UI Reference

- Documents list and upload command: `docs/ui/kb_ui.zip!/Knowledge Engine
  Lite.dc.html:265` (`isDocs`).
- Existing upload/preflight dialog: archive entry line 1312 (`upOpen`).
- Existing Artifact inspector: archive entry line 1451 (`artOpen`).
- Visual language: `UI-013`; desktop 1440 x 900 and narrow below 900 px,
  observed around 644 px.

## Scope

- Server-backed listing of persisted document submissions on the existing
  Documents page.
- Bounded document facts: stable source identity, filename, format or media
  type, byte size, processing class when available, resolved Ingestion Profile,
  latest related Run, and authoritative processing state.
- Deterministic bounded paging and refresh, with populated, loading, empty, and
  recoverable-error states.
- Contract-permitted navigation to the latest related Run and inspectable source
  or output Artifacts, while preserving the existing upload/preflight command.
- Responsive dense-table presentation using the adopted workbench language.

## Non-goals

- Delete, archive, rename, publish, approve, retain, synchronize, or version
  document workflows.
- Treating equal filenames or content digests as versions of one logical
  document, or silently deduplicating submissions.
- A separate upload-without-Run lifecycle or a synthetic `NOT_INGESTED` state.
- Browser-derived processing state, fake document metadata, raw content in list
  responses, or exposing storage locators and local filesystem paths.
- Copying the screenshot's prototype data or adopting every pictured column and
  action literally.

## Acceptance Criteria

1. After an ingestion submission persistently registers its source Artifact,
   the Documents page lists that submission after refresh and after a normal
   runtime restart; preflight-only files never appear.
2. Each row shows its stable source identity, filename, format or media type,
   byte size, processing class when available, resolved Ingestion Profile,
   latest related Run, and authoritative processing state. Unavailable optional
   facts are explicitly marked and no row value is inferred in the browser.
3. Repeated submissions produce distinct rows. The server selects the latest
   related Run deterministically from persisted lineage, and Run state changes
   become visible without merging records by filename or digest.
4. A row exposes only actions supported by its projection: open the latest Run
   when present and inspect an available source or output Artifact through the
   existing S-024 inspector. No lifecycle or destructive action is present.
5. Bounded paging and refresh preserve stable ordering without duplicate or
   missing rows, and loading, first-use empty, populated, and recoverable-error
   states keep the upload/preflight command available.
6. List APIs and rendered rows expose bounded safe metadata only; they do not
   return raw document content, credentials, provider payloads, storage
   locators, or local filesystem paths.
7. At 1440 x 900 the page presents the populated list as a dense ruled table
   with the upload command in the page command area. Below 900 px, including the
   observed 644 x 900 context, controls, row content, and scoped overflow remain
   reachable without page-level overlap.
8. Reviewed screenshots cover populated, empty, loading, and recoverable-error
   list states at desktop and narrow contexts and visibly follow UI-003 and
   UI-013 without copying synthetic prototype values.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-3 | Persistence/restart, lineage, repeated-submission, ordering, and state-transition scenarios | Integration |
| 2, 4-6 | List projection, paging, action eligibility, bounded metadata, and failure-state assertions | Contract and end-to-end |
| 7-8 | Desktop/narrow populated and exceptional-state comparisons plus overflow checks | Visual regression |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 7-8 | UI-003 | 1440 x 900 | Populated | Dense ruled document table, compact facts and statuses, and page-level upload command | Screenshot comparison |
| 5, 8 | UI-003 | 1440 x 900 | Loading, first-use empty, recoverable error | Stable list region and reachable upload command without fabricated rows | State screenshots |
| 7-8 | UI-003, UI-013 | Narrow below 900 px; observed around 644 x 900 | Populated and exceptional states | Readable controls and row content with scoped overflow and no incoherent overlap | Screenshots and geometry checks |
| 4, 7 | UI-005, UI-013 | Desktop and narrow contexts above | Run and Artifact actions available or unavailable | Only contract-permitted controls appear and preserve the adopted focus and semantic-state language | Interaction and screenshot evidence |

## Open Questions

None. Exact API shape, page bounds, stable sort key, persistence projection, and
responsive table mechanics belong to Story design.

## Relationships And Blocks

- Extends the document-list portion of S-024 without changing its preflight,
  Ingestion Run, or Artifact inspection behavior.
- Uses S-002 and S-010 persisted Run/Artifact evidence; it does not change their
  engine contracts unless Story design finds the required source metadata is
  not persisted safely.
- Requires no Feature remapping or global product reapproval.

## Change History

- **2026-09-14:** Compiled after change triage classified the missing persisted
  document list as a Story-level correction. The user confirmed the direction
  and bounded scope; the compiled Story awaits explicit contract confirmation.
- **2026-09-14:** User explicitly confirmed the compiled S-028 Story boundary;
  it is eligible for just-in-time technical design and delivery.
