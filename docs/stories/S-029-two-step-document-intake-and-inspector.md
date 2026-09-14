# S-029: Two-Step Document Intake And Unified Document Inspector

- **Parent Feature:** FEAT-005
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-005, S-008, S-010, S-024, S-028

## Outcome

Let engineers select a real local document, review server-owned detection and
Profile resolution before persistent submission, and inspect the resulting
document content and related RAG Chunks through one document-centered view.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-004`, `DES-005`, `DES-007`, `DES-008`, `DES-011`, `DES-016` | Confirmed through 2026-09-11 |
| FD | `docs/designs/features/FEAT-002-configurable-ingestion-engine.md#FD-003`, `FD-004` | Approved 2026-09-10 |
| UI | `docs/ui/reference.md#UI-003`, `UI-005`, `UI-013` | Confirmed 2026-09-11 |
| Story | `docs/stories/S-024-document-ingestion-and-artifact-ui.md`, `docs/stories/S-028-persisted-document-list.md` | Implemented through 2026-09-15 |

## Inherited Requirements And Constraints

- Preflight, document characteristics, Profile compatibility, matched rules,
  resolved plan, Artifact relationships, and Chunk/source locators come from
  engine/control APIs; the browser does not derive them. `[REQ-017][DES-007]`
- A preflight may send bytes to the local service for bounded temporary
  inspection, but it does not persistently register an uploaded document.
  Persistent Source Artifact registration and the list record occur only when
  the user confirms the resolved Profile and creates a new Ingestion Run.
  `[DES-004][DES-008][S-024][S-028]`
- Explicit Profile selection takes precedence over automatic resolution.
  Automatic resolution shows observable features, evaluated rules,
  candidates, and the selected Profile. `[DES-007][FD-004]`
- The inspector follows typed Artifact lineage from the selected persisted
  source through the latest deterministically related Ingestion Run. It does
  not merge repeated submissions or infer relationships from filenames.
  `[DES-004][DES-008][S-028]`
- Canonical elements and Chunks retain stable IDs and format-appropriate source
  locators. Chunk excerpts remain bounded and raw vectors, storage locators,
  filesystem paths, and provider-native payloads remain hidden.
  `[DES-005][DES-011][FD-003]`
- Any externally backed selected stage is disclosed before Run creation. The
  UI must not make the prototype's unsupported fully-offline claim.
  `[DES-016][UI-003]`

## Relevant UI Reference

- Two-step upload and Profile selection: `docs/ui/kb_ui.zip!/Knowledge Engine
  Lite.dc.html:1312` (`upOpen`), including step identity, preflight facts,
  automatic/explicit Profile selection, matched rules, and the final start
  command.
- Document-row inspector command: archive entry line 316 (`d.openArt`).
- Unified Artifact/source surface: archive entry line 1451 (`artOpen`).
- Visual language: `UI-013`; desktop 1440 x 900 and narrow below 900 px,
  observed around 644 x 900.

## Scope

- A distinct two-step upload interaction: local file selection first, followed
  by server-owned preflight and Profile resolution before final submission.
- Real detection facts supported by the detector, automatic and explicit
  compatible Profile choices, matched-rule rationale, resolved-plan identity,
  and applicable external-stage disclosure.
- Final confirmation that persistently registers the Source Artifact, creates
  a new immutable Ingestion Run, and routes to Run diagnosis.
- One document-row Artifact Inspector command backed by a document-centered
  server projection that resolves the persisted source, latest related Run,
  applicable Canonical/table Artifacts, and latest applicable ChunkSet.
- Format-appropriate source content preview, including a real bounded PDF page
  view for the representative PDF path, plus applicable Canonical, structure,
  table, Chunks, metadata, and lineage tabs.
- Chunk inspection with bounded content, stable Chunk and canonical element
  identities, parent/child facts when present, citations, and synchronized
  format-appropriate source locators.
- Loading, unavailable, expired-preflight, recoverable-error, and partial-view
  states at desktop and narrow widths.

## Non-goals

- Browser-side document parsing, Profile resolution, Artifact lineage
  inference, or PDF text extraction.
- Persisting a document before final Run creation, upload-only lifecycle,
  deduplication, document versioning, deletion, publication, or retention.
- Displaying raw embeddings, unbounded document content, provider payloads,
  storage locators, local paths, or credentials.
- Row-level rerun or Query Lab shortcuts, multi-Run history selection inside
  the document inspector, or copying synthetic prototype facts.
- Guaranteeing a graphical page renderer for every document format; unsupported
  formats expose the safest applicable structured or text projection and an
  explicit unavailable state.

## Acceptance Criteria

1. Activating Upload opens step 1 with a real local-file control and no Profile
   choice or persistent submission. Selecting a supported file and requesting
   preflight sends it to the local service and transitions to step 2 without
   adding a document-list row.
