# Story Design: S-013 - Candidate Fusion And Reranking

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-013-candidate-fusion-and-reranking.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; pipeline delivery
  started 2026-09-12.
- **Material Decisions Requiring Approval:** None. The Story Pipeline
  invocation authorizes the bounded fusion, reranker, and repeated-port choices
  recorded below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add immutable `FusionCandidateSet/v1` whose candidates retain every contributing `RetrievalCandidate` unchanged, its contributor ID, original rank, safe score, and score kind. A registered `fusion.reciprocal-rank@1` consumes one to eight named candidate-set inputs and applies deterministic reciprocal-rank fusion (RRF). | Contract fixture with keyword/vector lists asserts canonical bytes, contributor order, original rank retention, source/index identity, normalized fused score, method identity, and chunk-ID tie order. |
| 2 | Deduplicate only on the common `(document_id, chunk_id)` evidence identity after proving every input binds the same indexed Artifact and document. Preserve each source candidate as a separate contribution, including its element/locator pairs and structural projection. | Overlapping candidates with distinct locators and structural fields assert one fused candidate containing all contributions; incompatible index, document, malformed, duplicate-input, and conflicting candidate identity cases fail without an output Artifact. |
| 3 | Add immutable `RerankedCandidateSet/v1` and `reranker.lexical-overlap@1`. It receives the question, a fused set, and its exact Search Index, scores only fused candidates with deterministic bounded lexical overlap, and records a decision for every input candidate. | Golden rerank fixture asserts input/output ranks, `[0,1]` finite scores, implementation/configuration identity, included and limit-excluded reasons, stable ties, and immutable fused input bytes. |
| 4 | Validate port cardinality, Artifact schemas/digests, candidate-set identities, finite scores, cancellation, and deadline before output creation. Empty valid fusion succeeds with an empty set; incompatible inputs, invalid scores, timeout, cancellation, or Plugin failure fail the stage with no eligible result. | Parameterized direct-port and PluginExecutor resilience matrix covers zero/too-many inputs, empty inputs, stale/mixed index bindings, invalid payloads, unavailable Plugin, timeout, cancellation, and a forged port result; it asserts one safe failure and no commit. |
| 5 | Use fixed synthetic retrieval/fusion/rerank fixtures and canonical serializers. Fusion and rerank read parsed copies only and create new Artifacts; they do not modify source candidate Artifact bytes or manifests. | Contract snapshots run the same candidates through retrieval, fusion, and rerank twice; integration invokes Registry Plugins and compares parent Artifact bytes/digests before and after, plus a compatible synthetic reranker conformance case. |

## Current Code Findings

S-012 provides immutable `RetrievalCandidateSet/v1` payloads with one indexed
Artifact binding, document identity, retriever/contributor identities, ordered
candidate ranks, finite bounded scores, citation-ready locators, and closed
structural projections. Candidate IDs intentionally include the contributor,
so they cannot be used as cross-retriever deduplication keys. Their shared
document/chunk identity is the safe fusion key. The retrieval Plugin already
proves its index content digest before publication and preserves upstream
Artifact immutability.

The Registry/Executor supports typed, allowlisted Plugins, atomic outputs,
deadline/cancellation handling, and safe failed-attempt traces. It currently
requires exactly one artifact for every declared input port, while the Query
Profile compiler accepts one source string per named port. A fusion stage must
consume a declared bounded number of same-schema candidate-set inputs, so the
generic named-port contract needs bounded repeated-input support; encoding a
candidate list in an opaque wrapper would lose typed plan validation and create
an unowned bundling stage.

S-011 already defines ordered `retrieve[1..8] -> fuse? -> rerank?` slots and
the `text-hybrid` fixture has separate keyword/vector outputs. There is no
Query Engine yet; S-015 owns plan execution and must consume this Story's
concrete port contracts rather than adding an alternate fusion path.

## Proposed Approach

### Contracts And Artifact Boundaries

Add sibling `kb2_runtime.fusion` and `kb2_runtime.reranking` packages with
frozen Pydantic contracts, canonical ASCII JSON serializers, pure local ports,
and Registry Plugin adapters:

