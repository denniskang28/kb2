# FEAT-002: Configurable Ingestion Engine

- **Status:** Mapped
- **Phase:** Lite Core
- **Optional Design:** Approved

## Outcome And Boundary

Let an engineer select or resolve a declarative Ingestion Profile that composes
reusable plugins to turn varied complex documents into validated Canonical
Documents, chunks, embeddings, and search artifacts without copying an
end-to-end script.

## Source Routing

- Requirements: `REQ-002` through `REQ-006`, `REQ-008`
- Core Design: `DES-002` through `DES-008`, `DES-014` through `DES-016`
- UI Reference: None

## Confirmed Shared Rules

- Profiles compose extraction, structure, chunking, enrichment, embedding, and
  indexing axes; business type alone does not create a whole custom pipeline.
- Every plugin is registered, schema-validated, and invoked through a common
  runner boundary.
- All parser paths normalize into `CanonicalDocument/v1`; downstream plugins
  do not consume provider-native objects.
- Explicit fallback is traceable; runtime failure never causes silent provider
  switching.
- Representative native, scanned, layout-rich, table-heavy, presentation,
  spreadsheet, and long-hierarchical strategies reuse common components.

## Dependencies And Risks

- Depends on FEAT-001 for Registry, Artifact, run, and trace contracts.
- Canonical Document breadth can become speculative; fixtures and downstream
  citation/evaluation needs must justify each field.
- Parser and OCR dependencies may require separate containers and substantial
  local resources.
- Too many complete Profiles recreate a script-per-document design; component
  axes and benchmark evidence must control growth.

## Story Index

| Story | Outcome | Primary Source Coverage | Status |
|---|---|---|---|
| S-004 | Ingestion Profile compilation and deterministic resolution | REQ-002 through REQ-005; FD-001, FD-004 | Confirmed |
| S-005 | Canonical Document and normalization boundary | REQ-003, REQ-006, REQ-008; FD-003 | Confirmed |
| S-006 | Representative parser and OCR Plugins | REQ-005, REQ-006, REQ-008; FD-002, FD-003 | Confirmed |
| S-007 | Hierarchy, reading order, and table preservation | REQ-006, REQ-008; FD-003, FD-004 | Confirmed |
| S-008 | Citation-preserving chunking and enrichment | REQ-005, REQ-006, REQ-008; FD-003, FD-004 | Confirmed |
| S-009 | Provider-neutral embedding and local index Artifacts | REQ-003, REQ-005, REQ-008; FD-002, FD-003 | Confirmed |
| S-010 | End-to-end Ingestion execution and validation | REQ-003 through REQ-008; FD-001 through FD-004 | Confirmed |

All routed REQ-002 through REQ-006 and REQ-008 are compiled into at least one
Story. Shared Feature rules and non-goals apply to every Story above.

## Open Boundary Questions

None. Shared behavior is confirmed in
`docs/designs/features/FEAT-002-configurable-ingestion-engine.md`.

## Change History

- **2026-09-10:** Created and confirmed the Feature boundary.
- **2026-09-11:** Compiled S-004 through S-010; Story boundaries await user
  confirmation.
- **2026-09-11:** User confirmed S-004 through S-010 Story boundaries.
