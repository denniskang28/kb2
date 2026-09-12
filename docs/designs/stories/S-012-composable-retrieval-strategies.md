# Story Design: S-012 - Composable Retrieval Strategies

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-012-composable-retrieval-strategies.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; pipeline delivery
  started 2026-09-12.
- **Material Decisions Requiring Approval:** None. The Story Pipeline invocation
  authorizes the bounded local retriever, candidate-schema, and trace choices
  below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add frozen `RetrievalCandidateSet/v1` / candidate contracts and canonical serialization. Every result carries the selected Search Artifact identity, source document/chunk/Canonical element IDs, locator, contributor ID, rank, and safe normalized score. Local retrievers read only a supplied `SearchIndexResult/v1` and retain its citation-bearing fields. | Contract fixtures for prose, hierarchy, and table data assert schema validity, stable bytes, rank order, index/document/chunk/locator lineage, and no native payload leakage. |
| 2 | Register separate keyword, vector, hierarchy-aware, table-aware, and metadata-filter retrieval Plugin descriptors. Each produces its own candidate-set Artifact; no hybrid merging, cross-retriever deduplication, or score comparison occurs here. | Integration executes keyword and vector as distinct stages over the same index, and asserts structural strategy fields plus independent contributor/rank/score lists. |
| 3 | Closed retriever configurations pin declared filters, limit, structural expansion mode, and timeout through the resolved Query plan. Plugins emit bounded stage metrics/signals and the candidate-set payload records the plan/index/contributor identities needed for later trace attribution. | Profile/Registry integration snapshots resolved configuration and plan digest, then asserts deterministic filtered results, limits, tie order, and bounded trace metrics/signals. |
| 4 | Validate Search Artifact identity and payload correspondence before searching; map malformed data, unavailable descriptors, cancellation, deadline timeout, and implementation drift to existing safe Plugin/trace failures without publishing a candidate Artifact. | Resilience matrix asserts a failed attempt and no eligible output Artifact for every case, including stale index Artifact binding. |
| 5 | Define a provider-neutral `RetrieverPort` with strict request/result contracts. The coordinator/Plugin layer dispatches only through registered descriptors, so a synthetic compatible retriever is selected by Profile data and passes the shared suite without engine or compiler branching. | Shared provider conformance fixture runs the baseline and synthetic retrievers; an architecture regression replaces one retriever descriptor/Profile reference only. |

## Current Code Findings

S-009 provides the immutable, portable `SearchIndexResult/v1` payload and the
explicit `HybridSearchPort`. It already contains ordered searchable documents,
chunk citations and locators, hierarchy context, language, bounded document
metadata/enrichments, deterministic BM25/cosine helpers, and a credential-free
hashing embedder. Its `SearchHit` is intentionally an adapter-local result: it
does not contain candidate-set identity, contributor attribution, structural
decision fields, bounds, or safe score validation required by this Story.

S-011 pins an exact `search.index.result/v1` Artifact reference, descriptor
identity, validated stage configuration, and plan digest in immutable Query
plans. Its five initial Profile fixtures still use fixture-only opaque query
descriptors; executable retrieval must replace only the retriever references
and typed ports, while later S-013 through S-015 retain ownership of fusion,
Evidence/context, and complete Query execution.

The existing Plugin Registry and Executor provide the required allowlist,
configuration validation, deadline runner, cancellation publication check,
atomic Artifact commit, and sanitized failed-attempt trace behavior. The
Artifact catalog is additive and existing `RunService` already supports
`EngineKind.QUERY`, although a full Query engine is deliberately owned by
S-015. `IngestionEngine` is not reusable: its six-axis fallback/quality
selection semantics conflict with Query Profile's ordered repeatable retrieval
stages.

## Proposed Approach

### Contracts And Artifact Boundary

Add a sibling `kb2_runtime.retrieval` package:

```text
retrieval/
  contracts.py     # frozen candidate, request/filter/configuration, port models
  serializer.py    # canonical ASCII JSON and digest helpers
  local.py         # pure local keyword/vector/structure selection algorithms
  plugin.py        # SearchIndexResult input -> candidate-set Plugin adapters
```

Extend the supported Artifact catalog with `retrieval.candidate.set/v1`. It is
the sole S-012 output and is immutable. It has no vectors, posting lists,
provider response body, unbounded excerpt, raw query text, secret, or mutable
index/collection handle. Candidate Artifacts parent the selected Search Artifact
and the Stage trace therefore preserves normal Artifact lineage.

`RetrievalCandidateSet/v1` contains a schema version, a semantic candidate-set
ID/digest, the exact index Artifact binding (`id`, content digest, type,
revision), document identity, retriever Plugin/implementation identity,
contributor/stage ID, validated configuration digest, and one bounded ordered
candidate list. The candidate-set ID is the digest of the canonical header and
ordered candidate evidence; each candidate ID is independently derived from
the index identity, contributor identity, and Chunk ID, avoiding a circular
identity definition. A candidate carries document and Chunk IDs; non-empty ordered
Canonical element IDs and their exact typed locators; rank starting at one;
`safe_score` in `[0, 1]`; a `score_kind` label; and a bounded structural
projection. The projection may contain hierarchy path/parent-or-child relation
or table element/row/column context, but never arbitrary document metadata or
provider-native search objects. Validation proves unique candidates/ranks,
source-document consistency, bounded fields, finite scores, and citation/Chunk
binding. S-014 owns excerpts, citation keys, and `EvidenceSet/v1`; this schema
does not preempt it.