```text
fusion/
  contracts.py     # FusionConfig, contribution and fused-candidate contracts
  local.py         # pure reciprocal-rank fusion
  plugin.py        # repeated RetrievalCandidateSet Artifact adapter
  serializer.py
reranking/
  contracts.py     # RerankerConfig, decision and reranked-candidate contracts
  local.py         # pure lexical-overlap reranker port
  plugin.py        # question + fusion + Search Index adapter
  serializer.py
```

`FusionCandidateSet/v1` is an additive `fusion.candidate.set/v1` Artifact. It
pins one common `IndexArtifactBinding`, index ID, document ID, fusion Plugin
and implementation identities, configuration digest, ordered contributor-set
identities, method label, and at most 100 fused candidates. A fused candidate
uses `(document_id, chunk_id)` as its semantic identity, has an output rank and
finite `safe_score` in `[0,1]`, and contains one to eight complete original
`RetrievalCandidate` contributions in declared contributor-set order. It has
no excerpt, query text, vector, raw provider payload, or mutable handle.

`RerankedCandidateSet/v1` is an additive `rerank.candidate.set/v1` Artifact.
It pins the exact fusion Artifact binding and the same Search Index binding,
the reranker Plugin/implementation/configuration identities, and the selected
ordered fused candidates. Its `decisions` cover every fused input candidate:
input rank, optional output rank, finite `[0,1]` rerank score, and the closed
reason enum `included` or `limit_excluded`. Selected candidates retain their
full fusion contributions, so S-014 can trace evidence through both stages.
The selection and decision lists are both capped at 100 and validate one
decision per input identity, contiguous ranks, and exact included/excluded
correspondence.

Semantic IDs are SHA-256 truncations over canonical headers and ordered
evidence/decisions, following S-012 serializers. The Plugin adapters recompute
them before publishing to reject forged port results. A later reranker may
implement the same typed port only under a new allowlisted implementation
identity and must pass the shared contract suite.

### Bounded Repeated Candidate Port

Extend the generic `PluginPort` contract with bounded `min_items` and
`max_items`, defaulting to one. Keep port schemas and names singular; a
repeated port consumes an ordered tuple of inputs of that same pair. Update
`PluginDescriptor` validation, `PluginExecutor` input-schema matching, and
the Query Profile source/compiler representation so a named input maps to one
source string or an ordered source list when the port is repeated. The compiler
requires exactly the declared port names, validates list cardinality and every
source schema, serializes each resolved source in order, and still rejects
forward/self edges.

Only `fusion.reciprocal-rank@1` uses this new capability in this Story:

```text
candidate_sets: retrieval.candidate.set/v1 [1..8]
  -> fused_candidates: fusion.candidate.set/v1
```

The fusion Plugin reads inputs in resolved Profile order, rejects repeated
Artifact IDs and sets with different index binding, index ID, document ID, or
invalid canonical identity. An empty valid contributor set is allowed; one or
more valid input Artifacts are still required. `text-hybrid` is updated to
bind `keyword.candidates` then `vector.candidates` to the repeated port. The
other baseline Profiles may omit fusion. This is an additive general port
capability, not an arbitrary DAG or an untyped input envelope.

### Deterministic Fusion And Reranking

`FusionConfig` is closed declarative data: `limit` in `1..100` and
`rank_constant` in `1..1000` (default `60`). For each candidate contribution,
RRF adds `1 / (rank_constant + original_rank)`. Scores are normalized by the
largest fused score in this invocation solely to fit the existing safe-score
range; no cross-run or cross-method comparability is claimed. Candidates sort
by normalized score descending, then stable chunk ID ascending. The output
method label is `reciprocal_rank_fusion`; no upstream list, candidate, score,
or rank is modified.

Register the selected optional adapter as:

```text
reranker.lexical-overlap@1
  question: opaque.bytes/v1
  fused_candidates: fusion.candidate.set/v1
  index: search.index.result/v1
  -> reranked_candidates: rerank.candidate.set/v1
```

`RerankerConfig` has only `limit` in `1..100`. The adapter validates UTF-8
question bounds and proves the supplied Index Artifact bytes/digest and parsed
index agree with the fused set binding. The pure local reranker calculates
case-normalized token overlap between the question and the indexed chunk's
bounded keyword text for each fused candidate, then normalizes scores to
`[0,1]`. Ties break by fused input rank, then chunk ID. It selects the first
`limit`; all remaining candidates receive `limit_excluded`. This is a
provider-neutral baseline, not a hidden second retrieval pass, document
specific ranking rule, model call, or global score metric.

