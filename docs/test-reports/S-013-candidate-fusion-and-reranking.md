# Test Report

## Story And Designs

- Story: `docs/stories/S-013-candidate-fusion-and-reranking.md`
- Approved design: `docs/designs/stories/S-013-candidate-fusion-and-reranking.md`

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | Fusion/RRF attribution and immutable-parent integration path; ordered repeated-port compilation | Contract/integration | Pass |
| 2 | Fusion mixed-index rejection and source-artifact preservation | Integration/resilience | Pass |
| 3 | Rerank decisions include exact input-candidate inventory and reject a missing exclusion decision; forged rerank ports cannot publish | Contract/integration | Pass after repair |
| 4 | Mixed identity, cancellation, stale/forged/malformed/non-finite Fusion input, cardinality, duplicate source, schema mismatch, forward-source, unavailable, and timeout cases | Contract/integration/resilience | Pass |
| 5 | Fixed ingestion fixture, deterministic Registry path, parent-byte preservation, and non-Docker regression suite | Integration/regression | Pass |

## Tests Added Or Updated

- `tests/integration/test_fusion_plugins.py`: decision completeness, stale/forged/malformed/non-finite Fusion Artifact, forged port, unavailable, and timeout no-publication regressions.
- `tests/contract/test_query_profiles.py`: ordered repeated fusion-port and invalid-binding matrix.

## Commands And Results

| Command | Result |
|---|---|
| `pytest -q tests/integration/test_fusion_plugins.py tests/contract/test_query_profiles.py tests/contract/test_plugins.py tests/contract/test_retrieval.py tests/integration/test_retrieval_plugins.py` | `50 passed` |
| `pytest -q -m 'not integration'` | `251 passed, 3 deselected` |
| `python -m compileall -q src` | Pass |
| `git diff --check` | Pass |
| `docker compose -f deploy/local/compose.yaml -f deploy/local/compose.test.yaml config --quiet` | Pass (only unset optional-secret warnings) |
| `pytest -q` | Docker lifecycle tests ran after the non-Docker portion; process exited with empty `lastfailed`, but the command transport did not return the final summary/count. |

## Visual Evidence

No visual acceptance matrix applies.

## Visual Baseline Changes

None.

## Build Status

Pass.

## Test Status

Focused and non-Docker regression gates pass. Docker-inclusive execution has no observed failed test, but lacks a captured terminal summary.

## Failure Classification

Two implementation defects were found and repaired during verification:

- Rerank contracts allowed an excluded input to have no decision.
- Reranking accepted Fusion content that did not match its manifest digest.

The initial full-suite Compose delay is an environment/lifecycle observation, not an S-013 assertion failure.

## Feedback For Development

None remaining.

## Remaining Gaps

- Re-run `pytest -q` with a terminal capture that retains its final summary if a complete Docker-inclusive result is required as delivery evidence.

## Regression Coverage

S-011 Query Profile compilation and S-012 retrieval candidates are included in the focused matrix and the full non-Docker suite.
