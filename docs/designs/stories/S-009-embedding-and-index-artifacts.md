# Story Design: S-009 - Embedding And Local Index Artifacts

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-009-embedding-and-index-artifacts.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; design prepared for the S-009 Story Pipeline run.
- **Material Decisions Requiring Approval:** None. The pipeline invocation authorizes the local adapter and hybrid-index choices below. They preserve the Story's provider-port and local-first constraints.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add immutable `EmbeddingSet/v1` and `EmbeddingRecord` contracts. The first adapter, `embedder.hashing@1`, produces a fixed 256-dimensional, L2-normalized vector from each exact Chunk ID and normalized chunk content, and records its stable Plugin ID, implementation digest, model label, dimension, and ChunkSet identity. Records contain no duplicate chunk text. | Contract fixtures assert one record per ordered Chunk ID, bounds, normalization, model/implementation identity, fixed dimensions, no content field, and deterministic canonical bytes. |
| 2 | Add `SearchDocumentSet/v1`; projection derives every searchable record from a validated `ChunkSet/v1` plus its `EmbeddingSet/v1`. Each record carries document/chunk IDs, hierarchy, language, bounded metadata/enrichments, citation element IDs and locators, keyword text, and vector reference/values. | Contract fixtures cover prose, hierarchy, table, language, metadata, and locator retention, plus rejection of missing/mismatched Chunk IDs or citation fields. |
| 3 | Build a deterministic `SearchIndexResult/v1` containing semantic `index_id`, input/configuration fingerprints, and a canonical local hybrid payload. The identity hashes ordered SearchDocumentSet content identity, embedding implementation/model/dimension, index implementation, and validated index configuration. Every query is scoped to the supplied result Artifact; no mutable active-index name exists. | Integration coverage runs identical inputs/configuration twice and asserts equal semantic identity/canonical bytes and query results; changing ChunkSet bytes, embedder identity/dimension, or index config produces a different `index_id`. |
| 4 | Validate all payloads before index construction. The indexer uses per-identity async locks and builds an in-memory immutable candidate before returning all outputs through the existing atomic Artifact commit. Cancellation and failures return typed Plugin errors before commit; a failed attempt never publishes a trace-visible index. | Resilience matrix covers dimension/record mismatch, unavailable optional adapter, malformed payload, cancellation, simulated partial Artifact-store/repository write, and concurrent same-identity build with a locked segment. It asserts one terminal failure where invoked, no successful output link, and recovery on a later valid invocation. |
| 5 | Define provider-neutral `EmbeddingPort` and `HybridSearchPort` protocols. Register the local hashing embedder, search-document projector, and local hybrid indexer as normal Plugins; a synthetic replacement embedding/index implementation exercises the same contracts without Registry, executor, or query-port dispatch changes. | Architecture conformance tests run the shared port suite against local and synthetic adapters, including keyword/vector/hybrid queries and citation-preserving hits. |

## Current Code Findings

S-003 supplies immutable, extra-forbidden descriptors and invocations, an allowlisted Registry, capability-aware runner selection, bounded Plugin output, and an executor that commits outputs only via `ArtifactService`. Its common contract already supports ordered multi-output Plugin results and turns validation, cancellation, timeout, crash, and output-limit failures into sanitized failed stage attempts.

S-008 supplies deterministic `ChunkSet/v1` bytes, stable Chunk IDs, content and token bounds, document/hierarchy/language metadata, exact element/locator citations, parent-child relations, and provenance-linked bounded enrichment. The current supported Artifact catalog ends at `chunk.set/v1`. Existing Artifact persistence is content-addressed local filesystem storage plus an atomic PostgreSQL trace transaction, but the storage UUID is intentionally not a reproducible semantic identity. There is no index schema, query service, embedding provider, or persisted mutable search collection yet.

## Proposed Approach

### Contracts And Artifact Flow

Add `kb2_runtime.indexing` with frozen Pydantic contracts and canonical JSON serialization:

```text
indexing/
  contracts.py     # EmbeddingSet, SearchDocumentSet, SearchIndexResult, ports/configuration
  serializer.py    # canonical ASCII JSON and digest helpers
  embedding.py     # deterministic local hashing adapter and embedding validation
  projection.py    # ChunkSet + EmbeddingSet -> citation-preserving search documents
  hybrid.py        # deterministic BM25/cosine build and provider-neutral search
  plugin.py        # registered Plugin adapters
```

Extend `SUPPORTED_ARTIFACT_SCHEMAS` additively with `embedding.set/v1`, `search.document.set/v1`, and `search.index.result/v1`.

The payload progression is strictly typed and immutable:

```text
ChunkSet/v1
  -> EmbeddingSet/v1
  -> SearchDocumentSet/v1
  -> SearchIndexResult/v1
```

`SearchDocumentSet/v1` names the source ChunkSet identity and the source EmbeddingSet identity. The projection Plugin receives both Artifact inputs and rejects cross-document, missing, duplicate, reordered, or dimension-incompatible records. It copies only retrieval evidence needed downstream: document and chunk identity, hierarchy context, language, bounded Canonical metadata and enrichments, ordered citation element IDs/locators, keyword text, and the matching embedding record. It does not preserve raw CanonicalDocument content, provider SDK objects, arbitrary metadata, or provider-native payloads.