2. Step 2 presents the filename and all detector-supported bounded facts,
   automatic selection, compatible explicit Profile choices, matched rules,
   selected Profile rationale, and resolved-plan identity. Changing the
   Profile produces a fresh server-owned preview and invalidates the prior
   submission authority.
3. The final action remains unavailable until the current preflight, selected
   Profile, and any required external-stage acknowledgement are valid. On
   confirmation it creates exactly one new Ingestion Run and persistent source
   record, then opens that Run; cancellation, expiry, replacement, and failed
   confirmation do not fabricate a list row.
4. Each eligible persisted-document row exposes one eye-style document
   inspector control. Eligibility and all related Artifact IDs come from the
   server projection; unsupported or unavailable views are omitted or
   explicitly marked rather than represented by inert controls.
5. The document inspector opens with a real format-appropriate source preview.
   For the representative PDF path it shows bounded page content and supports
   navigation to a server-authorized page/region without exposing a storage
   locator or filesystem path.
6. Applicable tabs expose Canonical elements, structure, tables, Chunks,
   metadata, and lineage from the selected source and its latest related Run.
   A Chunk row shows its bounded content, stable identity, source element IDs,
   parent/child identities when present, token count when available, and
   citations/source locators.
7. Selecting a Canonical element, table, Chunk, or citation synchronizes the
   corresponding source locator in the preview when that renderer supports the
   locator. Missing content, a missing latest Run, or a missing ChunkSet keeps
   the remaining applicable views usable and explains the unavailable view.
8. Inspector and preflight APIs return bounded safe projections only. Repeated
   submissions remain distinct, latest-Run selection is deterministic, and no
   raw vectors, credentials, provider payloads, storage locators, or local
   filesystem paths reach the browser.
9. At 1440 x 900 and the observed 644 x 900 narrow context, both upload steps,
   document preview, tabs, Chunk list/detail, errors, and close/cancel controls
   remain reachable without page-level overlap; keyboard focus is contained
   and restored for modal and inspector interactions.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-3 | Preflight lifecycle, Profile replacement, disclosure, single persistent submission, expiry/cancel/failure, and Run routing | Contract and end-to-end |
| 4, 6-8 | Document-centered projection, deterministic lineage, partial availability, bounded content, identity, and safe-field exclusions | Contract and integration |
| 5-7 | Representative PDF content rendering, page/region navigation, Chunk/source synchronization, and unavailable renderer states | Browser and integration |
| 9 | Desktop/narrow step, preview, Chunk, loading, and failure comparisons plus focus/overflow checks | Visual regression and accessibility |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 1-3, 9 | UI-003, UI-013 | 1440 x 900 and 644 x 900 | Step 1; step 2 automatic; explicit Profile; disclosure; expired/error | Reference-aligned two-step modal with dense facts, clear current selection, stable commands, and no overlap | Screenshot comparison and interaction recording |
| 4-7, 9 | UI-005, UI-013 | 1440 x 900 and 644 x 900 | PDF preview; Canonical/table; populated Chunks; partial/unavailable | One large document-centered inspector with applicable tabs, real source content, bounded Chunk facts, and synchronized selection | Screenshot comparison and interaction recording |
| 4, 9 | UI-003, UI-013 | 1440 x 900 and 644 x 900 | Eligible and unavailable document rows | One eye-style inspector control only when the server projection permits inspection | Screenshot comparison and geometry assertions |

## Open Questions

None. The user confirmed the two-step intake and document-centered source/Chunk
inspection boundary on 2026-09-15. Exact renderer, endpoint, paging, and
lineage-query choices belong to Story design.

## Relationships And Blocks

- Refines S-024's existing upload/preflight and schema-conditional Artifact
  inspection behavior without changing ingestion engine semantics.
- Replaces S-028's separate Source/Output inspector buttons with one
  server-authorized document-centered inspector command.
- Reuses S-005 CanonicalDocument, S-008 ChunkSet, and S-010 persisted Run and
  Artifact lineage. It does not change their schemas unless Story design finds
  a confirmed projection cannot be produced from persisted evidence.
- Requires no Feature remapping or global product reapproval.

## Change History

- **2026-09-15:** Compiled from the user-confirmed two-step upload and unified
  file-content/RAG-Chunk inspection correction. Story boundary is confirmed
  and eligible for just-in-time design and delivery.
- **2026-09-15:** Implemented the server-owned two-step intake, exact-source
  document Inspector, bounded typed Canonical/table/Chunk/lineage views,
  authorized PDF Range preview, synchronized locators, complete table-cell
  continuation, safe observability, and responsive interaction states.
  Independent acceptance and repaired final review passed.
