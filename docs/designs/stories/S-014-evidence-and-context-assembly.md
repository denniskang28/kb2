# Story Design: S-014 - Evidence And Context Assembly

## Status
Approved for Story Pipeline development.

## Story Contract Snapshot
- Story: `S-014`, confirmed 2026-09-11.
- Sources checked: the Story contract; `FD-006`; `DES-011`; current query
  compiler, retrieval/fusion/reranking contracts, ChunkSet, CanonicalDocument,
  Plugin Registry, and their direct tests.
- Material decisions requiring approval: None. Pipeline invocation authorizes
  the choices below.

## AC To Design Mapping
| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add immutable `EvidenceSet/v1`, `EvidenceItem`, citation mapping, source Index Artifact binding, and deterministic IDs. Resolve item text, chunk identity, locators, and lineage from the selected candidate plus the pinned `SearchIndexResult`. | Contract fixtures prove stable keys, source mapping, contributor/scores, and deterministic bytes. |
| 2 | Add a deterministic local context assembler with declared item/token/excerpt bounds, optional bounded structural expansion, de-duplication, and a decision record for every supplied or expansion candidate. | Golden budget, expansion, deduplication, and repeated-run integration scenarios. |
| 3 | Derive prose/hierarchy source identities from `SearchDocument` citations/hierarchy and table evidence from table-element citations plus a bounded table excerpt. | Prose, hierarchy, and table fixture assertions preserve exact typed locators and source element IDs. |
| 4 | Validate Artifact type/digest, candidate-set identity, index affinity, candidate-to-index mapping, locators, bounded excerpts, and unique citation keys before emitting an Artifact. | Invalid/malformed/stale/forged Artifact and contract payload tests assert no output publication. |
| 5 | Persist an explicit, bounded shortage result in `EvidenceSet/v1`; the assembler has no retriever dependency and never expands beyond declared structural rules/budgets. | Empty, below-minimum, and budget-exhaustion scenarios assert shortage and no undeclared candidates. |

## Current Code Findings

- `QueryProfileCompiler` already requires a `context` stage whose `evidence`
  output reaches `final_state`. It has named, schema-exact ports, so a context
  plugin cannot accept an untyped union of retrieval, fusion, and rerank
  Artifacts.
- Retrieval candidates preserve chunk, canonical element IDs, locators, ranks,
  safe scores, and structural projection. Fusion retains contributor candidates;
  reranking retains its complete inclusion/exclusion decisions and the fused
  contributor history.
- `SearchIndexResult` is the bounded content source available to query stages:
  it contains `SearchDocument` chunk text, citations, hierarchy, table-element
  references, and parent/child relations. Its bound Artifact reference is the
  reproducible lineage root; the Trace Artifact parent chain resolves it back
  to the source ChunkSet and CanonicalDocument artifacts.
- The current baseline Profile fixtures use a temporary `query.context@1`
  compiler-only descriptor with an `opaque.bytes` output. That placeholder must
  be replaced with the delivered evidence descriptor and `evidence.set/v1`
  output in Story-owned fixtures/tests.

## Proposed Approach

### Contracts And Identity

Create `kb2_runtime/evidence/` with Pydantic contracts, deterministic
serialization/identity helpers, a local assembler port/implementation, and a
Plugin Registry adapter.

`EvidenceSet/v1` will contain the selected items, all bounded context decisions,
the bound Search Index Artifact (`id`, digest, type, revision), source candidate
set identity, resolved context plugin/configuration/implementation identities,
and a `shortage` record. It will have a deterministic `evidence_set_id` derived
from this complete canonical payload.

Each `EvidenceItem` will include a deterministic `evidence_id`, a stable
unique `citation_key`, document/chunk IDs, ordered canonical element IDs and
their exact typed locators, a bounded excerpt, contributor identities, finite
safe stage scores, and bounded structural/table metadata. It deliberately
excludes embeddings, provider payloads, raw source bodies, and arbitrary
metadata. Citation keys are derived from source identity (document, chunk,
element/locator pairs), rather than selection position, so a retained source
has the same answer-visible key across compatible assemblies.

`ContextDecision` records the source chunk and an enum reason such as
`included`, `excluded_budget`, `deduplicated`, `expanded_parent`, or
`expanded_neighbor`, plus only bounded rank/score facts. Decisions cover every
input candidate and every attempted expansion. The explicit `EvidenceShortage`
record reports configured minima, selected count/tokens, and a bounded reason;
it is data for S-015 final-state validation, not a trigger for retrieval.

### Configuration And Algorithm

Define a closed `ContextAssemblerConfig` with finite bounds: `max_items`,
`max_tokens`, `max_excerpt_chars`, `minimum_items`, optional parent expansion,
and a small non-negative neighbor window. It may also select a closed
structural rule (`none`, `hierarchy`, or `table`) and a bounded source-diversity
mode. Defaults remain conservative and all expansion is opt-in. Validation
rejects contradictory minima, unbounded excerpts, or unsupported rules.

The local assembler accepts a normalized ranked source and `SearchIndexResult`:

1. Validate input Artifact digests and canonical source-set IDs; validate
   index/document affinity and that every candidate chunk/element/locator is
   exactly present in the pinned index.