`SearchIndexResult/v1` is a portable canonical JSON index artifact, not a provider collection handle. It contains the versioned index implementation identity, validated index configuration, `index_id`, document-set and embedding-set content digests, corpus counts, and the immutable hybrid index payload. Keeping the local index in the Artifact Store permits normal lineage, restart recovery, and content-digest validation without adding a global database table or a mutable replacement pointer. A caller selects the exact successful result Artifact it queries; a new index is therefore replacement safe by construction.

### Initial Local Providers

The first local embedding decision is `embedder.hashing@1`, an in-process, credential-free, deterministic feature-hashing adapter. Its closed configuration has `dimension` fixed at 256 for revision 1 and a bounded declared normalization mode (`l2`). It tokenizes the Chunk's normalized whitespace text using a documented ASCII-lowercase lexical tokenizer, maps unigrams and adjacent bigrams through SHA-256 into signed buckets, then L2 normalizes the resulting vector. The `model_id` is the stable label `local.feature-hash-256@1`; its descriptor implementation digest identifies the exact implementation revision. This is a local reproducibility baseline, not a semantic-model quality claim. A future model-backed adapter must use a new Plugin identity and pass the same port conformance tests.

The initial local index decision is `indexer.local-hybrid@1`, also in process. It builds a canonical JSON payload with a term lexicon/postings needed for BM25-style lexical scoring, document lengths and average length, and ordered 256-dimensional vector records for exact cosine scoring. The index consumes no SQLite, pgvector, external process, network, credentials, model files, or provider collection. PostgreSQL/pgvector remains runtime infrastructure, not the first search-provider dependency; a later pgvector adapter is a distinct provider implementation with conformance and evaluation evidence.

The `HybridSearchPort` accepts an explicit validated `SearchRequest` and a `SearchIndexResult` payload, then returns bounded `SearchHit` values only: chunk/document IDs, score breakdown, hierarchy/language/metadata snapshot, and exact citations. Requests contain a bounded query string, optional structured filter labels, `top_k` (1-100), and lexical/vector weights (non-negative, with at least one positive). The local implementation derives the query vector through the paired `EmbeddingPort`, calculates BM25 and cosine scores over eligible records, normalizes each score channel over the candidate set, sums the configured weighted scores, then breaks ties by `chunk_id`. It never replaces an index, fetches an undeclared Artifact, or exposes index internals. S-012 may consume this port; this Story does not add an HTTP query endpoint.

### Validation, Identity, And Recovery

All contracts are frozen, extra-forbidden, bounded, and serialized with sorted ASCII JSON keys. An embedding record has exactly one Chunk ID, no content field, finite numeric values, the declared positive dimension, and an L2 norm within a documented tolerance. An embedding set has unique ordered Chunk IDs, a nonempty uniform dimension, and the producing Plugin/model/configuration identity used to create it.

Search-document validation proves a one-to-one alignment with the source ChunkSet: matching document ID, Chunk IDs, citation IDs/locators, hierarchy, language, and no additional or missing records. Index construction rejects empty sets, nonfinite vectors, duplicate Chunk IDs, unsupported configuration, corrupt canonical bytes, and mixed dimensions before it materializes any candidate payload. Error codes added at the Plugin boundary are specific but safe, including `EMBEDDING_DIMENSION_MISMATCH`, `EMBEDDING_RECORD_INVALID`, `INDEX_INPUT_INVALID`, and `INDEX_SEGMENT_LOCKED`; their trace mapping remains bounded validation/dependency evidence and contains no chunk text, query, vector, or provider response.

`index_id` is `idx_` plus the first 32 hexadecimal characters of SHA-256 over canonical JSON containing the result schema version, local index implementation digest, normalized index configuration, ordered search-document identity, embedding Plugin/model/dimension identity, and source Artifact content digests. Replaying equals the same semantic `index_id`, payload digest, and search results even though a separate Run may create a distinct trace Artifact UUID. Any changed source bytes, provider/model/implementation/dimension, or configuration changes the identity. This makes reproduction observable without claiming that trace storage IDs themselves are deterministic.

The local builder maintains a process-local keyed async lock only for the calculated `index_id`. It does not let a lock holder publish incrementally; it fully validates and builds the immutable payload, checks cancellation before returning, and releases the lock in `finally`. The existing executor then submits all stage outputs to `ArtifactService.complete_with_outputs`, whose database transaction makes trace records and the successful Stage transition atomic. A filesystem blob left by a failed publish is unreferenced and cannot be read through eligible Artifact lineage. A transient lock/cancellation/write failure is retryable only where the existing runner/storage semantics mark it so; a later valid invocation can build the same identity cleanly.

### Plugin Registration And Capabilities

Register these normal in-process descriptors in `plugins.bootstrap`:

