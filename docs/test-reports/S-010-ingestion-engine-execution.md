# Test Report

## Story And Designs

- Story: `S-010 - Ingestion Engine Execution And Validation`
- Design: `docs/designs/stories/S-010-ingestion-engine-execution.md`
- Shared rule: `FD-012 - Bounded Ordered Sub-Stages Within Component Axes`
- Test status: passed after the implementation repair rounds.

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | Explicit parser/normalizer sub-stage execution, pinned resolver evidence, ordered stage inputs, source schema rejection, and compiler chain validation | Contract/integration | Passed |
| 2 | Conditional skip, quality rejection and declared fallback, cancellation, exact invalid Plugin output failure, and stable candidate attempt keys | Contract | Passed |
| 3 | One retry of the same candidate after a retryable persisted failure, implementation-drift failure, distinct plan digest and Run after configuration change | Contract | Passed |
| 4 | Native, scanned, and table document-class resolution against shared registered components and distinct Profiles | End-to-end | Passed |
| 5 | Synthetic strategy registered as a Plugin and selected entirely through Profile data | End-to-end | Passed |
| 6 | Docker restart/readback of ordered stage inputs, resolver evidence, outputs, metrics, signals, timings, retry error, and terminal state | Integration | Passed |

## Tests Added Or Updated

- `tests/contract/test_ingestion_engine.py`: conditional skip, cancellation, retry, configuration-change/new-Run, fallback, drift, and complete sub-stage execution evidence.
- `tests/contract/test_trace_contracts.py`: persist a validated ingestion resolver evidence record with its SHA-256 plan digest; reject a sensitive resolver observable before a database write.
- `tests/contract/test_plugins.py`: record a retryable unavailable Plugin attempt before returning the Plugin error.
- `tests/contract/test_ingestion_profiles.py`: reject duplicate sub-stage IDs in one fixed component axis.
- `tests/integration/test_trace_persistence.py`: persist and restart-read ordered stage inputs and ingestion resolver evidence in the Docker-backed trace lifecycle scenario.

## Commands And Results

| Command | Result |
|---|---|
| `python -m compileall -q src` | Passed |
| `git diff --check` | Passed |
| `pytest -q tests/contract/test_ingestion_engine.py tests/contract/test_trace_contracts.py tests/integration/test_ingestion_engine_e2e.py` | `23 passed` |
| `pytest -q tests/contract/test_ingestion_profiles.py tests/unit/test_profile_resolver.py tests/contract/test_ingestion_engine.py tests/integration/test_ingestion_engine_e2e.py tests/contract/test_plugins.py tests/contract/test_trace_contracts.py tests/integration/test_trace_persistence.py` | Passed after the repair; Docker-backed trace scenario completed with no `lastfailed` entries. The initial focused execution before the final two contract additions reported `51 passed`; those additions passed in the 23-test rerun above. |
| `pytest -q tests/integration/test_trace_persistence.py` | Passed after repair; Docker lifecycle completed and no failures were recorded in `.pytest_cache/v/cache/lastfailed`. |
| `pytest -q -m 'not integration'` | `208 passed, 3 deselected` |
| `pytest -q` | Passed after repair with `209` collected tests at that point; the final two subsequent contract additions are included in the focused and non-Docker broad commands above. Final collection: `211 tests collected`. |

## Visual Evidence

| AC | UI Anchor | Capture Conditions | Baseline | Diff Or Review Evidence | Result |
|---|---|---|---|---|---|
| N/A | N/A | Engine/runtime Story; no adopted UI acceptance row | None | N/A | N/A |

## Visual Baseline Changes

None.

## Build Status

Passed. Python source compilation and whitespace/error checks passed.

## Test Status

Passed. Focused S-010 acceptance coverage, Docker restart persistence coverage, and the broad non-Docker regression suite are green.

## Failure Classification

One repaired implementation defect was found. `TraceRepository.record_ingestion_evidence` passed the required 64-character `plan_digest` through the generic sensitive-text detector, which classified every valid digest as unsafe and raised `PLAN_SNAPSHOT_INVALID`. The repair exempts only the validated digest while continuing to scan all resolver-provided evidence. The positive persistence and negative sensitive-observable tests both pass.

## Repair Round Two

Four review gaps were independently rechecked after the second repair:

| Former Gap | Executable Evidence | Result |
|---|---|---|
| Unavailable Plugin attempt was not persisted | `test_unavailable_and_oversized_plugin_fail_without_output_commit` verifies the executor starts and records one retryable `PLUGIN_UNAVAILABLE` failure without an output commit. | Passed |
| Duplicate ordered input IDs could not restart-read | Docker `test_trace_migration_lifecycle_lineage_and_restart` binds the same parent Artifact twice, then asserts the restarted trace returns `[parent_id, parent_id]` in ordinal order. | Passed |
| Duplicate sub-stage IDs were accepted | `test_profile_rejects_duplicate_sub_stage_ids_within_one_axis` requires parser rejection. | Passed |
| Published output manifest mismatch remained succeeded before fallback | `test_engine_invalidates_manifest_mismatch_before_declared_fallback` requires the first candidate to be `FAILED` with `STAGE_OUTPUT_INVALID` and the declared fallback to run. `test_repository_persists_failed_invalidation_of_a_published_output_attempt` verifies the persisted state/result update. | Passed |

| Command | Result |
|---|---|
| `pytest -q tests/contract/test_ingestion_profiles.py tests/unit/test_profile_resolver.py tests/contract/test_plugins.py tests/contract/test_ingestion_engine.py tests/contract/test_trace_contracts.py tests/integration/test_ingestion_engine_e2e.py` | `56 passed` |
| `pytest -q tests/integration/test_trace_persistence.py` | Passed; Docker restart scenario completed and `.pytest_cache/v/cache/lastfailed` remained empty. |
| `pytest -q -m 'not integration'` | `211 passed, 3 deselected` |
| `pytest -q` | Passed; Docker-inclusive lifecycle, trace restart, and structure persistence tests completed with no `lastfailed` entries. Final collection: `214 tests collected`. |

## Feedback For Development

No remaining action required for S-010 test acceptance. Keep the resolver-evidence tests: the digest exception is deliberately narrow and must not become a general metadata bypass.

## Remaining Gaps

None for the Story acceptance contract. The Docker-backed restart test completed in this environment.

## Regression Coverage

Profile compilation/resolution, Plugin runners, trace contracts, Engine execution, document-class end-to-end paths, and the full non-Docker regression surface passed. The final Docker-inclusive suite also completed after the repair rounds.
