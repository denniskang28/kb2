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

Not yet decomposed. Suggested boundaries: Profile schema/compiler/resolver;
Canonical Document; parser/OCR adapters; structure/table normalization;
chunking/enrichment; embedding/index Artifact construction.

## Open Boundary Questions

None. Shared behavior is confirmed in
`docs/designs/features/FEAT-002-configurable-ingestion-engine.md`.

## Change History

- **2026-09-10:** Created and confirmed the Feature boundary.