`RetrieverRequest` is an in-memory input used by the port and Plugin adapter:
bounded query text (the existing 4096-character bound), one parsed exact
`SearchIndexResult`, the pinned Artifact binding, contributor/stage ID,
validated retriever configuration, and a cancellation event/deadline. The
Plugin receives S-011's existing `opaque.bytes/v1` `query.question` input and
converts it to this transient request after bounded UTF-8 validation; it does
not introduce a second Query ingress schema. The adapter first proves the
supplied Artifact reference is `search.index.result/v1` and its content digest
equals canonical result bytes. A mismatch is a stale index identity; it never
returns an empty-but-eligible candidate set.

### Initial Local Strategies

Register all five separate normal in-process implementations through
`plugins.bootstrap`, with closed Pydantic configurations and named ports:

```text
retriever.keyword@1
retriever.vector@1
retriever.hierarchy@1
retriever.table@1
retriever.metadata@1
  opaque.bytes/v1 + search.index.result/v1 -> retrieval.candidate.set/v1
```

The first input is S-011's established bounded `query.question` binding,
materialized as an `opaque.bytes/v1` Artifact by the eventual Query engine.
S-015 owns materializing it and executing the complete Query plan. S-012
contract and Plugin tests may materialize it through the existing Artifact/Run
services; no new query-input Artifact schema is added.

All configurations require `limit` in `1..100`; optional filters are a closed
combination of language, exact metadata/enrichment primitive equality, and
declared document class labels. Filter keys/values are bounded and no dynamic
expression, path, shell, or arbitrary predicate is accepted. Filter evaluation
is deterministic before ranking. A no-match condition returns a valid empty
candidate set with named `no_candidates` trace evidence; invalid identity,
input, or provider state returns a failure instead.

- **Keyword:** reuse S-009's tokenization/postings and BM25 calculation, then
  normalize only that retriever's eligible scores to `[0, 1]`; ties break by
  Chunk ID.
- **Vector:** reuse the pinned local embedding adapter / vector dot product,
  normalize only vector scores for eligible records, and apply the same tie
  rule. It does not invoke keyword scoring.
- **Hierarchy:** rank lexical relevance against `hierarchy_context` plus chunk
  text. Its declared `relation_mode` is `self`, `parent`, or `children`; it may
  emit only existing linked chunks from the same index and records the relation
  in the structural projection. To retain the S-008 relation contract through
  the S-009 boundary, add bounded `parent_chunk_id` and `child_chunk_ids` to
  `SearchDocument` and populate them in the projector; result validation proves
  the links refer to indexed documents and agree bidirectionally. Expansion is
  bounded by `limit` and cannot silently add a second retrieval pass.
- **Table:** select only chunks with table-capable Canonical citations/locators,
  rank their bounded rendered text lexically, and retain table/cell/sheet-range
  locator fields in the projection. It never invents a table row/column or
  converts a non-table candidate into one.
- **Metadata:** filters eligible indexed document metadata/enrichments first,
  then uses deterministic lexical ranking. Its candidate projection records
  only the matched declared key names, not full metadata values.

Every strategy implements `RetrieverPort.retrieve(request) ->
RetrievalCandidateSet`. The runner-facing Plugins only parse validated inputs,
call that port, serialize canonical output, and report bounded metrics. No
retriever calls another strategy, fuses lists, alters an upstream Artifact, or
exposes raw indexing payloads. A later provider adapter must carry a new Plugin
identity/implementation digest and pass this same port suite.

### Plan Binding, Trace, And Failure Behavior

Update the baseline Query Profile fixture registry and source fixtures so each
retrieval stage names an actual retriever and its established `query.question` /
`search.index` bindings. `text-hybrid` declares two retrieval stages,
`keyword` and `vector`, with separate output logical names; it does not claim a
hybrid result before S-013. `hierarchy-aware` and `table-aware` select their
respective strategy. `high-precision-fact` may declare keyword/vector as
independent contributors with stricter per-stage limits. `section-summary`
uses hierarchy retrieval with a wider but bounded limit. S-011's compiler
continues generic descriptor/port validation; it gains no retriever-mode
branching.

The resolved plan already pins the descriptor, implementation digest, runner,
configuration, index binding, and plan digest. The S-015 executor will verify
the current descriptor still equals that pinned identity before invoking a
stage. This Story's Plugin integration coverage makes that rule executable
without prematurely building a full Query orchestrator.

