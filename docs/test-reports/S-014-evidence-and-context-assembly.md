# Test Report

## Story And Designs

- Story: `docs/stories/S-014-evidence-and-context-assembly.md`
- Approved design: `docs/designs/stories/S-014-evidence-and-context-assembly.md`

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | Deterministic EvidenceSet bytes, citation key, source element/locator, contributor, index binding, and all three typed retrieval/fusion/rerank adapters | Contract/integration | Pass |
| 2 | Exact budget shortage, fixed hierarchy parent/neighbor expansion, deterministic decision bytes, and de-duplication | Contract | Pass |
| 3 | Table-heavy and hierarchy fixtures retain typed locators, table element IDs, and hierarchy source identity | Contract/integration | Pass |
| 4 | Duplicate citation, invalid config, forged evidence ID, stale index identity, source-incompatible locator, stale Artifact digest, cancellation, unavailable plugin, and no-publication failures | Contract/resilience | Pass after repair |
| 5 | Empty budget result records explicit `budget_exhausted` shortage; no context adapter exposes retrieval inputs or an undeclared retrieval path | Contract/design inspection | Pass |

## Tests Added Or Updated

- `tests/contract/test_evidence.py`: Evidence contract determinism, budgets, hierarchy expansion/de-duplication, table identity, forged Evidence ID rejection, typed plugin paths, and executor failure/no-publication coverage.

## Commands And Results

| Command | Result |
|---|---|
| `pytest -q tests/contract/test_evidence.py` | `7 passed` |
| `pytest -q tests/contract/test_query_profiles.py tests/integration/test_retrieval_plugins.py tests/integration/test_fusion_plugins.py` | `29 passed` |
| `pytest -q tests/contract/test_evidence.py tests/contract/test_query_profiles.py tests/integration/test_retrieval_plugins.py tests/integration/test_fusion_plugins.py` | `35 passed` |
| `pytest -q -m 'not integration'` | `258 passed, 3 deselected` |
| `pytest -q` | Environment-blocked: non-Docker body reached 100% progress, then Docker Compose lifecycle startup/build stalled without a terminal pytest summary. |

## Visual Evidence

No visual acceptance matrix applies.

## Visual Baseline Changes

None.

## Build Status

Pass for the Python build and non-Docker test surface.

## Test Status

Pass, subject to the separately environment-blocked Docker lifecycle regression. This is not waived and does not represent an observed S-014 assertion failure.

## Failure Classification

Two implementation defects were found and repaired during verification:

- `EvidenceItem` accepted a schema-valid but forged `evidence_id`; it now requires the deterministic identity derived from its citation key.
- Context plugin validation errors lacked corresponding `TraceErrorCode` entries, causing failure recording itself to raise `ValueError`; context input/candidate error codes are now traceable safe failures.

The Docker lifecycle stall is classified as an environment failure: Compose image build/start did not complete under the existing lifecycle test timeout/command transport. It remains a required follow-up regression, not a passing result.

## Feedback For Development

None remaining for the tested non-Docker surface.

## Remaining Gaps

- Re-run `pytest -q` in a Docker environment that can complete Compose build/start and retain its terminal summary. The three deselected tests are Docker lifecycle integration tests.

## Regression Coverage

Focused coverage includes S-011 Query Profile compilation, S-012 retrieval, and S-013 fusion/reranking boundaries. The non-Docker regression suite covers the complete currently executable project surface.