Both adapters check cancellation before and during bounded loops and rely on
the existing executor publication check. They map malformed JSON, invalid
identity, unsafe/non-finite value, and invalid result contracts to new
stage-specific safe Plugin error codes; timeout/cancellation/unavailability
reuse the existing generic terminal outcomes. Empty valid fusion/rerank input
produces a valid empty output with explicit bounded metrics/signals. Any
failure publishes no Artifact.

### Trace, Compatibility, And Security

Register in-process descriptors with 10-second deadlines and bounded output
hints. Fusion emits `fusion_input_sets`, `fusion_input_candidates`,
`fusion_deduplicated`, and `fusion_duration_ms`, with `fusion_validation` and
`no_candidates` signals. Reranking emits `rerank_input_candidates`,
`rerank_included`, `rerank_excluded`, and `rerank_duration_ms`, with
`rerank_validation` and `no_candidates` signals. They retain only identities,
counts, timing, method labels, ranks, bounded scores, and declared decision
reasons. Question text, token lists, raw score distributions, Search Index
content, vectors, and provider payloads are excluded from output Artifacts and
trace summaries.

This is additive to the Artifact catalog and preserves S-012 payload bytes and
the existing fixed-slot Query Profile model. No API route, database migration,
network call, credential, dynamic command/path, external reranker, or UI work
is introduced. S-014 owns EvidenceSet/excerpt/citation-key creation; S-015
owns actual resolved-plan execution.

## Alternatives And Risks

- Averaging retrieval scores would imply comparability between independently
  normalized strategy scores. RRF uses only retained ranks and makes fusion
  deterministic without that unsupported assumption.
- Collapsing a duplicate to one source candidate would discard table or
  hierarchy locator/context details. Keeping complete ordered contributions
  preserves attribution at a bounded cost of at most 800 contributions.
- A fixed two-input fusion Plugin would prevent a one-contributor Profile and
  conflict with up to eight declared retrieval stages. Bounded repeated ports
  preserve static schemas, plan validation, and future reusable fan-in.
- An external or model reranker would add capability/credential behavior and
  opaque scoring before a provider contract exists. The deterministic local
  adapter proves the substitution boundary while keeping this delivery local.

## Test Strategy

Add `tests/contract/test_fusion.py` for frozen schema rejection, canonical
identity, RRF golden ordering, contributor/rank/locator/structural retention,
deduplication, empty valid inputs, score normalization, and forged identity
rejection. Add `tests/contract/test_reranking.py` for lexical golden rankings,
decision completeness, included/excluded rationale, score/rank bounds,
ties, and no mutation of parsed Fusion or Retrieval values.

Add `tests/integration/test_fusion_plugins.py` to invoke actual Registry
descriptors through `PluginExecutor` with one and multiple candidate Artifacts,
then invoke the reranker with the question and exact Search Index. Cover no
commit plus a single safe failure for mixed/stale identities, malformed or
non-finite content, deadline timeout, cancellation, unavailable descriptors,
and intentionally forged fusion/reranker ports. Assert parent bytes/digests
are unchanged. Extend Query Profile contract tests for repeated named-port
cardinality, ordered schema-valid sources, type mismatch, duplicate/forward
source rejection, and the updated `text-hybrid` fusion binding. Run focused
tests and the full Python suite, including S-011/S-012 regressions.

## Implementation Checklist

- [ ] Add bounded repeated named-input support to Plugin descriptors/executor
  and Query Profile compilation, with compatibility defaults of exactly one.
- [ ] Add frozen fusion/rerank contracts, serializers, semantic validation,
  local RRF/lexical-overlap ports, safe errors, and Plugin adapters.
- [ ] Register the two allowlisted in-process Plugins and update only the
  affected baseline Query Profile fixture(s).
- [ ] Add contract, integration, failure, immutability, and extension-path
  tests; run focused and full regression suites.

## Open Questions

None. The selected deterministic local reranker is sufficient for the
confirmed optional-stage contract; provider/model adapters remain future
allowlisted substitutions.

## Approval

The S-013 Story Pipeline invocation authorizes this just-in-time technical
design. It records implementation choices without changing the confirmed Story
contract.

## Change History

- **2026-09-12:** Created for the S-013 Story Pipeline delivery run.
