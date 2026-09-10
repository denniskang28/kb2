# Feature Design: FEAT-002 - Configurable Ingestion Engine

## Status

Approved - 2026-09-10

## Bounded Design Purpose

Define the shared Profile, Plugin, Artifact, routing, and execution behavior
needed before the ingestion Feature is decomposed into independently deliverable
Stories.

## Source Anchors

- `docs/features/FEAT-002-configurable-ingestion-engine.md`
- `docs/prd.md#REQ-002` through `REQ-008`
- `docs/core-design.md#DES-002` through `DES-008`, `DES-014` through `DES-016`

## Shared Design Records

### FD-001: Ingestion Profile Structure And Compilation

- **Status:** Confirmed
- **Applies To:** Profile compiler, resolver, executor, and experiment controls

An Ingestion Profile declares metadata plus six independently reusable
component axes:

```yaml
id: scanned-contract
revision: 1
components:
  extraction: scanned-pdf
  structure: legal-hierarchy
  chunking: parent-child
  enrichment: contract-fields
  embedding: local-default
  indexing: local-hybrid
```

Each component expands to typed stages. A stage declares `id`, registered
`uses`, named Artifact inputs/outputs, schema-validated `config`, optional
bounded `when`, and optional explicit fallback candidates with measurable
acceptance conditions. The compiler resolves all references and defaults,
validates graph order and Artifact compatibility, rejects cycles/unbound inputs,
and emits a complete execution-plan snapshot and digest.

The condition language is a restricted expression model over declared document
features and prior quality signals. It has no filesystem, network, environment,
reflection, or code-execution access.

### FD-002: Plugin Descriptor And Runner Protocol

- **Status:** Confirmed
- **Applies To:** Plugin Registry and every ingestion stage implementation

Each Registry descriptor contains:

```text
plugin_id, kind, implementation_digest, runner_type,
config_schema, accepted_input_schemas, output_schemas,
timeout, resource_hints, capabilities
```

The executor sends a `StageInvocation/v1` containing run/stage identity,
resolved configuration, immutable input Artifact references, an output scope,
and a cancellation/deadline value. The runner returns one `StageResult/v1`
with terminal state, output Artifact manifests, bounded metrics and quality
signals, structured error, and timing.

The Python in-process runner and local-container runner implement this same
protocol. A container receives only declared read-only inputs, a bounded output
location, and explicitly allowed settings. Provider-native output may be stored
as a diagnostic Artifact, but it never crosses the stage boundary as an SDK
object.

### FD-003: Artifact Flow And Canonical Boundary

- **Status:** Confirmed
- **Applies To:** Parser, normalizer, structure, chunk, embedding, and index work

The baseline Artifact flow is:

```text
SourceDocument
  -> DetectionReport
  -> ProviderParseResult / OcrResult
  -> CanonicalDocument/v1
  -> ChunkSet/v1
  -> EmbeddingSet/v1
  -> SearchDocumentSet/v1
  -> SearchIndexResult/v1
```

Provider Parse and OCR results remain adapter-specific Artifacts. The
normalizer is the only component allowed to convert them into the common
Canonical Document. Chunk records reference exact canonical element IDs and
source locators. Embedding records reference chunk IDs. Search documents retain
document, chunk, structure, language, metadata, and citation fields without
embedding provider-native payloads.

The first Canonical schema is deliberately minimal: it adds a field only when
at least one representative fixture, downstream query, citation, or evaluation
case consumes it.

### FD-004: Profile Resolution And Controlled Fallback

- **Status:** Confirmed
- **Applies To:** Detection, routing, experiment execution, and diagnosis

The resolver applies the DES-007 precedence and records every candidate rule,
matched feature, and final selection. Base Profile families initially cover:

- native text-bearing documents;
- scanned/OCR documents;
- layout-rich documents;
- table-heavy documents;
- presentations;
- spreadsheets;
- long hierarchical documents.

These families are processing characteristics, not MIME-only or department
labels. A document may use an extraction component selected by format and a
structure/chunk component selected by measured content characteristics.

Fallback uses an explicit `first_acceptable` stage only when every candidate,
order, acceptance metric, cost/resource bound, and failure behavior is in the
resolved plan. Automatic retry preserves the chosen candidate. Trying a new
implementation is a new run, not an invisible retry.

## Verification Direction

- Schema fixtures prove valid and invalid Profile compilation.
- Contract tests run the same sample plugin through in-process and container
  runners.
- Canonical fixtures cover stable source locators, reading order, tables, and
  chunk-to-element lineage.
- Router matrices prove precedence, deterministic resolution, and trace output.
- A new test plugin/Profile is added without changing executor source.

## Open Cross-Story Questions

None. Exact initial plugin implementations and physical schemas belong to Story
technical design, constrained by these records.

## Change History

- **2026-09-10:** Created and approved FD-001 through FD-004.