Each successful stage reports only bounded, query-safe observability:
`retrieval_candidates`, `retrieval_filtered`, `retrieval_duration_ms`, and
per-strategy `retrieval_strategy`; signals `retrieval_validation` and
`no_candidates`. The candidate Artifact holds contributor/stage identity and
ranked output; the standard Stage trace holds Plugin identity, configuration
digest, input/output references, timing, and safe failures. It never logs the
question, query vector, raw score distribution, full metadata, or native
provider payload.

Before materializing output, every adapter checks cancellation; the existing
executor checks it again before commit. Timeouts rely on the descriptor's
bounded runner deadline and propagate the existing safe timeout result.
Malformed query/index/candidate output maps to a new bounded retrieval input or
candidate-validation Plugin error; unavailable Registry capability uses the
existing `PLUGIN_UNAVAILABLE`; stale Artifact/content identity uses a specific
safe retrieval identity error. All fail the stage with no eligible candidate
Artifact. An empty successful list remains distinguishable from failure.

## Relevant Impacts

### Data And Compatibility

This is additive: `retrieval.candidate.set/v1` enters the existing Artifact
catalog, and bootstrap gains retrieval descriptors. `SearchDocument` gains
additive bounded parent/child Chunk relation fields so S-012 can perform the
structural expansion promised by its hierarchy strategy; older indexed payloads
without them deserialize with empty links and support only `self` relation mode.
Newly projected/indexed Artifacts include the fields in their existing canonical
bytes and semantic identities. Query-plan, Profile, trace, and Plugin contracts
remain compatible. The fixture updates intentionally change baseline retrieval
stage ports from S-011 test placeholders to real schemas; compiler tests must
update their fixture registrations together. No database migration, API route,
mutable index collection, or UI work is required.

### Security And Observability

Only Registry-selected implementations execute. Declarative configurations
remain closed data and contain no code, credential, command, path, or external
provider payload. Queries and vectors are read transiently, while trace and
Artifacts retain only bounded identities, ranks, safe scores, structural
context, locators, and safe metrics. The local implementations make no network
call and need no credential or optional capability.

## Alternatives And Risks

- Reusing `SearchHit` as the candidate contract would leak a local adapter
  shape, omit contributor/plan identity, and make S-013 attribution ambiguous.
  A versioned provider-neutral candidate Artifact is required.
- A single configurable `mode` retriever would hide which algorithm produced a
  list and weaken replacement conformance. Separate descriptors make strategy
  identity measurable while Profiles still compose them declaratively.
- Using S-009's combined `search()` for text-hybrid would violate the separate
  keyword/vector requirement. Its shared internals may be factored into pure
  helpers, but each S-012 adapter must calculate and normalize only its own
  channel.
- Implementing full Query run orchestration now would overlap S-015 and
  prematurely determine generation/final-state behavior. This Story provides
  executable Plugins and trace-compatible Artifacts only.

## Test Strategy

Add `tests/contract/test_retrieval.py` for canonical candidate-set validation,
semantic identity, score/rank/candidate uniqueness, locator and Chunk lineage,
score bounds/non-finite rejection, and no-native-payload assertions. Fixed
sanitized fixtures cover prose, hierarchy relations, tables, language and
metadata/enrichment filters.

Add `tests/integration/test_retrieval_plugins.py` using existing in-memory
Artifact/Run services and registered descriptors. Execute all five strategies
over one pinned Search Artifact; assert separate keyword/vector output
Artifacts, deterministic filter/limit/tie behavior, structural fields, parent
lineage, stage metrics/signals, and an empty-but-successful no-match result.
Exercise Artifact content-digest mismatch, malformed index/request, descriptor
unavailability, cancellation before/during invocation, timeout, and invalid
candidate serialization; assert failed stage attempts and no eligible output.

Add Query Profile contract/integration updates proving the five baseline
families compile with the real retrieval descriptors and that plan payloads
pin each strategy/filter/limit/index identity. A shared `RetrieverPort`
conformance fixture must run both a baseline adapter and a synthetic compatible
retriever selected only by descriptor/Profile data; no compiler, coordinator,
or engine dispatch change is permitted. Run focused retrieval, Query Profile,
Indexing, Plugin, Trace persistence, and full regression suites.

## Implementation Checklist

- [ ] Add frozen retrieval candidate-set contracts, canonical serializers,
  supported Artifact schema, and bounded retrieval error codes.
- [ ] Implement deterministic local keyword, vector, hierarchy, table, and
  metadata port adapters with filters, limits, safe-score normalization,
  structure projections, identity validation, cancellation, and metrics.
- [ ] Register the five descriptors/closed configurations and update baseline
  Query Profile fixtures plus their test registry to real typed ports.
- [ ] Add candidate contract, Plugin/integration, plan-pinning, resilience, and
  replacement-conformance coverage; run focused and full regressions.

## Open Questions

None. Fusion, reranking, Evidence/context, full Query execution, external
search adapters, score calibration, and UI presentation are intentionally
deferred to their owning Stories.

## Approval

The S-012 Story Pipeline invocation authorizes this just-in-time technical
design. It records the local retrieval and candidate-contract choices without
changing the confirmed product contract.

## Change History

- **2026-09-12:** Created for the S-012 Story Pipeline delivery run.