```text
embedder.hashing@1
  chunk.set/v1 -> embedding.set/v1
  input: chunk_set; output: embedding_set

search-document.projector@1
  chunk.set/v1 + embedding.set/v1 -> search.document.set/v1
  inputs: chunk_set, embedding_set; output: search_document_set

indexer.local-hybrid@1
  search.document.set/v1 -> search.index.result/v1
  input: search_document_set; output: search_index_result
```

The local implementations require no optional capability, so core readiness does not depend on an external embedding model or search service. A registered future model/container adapter declares its own optional capability; Registry inspection will report it registered but not runnable when unavailable, and the executor will not start an attempt or expose an index as successful. Descriptors keep named ports and closed config models, so profile resolution and future S-010 execution gain no special-case dispatch.

## Relevant Impacts

### Data And Compatibility

This is an additive Artifact schema and bootstrap-registration change. Existing ChunkSet payloads, trace rows, profile compiler behavior, and S-003 execution interfaces remain compatible. No migration is needed because immutable index state lives in existing Artifact storage and semantic identity is in the versioned result payload. Index revision 1 is intentionally exact/local rather than a performance or managed-provider promise.

### Security And Observability

The selected local path has no credentials, network calls, filesystem paths in Profile data, dynamic model downloads, arbitrary code, or provider SDK objects. All vectors and lexical terms remain Artifact content; traces retain only bounded summaries, metrics, signals, Plugin identity, configuration digest, input lineage, and output references. Metrics include `embedding_records`, `embedding_dimension`, `search_documents`, `index_terms`, `index_vectors`, `index_build_ms`, and `index_reused` where applicable. Signals include `embedding_validation`, `search_document_validation`, and `index_validation`; none include text, vector values, or queries.

## Alternatives And Risks

- A model-backed local embedding library would provide better semantic quality, but adds model weights, platform constraints, and a capability/credential surface before a retrieval evaluation corpus exists. Deterministic feature hashing is a reproducible provider-port baseline; later evaluation can justify a revisioned model adapter.
- pgvector plus PostgreSQL full-text search would be a viable local hybrid backend, but would couple first conformance tests to a running service and make a portable immutable index artifact harder to inspect. The JSON exact scorer is appropriate only for Lite fixtures and local experiments, not a scale-performance claim.
- A mutable index alias would make replacement convenient but risks readers observing changed contents under the same identifier. Explicit immutable result Artifact selection keeps runs reproducible and avoids an unscoped publication workflow.
- Exact vector scan is bounded by the existing Artifact and output limits. Any approximate/index-store optimization later needs a new implementation identity and equivalent query conformance evidence.

## Test Strategy

Add `tests/contract/test_indexing.py` with sanitized ChunkSet fixtures to test canonical payload round trips; identity determinism; record-to-Chunk alignment; dimension/finite/normalization bounds; search-document preservation of table, hierarchy, language, metadata, and citations; and exact safe failure codes.

Add `tests/integration/test_indexing_artifacts.py` to invoke registered plugins through `PluginExecutor` with the existing fake and Docker-backed Artifact services. It will prove atomic index commits, replay identity, changed-input/provider/config divergence, replacement-safe explicit query selection, keyword/vector/hybrid scoring, deterministic tie order, and restart readability of the stored result Artifact.

Add a shared conformance fixture for `EmbeddingPort` and `HybridSearchPort`. Run it against `embedder.hashing@1` / `indexer.local-hybrid@1` and a synthetic replacement adapter registered only in tests. The latter must require no Registry, executor, or generic query-port source change. Resilience tests inject malformed records, unavailable capability, cancellation, a keyed-lock contention outcome, and Artifact store/repository failures; every case asserts no trace-visible successful index and successful recovery after the fault is removed. Run the existing Plugin, Chunking, Trace persistence, Profile, and full regression suites.

## Implementation Checklist

- [x] Add frozen `EmbeddingSet/v1`, `SearchDocumentSet/v1`, `SearchIndexResult/v1`, request/hit, and provider-port contracts plus canonical serializers.
- [x] Add the three Artifact schemas to the supported catalog.
- [x] Implement deterministic 256-dimensional hashing embeddings, strict embedding validation, and citation-preserving search-document projection.
- [x] Implement canonical BM25/exact-cosine local hybrid build/query, semantic index identity, keyed build locking, cancellation checks, and safe metrics.
- [x] Register the three local Plugins through the existing allowlist with closed configuration schemas and named ports.
- [ ] Add contract, provider-conformance, integration, restart, and failure/recovery coverage; run focused and full regressions. Contract, in-memory integration, conformance, lock/cancellation, unavailable-capability, and direct ArtifactService repository-failure/retry coverage are complete. Docker-backed restart/full-regression verification remains pending: Docker Desktop, Compose configuration, and required images were available, but the existing lifecycle `compose up --build --detach --wait` stalled before any container was created.

## Open Questions

None. Model-backed embedding quality, approximate search, pgvector, external providers, and query API exposure are intentionally deferred to later revisioned adapters and retrieval Stories.

## Approval

The S-009 Story Pipeline invocation authorizes this just-in-time technical design. It records the local provider choices without changing the confirmed Story contract.

## Change History

- **2026-09-12:** Created for the S-009 Story Pipeline delivery run.