2. Normalize the supported input (`RetrievalCandidateSet/v1`,
   `FusionCandidateSet/v1`, or `RerankedCandidateSet/v1`) into ordered source
   candidates while retaining all contributor attribution and safe scores.
3. Traverse candidates by `(rank, chunk_id)`. Derive a deterministic excerpt
   from bounded indexed chunk text and add an item only when item and token
   budgets permit. Record all non-selected candidates.
4. When explicitly configured, attempt parent then immediate indexed neighbors
   in a fixed relative order. Enforce the same budgets, source-diversity rule,
   and source-identity de-duplication; record each expansion or duplicate.
5. Render a table excerpt only from the selected bounded chunk text and retain
   the exact table element/locator pairs. No full table, vectors, or provider
   content is copied into Evidence.
6. Compute shortage after assembly and serialize only the resulting
   `EvidenceSet/v1`. The code has no retrieval call path.

Because registry ports are schema-exact, expose three allowlisted adapters over
the same assembler and configuration model:

- `context.from-retrieval@1`: `retrieval.candidate.set` + `search.index.result`
- `context.from-fusion@1`: `fusion.candidate.set` + `search.index.result`
- `context.from-rerank@1`: `rerank.candidate.set` + `search.index.result`

Each emits `evidence.set/v1`. This keeps a Profile declarative and typed while
allowing context after any ranked stage. Update baseline Profile fixtures to
bind the correct candidate output and the existing `search.index` input.

The plugin adapter follows the established retrieval/reranking sequence:
decode and validate inputs, construct a typed request using the invocation
configuration digest, run the local port, recompute expected set identity, then
emit one `evidence.set/v1` Artifact. Add explicit context input/candidate error
codes and context validation, shortage, selection, exclusion, expansion, and
duration metrics/quality signals. Add `evidence.set/v1` to trace-supported
schemas and export the new public contracts.

## Relevant Impacts

- **API/data:** Adds the internal typed Artifact schema and three registered
  context Plugin descriptors. Query Profile fixture sources switch their
  context output from placeholder `opaque.bytes` to `evidence.set/v1` and bind
  the pinned index as a second input. There is no HTTP endpoint or UI change.
- **Lineage/reproducibility:** Evidence pins the exact Search Index Artifact and
  source candidate-set identity; existing Artifact parent manifests provide the
  trace path to ChunkSet and CanonicalDocument. IDs and bytes are canonical and
  repeatable for the same inputs/configuration.
- **Security:** Configuration is closed Pydantic data and remains subject to
  registry executable-configuration rejection. Excerpts, diagnostics, and
  metadata are bounded; no provider payload or embedding crosses the boundary.
- **Compatibility:** Existing retrieval/fusion/rerank Artifact contracts are
  read-only inputs. Query fixture/compiler test registries need matching real
  evidence ports; no migration is required because no persisted Evidence
  Artifact exists yet.

## Alternatives And Risks

- A single context descriptor with a polymorphic candidate port was rejected:
  it would weaken the compiler's exact Artifact-port validation. Three
  descriptors retain the existing allowlisted, typed architecture.
- Passing a full CanonicalDocument into every context stage was rejected: it
  widens the plan input and context surface. The pinned search Artifact already
  carries the bounded source text and exact locators; Trace parent lineage is
  the resolution mechanism for the original Canonical Artifact.
- Table cell-level rendering is limited to information already present in the
  indexed chunk. The implementation must not synthesize cell IDs or pull a
  complete table. A future richer table projection needs its own Story/contract.

## Test Strategy

- Add evidence contract tests for set/item/citation/decision validation,
  deterministic canonical bytes/IDs, finite score and bounds enforcement, and
  rejected duplicate citation keys or incompatible identities.
- Add integration tests through `PluginExecutor` using existing table-heavy and
  long-hierarchy fixtures: retrieval-to-context, fusion-to-context, and
  rerank-to-context paths; assert source locators, contributor preservation,
  table/hierarchy identity, output Artifact schema, and unchanged inputs.
- Cover exact budget boundaries, parent/neighbor expansion order, duplicate
  expansion, source-diversity exclusion, no-candidate and below-minimum
  shortages, and repeated-run byte equality.
- Cover stale digest, forged set ID, mismatched index/document, malformed
  locator, overlong excerpt, duplicate citation key, cancellation, unavailable
  plugin, and no-publication failure behavior.
- Update query Profile compiler fixtures/tests to validate the new named
  context ports and `evidence.set/v1` flow to `final_state`; run focused
  evidence/query/fusion regression tests, then the project suite.

## Implementation Checklist

- [ ] Add evidence contracts, serializer, local normalized assembly port, and
  deterministic ID validation.
- [ ] Add context plugin adapters, error codes, registry descriptors/exports,
  and trace schema registration.
- [ ] Update baseline Query Profile fixture bindings and compiler test registry.
- [ ] Add contract and integration coverage for all AC scenarios and failures.
- [ ] Run focused and full regression verification.

## Open Questions

None. The bounds above are implementation defaults subject to test calibration;
they remain explicit Profile configuration, not hidden runtime behavior.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-014
  and direct implementation contracts.
