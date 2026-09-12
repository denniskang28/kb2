# Test Report

## Story And Designs

- Story: `S-024 Document, Ingestion Run, And Artifact UI`.
- Approved design: `docs/designs/stories/S-024-document-ingestion-and-artifact-ui.md`.
- Verification date: 2026-09-13.

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | `test_preflight_returns_detector_facts_automatic_resolution_stages_and_local_disclosure`; `test_preflight_is_bounded_and_requires_a_saved_ingestion_profile` | Contract | Passed, but narrow local-only coverage |
| 2 | Preflight local disclosure assertion | Contract | Partial; no external-stage fixture or acknowledgement flow coverage |
| 3 | No S-024 Run projection test | Contract/API/UI | Missing |
| 4 | No S-024 action eligibility, stop ownership, immutable rerun, or no-manual-retry test | Contract/API/UI | Missing |
| 5 | `test_artifact_view_preserves_canonical_table_identity_and_locator`; `test_artifact_view_preserves_chunk_citation_locator` | Contract | Passed after repair; client source synchronization remains failed |
| 6 | No S-024 browser fixture or visual tests | Browser/visual | Missing; local Chrome runtime is unavailable |

## Tests Added Or Updated

- Added schema-realistic Canonical table/locator and Chunk citation/locator
  projection tests to `tests/contract/test_workbench_documents.py`.
- Tests reuse the established CanonicalDocument fixture and documented ChunkSet
  field names. They are valid contract tests and were not weakened.

## Commands And Results

| Command | Result |
|---|---|
| `node --check src/kb2_runtime/workbench/static/workbench.js` | Passed |
| `git diff --check` | Passed |
| `pytest -q tests/contract/test_workbench_documents.py tests/contract/test_workbench.py tests/contract/test_workbench_browser.py` before added tests | 7 passed, 5 skipped |
| `pytest -q tests/contract/test_ingestion_engine.py tests/integration/test_ingestion_engine_e2e.py tests/contract/test_trace_contracts.py tests/contract/test_workbench_studio.py` | 32 passed |
| `pytest -q tests/contract/test_workbench_documents.py` after repair | 5 passed |
| Focused S-024/workbench/engine/trace regression retest | 42 passed, 5 skipped |

## Visual Evidence

| AC | UI Anchor | Capture Conditions | Baseline | Diff Or Review Evidence | Result |
|---|---|---|---|---|---|
| 1-2, 6 | UI-003 | 1440x900 and 644x900 required | None | No S-024 browser fixture/endpoints; Chrome executable unavailable | Blocked/missing |
| 3-4, 6 | UI-004 | Running, failed, fallback, retry | None | Runs client only renders a JSON preformatted block; no fixture/test | Missing |
| 5-6 | UI-005 | Canonical, table, Chunk, lineage source sync | None | Artifact endpoint and tabs now exist, but a locator click only reselects the same list control; no distinct source pane or reverse synchronization exists | Failed |
| 6 | UI-013 | Desktop/narrow exception states | None | No S-024 screenshots or overflow/overlap assertions | Missing |

## Visual Baseline Changes

None.

## Build Status

Static JavaScript syntax and diff whitespace checks pass.

## Test Status

Not ready for delivery: server Artifact schema projection is repaired, but the
required source synchronization and narrow drawer close behavior are still
incorrect, and S-024 browser/visual coverage is absent.

## Failure Classification

- **Repaired implementation:** `DocumentWorkbenchService._artifact_view` now
  correctly projects Canonical table identity/locators and Chunk IDs/citations;
  the prior focused contract failures pass.
- **Implementation:** the workbench client has Artifact endpoint usage and
  conditional tabs, but it has no distinct source surface to synchronize with.
  The sole locator-bearing control is the clicked list item itself, so it
  cannot provide bidirectional Canonical/table/Chunk source selection.
- **Implementation:** pressing Escape on the narrow Artifact drawer removes
  only its `open` class. The base `.artifact-inspector` remains fixed and
  visible, so the dialog does not close; the close button and Escape have
  divergent behavior.
- **Missing tests:** no current coverage for Run state projections/recovery
  capabilities, disclosure acknowledgement, or S-024 browser states.
- **Environment:** visual capture cannot run locally because the fixture suite
  is gated on `/Applications/Google Chrome.app/...`, which is absent.

## Feedback For Development

1. Implement a source surface and explicit shared selection state so artifact
   rows and source locators select each other by the returned stable IDs.
2. Make Escape invoke the same close/remove path as the close button, restore
   the originating action's focus, and verify it in a narrow browser test.
3. Add Run/recovery/disclosure API tests and S-024 fixture-backed browser tests
   before requesting final regression.

## Remaining Gaps

Full S-024 visual matrix, external disclosure selection, upload confirmation,
running/failed/fallback/retry state rendering, bidirectional Artifact source
inspection, and narrow Escape behavior remain unverified or unimplemented.

## Regression Coverage

Existing ingestion engine, trace, Studio, and current workbench contract tests
pass in non-Docker scope. Docker lifecycle coverage was not attempted because
the repository documents the existing Compose startup limitation.

## Repair Retest

The previously failing Artifact projection tests now pass: real
`CanonicalDocument/v1` tables/locators and real `ChunkSet/v1` IDs/citation
locators are correctly preserved by the service. The focused non-Docker
regression command completed with `42 passed, 5 skipped`; the skips are the
pre-existing Chrome-gated browser suite and do not cover S-024 states.

## Repair Retest Round 2

The client now renders separate stable-object and source-locator panes. Its
shared `data-stable-id` selection marks the matching entries in both panes, and
the narrow Escape path now removes the inspector and restores the invoking
control in code. These changes pass the pre-existing non-browser regression
scope (`42 passed, 5 skipped`) and static/build checks.

The revised focused UI contract test is nevertheless failing (`4 passed, 1
failed`): Chunk rendering still derives the sole displayed locator from
`row.citations?.[0]?.locator`. The service projects every Chunk citation, but
the client cannot show or synchronize any locator after the first. This is an
implementation failure against the design's exact Chunk citations/locators
requirement, not a browser-environment limitation.

The remaining visual matrix is genuinely environment-blocked: no S-024 browser
fixture has been added and the local Chrome executable required by the existing
browser harness is unavailable. No screenshots, overflow checks, or live
keyboard interaction recording can therefore be claimed.

## Repair Retest Round 3

The multiple-citation regression now passes. The Artifact inspector expands a
Chunk into one stable object/source binding per returned citation locator;
therefore no projected citation is silently hidden by a first-item shortcut.

Chrome became available during this round, so the prior environment statement
no longer applies. Added and executed a fixture-backed browser test at 1440x900
and 644x900. It captures each Artifact state and verifies:

- source-pane selection and object-pane selection each mark the matching pair
  by stable key;
- the inspector is semantic in the narrow viewport, has no horizontal page
  overflow, and is captured by the browser test;
- Escape removes the inspector and restores focus to its Artifact action.

`test_fixture_backed_ingestion_artifact_inspector_sync_and_escape` passes for
both viewports (`2 passed`). The non-browser focused regression suite passes
with `42 passed`; source and test compilation, JavaScript syntax, and diff
whitespace checks also pass.

All discovered implementation defects for the Story's Artifact/source-sync and
narrow-drawer paths are repaired. The full S-024 visual acceptance matrix is
still incomplete, but **not environment-blocked**: it lacks deterministic
browser fixtures/screenshots for upload/automatic selection, running, failed,
skipped, fallback, and retry states. Existing browser fixture coverage does not
exercise those S-024 states. This is a remaining test-evidence gap, not an
observed implementation failure.

## Final Visual Retest

Visual fixtures now cover the previously missing AC6 state matrix at both
1440x900 and 644x900. They are genuine test-only API state: the preflight
handler asserts the submitted Profile, filename, and raw PDF bytes; the Run
handler supplies a running Run with failed, accepted fallback/retry, skipped,
and running stage attempts. The browser test then captures preflight and run
matrix screenshots and asserts no horizontal page overflow. Artifact
inspection continues to exercise source/object synchronization, narrow dialog
semantics, Escape closure, and focus return.

Commands/results:

| Command | Result |
|---|---|
| `KB2_BROWSER_TESTS=1 pytest -q tests/contract/test_workbench_browser.py::test_fixture_backed_document_preflight_and_ingestion_state_matrix tests/contract/test_workbench_browser.py::test_fixture_backed_ingestion_artifact_inspector_sync_and_escape` | `4 passed` |
| Focused non-browser workbench/engine/trace suite | `42 passed` |
| `python -m compileall -q src tests`; `node --check ...`; `git diff --check` | Passed |

The visual matrix is no longer environment-blocked. It has executable
screenshot/interaction evidence for the required named states.

Acceptance remains **not ready** because AC3 is an implementation failure:
the current Run client renders stage key, attempt, state, selection, safe
failure, and output actions, but omits the required Plugin, inputs, outputs'
details, timing, metrics, and quality data from the Run projection. The server
projection may contain those fields, but the Story requires that the Run detail
render them. This conclusion is from direct client-code inspection, not an
absence of a visual fixture.

## AC3 Repair Retest

AC3's previously missing fields are now rendered in each Run stage as a safe
bounded detail projection containing `pluginId`, inputs, start/end timestamps,
metrics, and quality signals. The browser fixture supplies all of those values
for the accepted fallback attempt and asserts their visible rendering at both
required viewport widths.

| AC | Executable evidence | Result |
|---|---|---|
| 1 | Preflight API request/body fixture plus automatic-selection browser flow at 1440x900 and 644x900 | Pass |
| 2 | Local-only disclosure is covered; no external selected-stage and acknowledgement fixture exists | Evidence gap |
| 3 | API-backed running/failure/fallback/skip projection browser assertion includes Plugin, input, timestamps, metric, quality, output action, and safe failure | Pass |
| 4 | Existing code review shows action projection, but no focused action-eligibility/immutable-rerun browser or service test exists | Evidence gap |
| 5 | Canonical/table and multi-citation Chunk service contracts plus bidirectional Artifact source browser interaction | Pass |
| 6 | API-backed screenshots/interactions at 1440x900 and 644x900 for preflight/automatic, running/failed/skipped/fallback/retry, and Artifact source inspection | Pass |

Commands/results:

| Command | Result |
|---|---|
| `KB2_BROWSER_TESTS=1 pytest -q tests/contract/test_workbench_browser.py::test_fixture_backed_document_preflight_and_ingestion_state_matrix tests/contract/test_workbench_browser.py::test_fixture_backed_ingestion_artifact_inspector_sync_and_escape` | `4 passed` |
| `pytest -q tests/contract/test_workbench_documents.py tests/contract/test_workbench.py tests/contract/test_workbench_studio.py tests/contract/test_ingestion_engine.py tests/integration/test_ingestion_engine_e2e.py tests/contract/test_trace_contracts.py` | `42 passed` |
| `python -m compileall -q src tests`; `node --check src/kb2_runtime/workbench/static/workbench.js`; `git diff --check` | Passed |

AC3 is repaired. The story is still not acceptance-ready under the test
contract because AC2 external-disclosure acknowledgement and AC4 action
eligibility/immutable-plan behavior lack direct executable evidence. These are
test-evidence gaps, not observed implementation failures.

## Final Acceptance Retest

The remaining AC2 and AC4 evidence has been added and independently rerun.

| AC | Final evidence | Result |
|---|---|---|
| 1 | Raw-body preflight contract plus fixture-backed automatic-selection upload flow at 1440x900 and 644x900 | Pass |
| 2 | External-capability contract fixture requires acknowledgement, preserves its token after rejection, and browser interaction shows disclosure, blocked submit, acknowledgement, then enabled submission | Pass |
| 3 | Run projection browser fixture renders stage state/attempt/Plugin/input/output action/timing/metric/quality/safe failure | Pass |
| 4 | Server action-capability projection, browser visibility assertion for Stop/Rerun/Artifact with no retry command, static absence of a retry endpoint, and rerun-to-preflight client path; engine regression covers immutable resolved plans | Pass |
| 5 | Canonical/table and multi-citation Chunk contracts plus bidirectional Artifact/source browser interaction | Pass |
| 6 | API-backed screenshots and no-overflow assertions at 1440x900 and 644x900 for preflight/automatic, external disclosure, running, failed, skipped, fallback/retry, and Artifact source inspection | Pass |

Commands/results:

| Command | Result |
|---|---|
| `pytest -q tests/contract/test_workbench_documents.py tests/contract/test_workbench.py tests/contract/test_workbench_studio.py tests/contract/test_ingestion_engine.py tests/integration/test_ingestion_engine_e2e.py tests/contract/test_trace_contracts.py` | `43 passed` |
| `KB2_BROWSER_TESTS=1 pytest -q tests/contract/test_workbench_browser.py::test_fixture_backed_document_preflight_and_ingestion_state_matrix tests/contract/test_workbench_browser.py::test_fixture_backed_ingestion_artifact_inspector_sync_and_escape` | `4 passed` |
| `pytest -q tests/contract/test_workbench_documents.py` after token-preservation assertion | `6 passed` |
| `python -m compileall -q src tests`; `node --check src/kb2_runtime/workbench/static/workbench.js`; `git diff --check` | Passed |

**Acceptance-ready.** All S-024 acceptance criteria have executable evidence.
The visual matrix is available and executed under Chrome; no visual evidence is
environment-blocked.

## Review Repair Retest

The review-repair contract suite passes (`45 passed`), including workspace
Profile-set retention for an automatically selected inner Profile, server-owned
non-prefix external-capability disclosure, acknowledgement token preservation,
and planned Plugin lookup. Static/build checks also pass.

The target Chrome suite is **failing** (`2 failed, 2 passed`). The current Run
row renderer no longer renders `stage.selection` (or `stage.result`), even
though the Run fixture safely supplies `accepted` and `rejected` candidate
selection signals for fallback/skip diagnosis. Both desktop and narrow
state-matrix tests therefore fail waiting for these required diagnostic states.
This is an implementation regression against AC3/AC6, not an environment or
fixture issue; a clean rerun after checking the test port produced the same
result.

Current status is **not acceptance-ready** pending restoration of the selected,
fallback, and rejected stage-state rendering and a passing Chrome retest.

## Selection and Result UI Repair Retest

The Run-row projection again renders the safe `selection`/`result` diagnostic
alongside its bounded Plugin, input, timing, metric, and quality projection.
The fixture-backed Chrome matrix asserts `accepted`, `rejected`, and the
`parser.fixture@1`, `structure.fixture@1`, and `chunker.fixture@1` identities
at both required viewport widths.

| AC | Final evidence | Result |
|---|---|---|
| 1 | Contract preflight coverage and fixture-backed explicit/automatic Profile selection at 1440x900 and 644x900 | Pass |
| 2 | Server-owned external-capability disclosure, acknowledgement gating, and safe token preservation contracts; browser disclosure flow | Pass |
| 3 | Fixture-backed Run detail renders state, attempt, accepted/rejected diagnostics, Plugin identities, inputs, outputs, timing, metrics, quality, and safe failure at both widths | Pass |
| 4 | Contract action-capability coverage, no retry command, rerun-to-fresh-preflight behavior, and immutable-plan regression coverage | Pass |
| 5 | Canonical/table and multi-citation Chunk contracts plus bidirectional Artifact/source browser interaction and Escape focus restoration | Pass |
| 6 | Chrome fixture state matrix at 1440x900 and 644x900 covers explicit/automatic selection, external disclosure, running/failed/skipped/fallback/retry states, and Artifact inspection without overflow | Pass |

Commands/results:

| Command | Result |
|---|---|
| `pytest -q tests/contract/test_workbench_documents.py tests/contract/test_workbench.py tests/contract/test_workbench_studio.py tests/contract/test_ingestion_engine.py tests/integration/test_ingestion_engine_e2e.py tests/contract/test_trace_contracts.py` | `45 passed in 1.36s` |
| `KB2_BROWSER_TESTS=1 pytest -q tests/contract/test_workbench_browser.py::test_fixture_backed_document_preflight_and_ingestion_state_matrix tests/contract/test_workbench_browser.py::test_fixture_backed_ingestion_artifact_inspector_sync_and_escape` | `4 passed in 8.04s` |
| `python -m compileall -q src tests`; `node --check src/kb2_runtime/workbench/static/workbench.js`; `git diff --check` | Passed |

**Acceptance-ready.** All S-024 acceptance criteria have direct executable
evidence. The required Chrome visual matrix ran at both viewport widths; no
visual coverage remains environment-blocked.

## Rerun Handoff Final Retest

The Rerun browser contract now explicitly verifies the complete handoff rather
than navigation alone. At 1440x900 and 644x900 it triggers the conditional
Rerun action, reaches Documents, restores the selected Ingestion Profile,
shows the immutable source Artifact ID, exposes the fresh preflight token, and
offers the normal confirmable `创建新 Run` action. Both viewports remain free of
horizontal overflow. This establishes that rerun creates a new confirmable
preflight rather than mutating or replaying the source Run.

| AC | Rerun-relevant evidence | Result |
|---|---|---|
| 1 | Fresh Documents preflight restores automatic selected Profile after Rerun | Pass |
| 3 | Rerun begins from the conditional Run-detail action; source Run remains a rendered projection | Pass |
| 4 | Browser handoff verifies fresh preflight and normal confirmation action; existing service regression covers immutable source-plan behavior | Pass |
| 5 | Source Artifact provenance is visible in the resulting Documents preflight | Pass |
| 6 | Chrome verifies the full rerun handoff and no overflow at 1440x900 and 644x900 | Pass |

Commands/results:

| Command | Result |
|---|---|
| `KB2_BROWSER_TESTS=1 pytest -q tests/contract/test_workbench_browser.py::test_fixture_backed_ingestion_artifact_inspector_sync_and_escape tests/contract/test_workbench_browser.py::test_fixture_backed_document_preflight_and_ingestion_state_matrix` | `4 passed in 6.91s` |
| `pytest -q tests/contract/test_workbench_documents.py tests/contract/test_workbench.py tests/contract/test_workbench_studio.py tests/contract/test_ingestion_engine.py tests/integration/test_ingestion_engine_e2e.py tests/contract/test_trace_contracts.py` | `45 passed in 0.91s` |

**Acceptance-ready.** The final rerun handoff evidence closes the remaining
UI transition risk; all S-024 acceptance criteria retain passing executable
coverage.

## Explicit Profile Selector Final Retest

The Documents browser contract now exercises the Profile selector as a real
submission flow. A `fixture-ingestion` Profile-set automatically selects its
non-default `fixture-ingestion` candidate while retaining `fixture-default` as
an option. The operator selects `fixture-default`; the fixture accepts only
that submitted selection, proving the override reaches the confirmation API.
A subsequent preflight still sends and renders `fixture-ingestion` as the
outer Profile-set and automatically resolves it again, so an inner override
does not replace the saved Profile-set context. The Rerun fixture now mirrors
the production preflight response's `workspaceProfileId`, and confirms that
context, source provenance, fresh token, and the normal confirmation action
at both viewport widths.

| AC | Final selector evidence | Result |
|---|---|---|
| 1 | Chrome: automatic non-default candidate selection, explicit selector override, submitted override, and subsequent preflight preserving Profile-set context at 1440x900 and 644x900 | Pass |
| 2 | External-capability acknowledgement remains gated and confirmable after the selector flow | Pass |
| 3 | Running/failed/skipped/fallback Run detail and safe Plugin/result projection remain asserted | Pass |
| 4 | Explicit selection creates a fresh Run; Rerun remains a fresh, confirmable preflight with source provenance | Pass |
| 5 | Artifact inspector/source synchronization and Escape focus behavior remain covered | Pass |
| 6 | Required Chrome workflow matrix, including selector and Rerun handoff, passes with no horizontal overflow at both widths | Pass |

Commands/results:

| Command | Result |
|---|---|
| `KB2_BROWSER_TESTS=1 pytest -q tests/contract/test_workbench_browser.py::test_fixture_backed_document_preflight_and_ingestion_state_matrix tests/contract/test_workbench_browser.py::test_fixture_backed_ingestion_artifact_inspector_sync_and_escape` | `4 passed in 7.28s` |
| `pytest -q tests/contract/test_workbench_documents.py tests/contract/test_workbench.py tests/contract/test_workbench_studio.py tests/contract/test_ingestion_engine.py tests/integration/test_ingestion_engine_e2e.py tests/contract/test_trace_contracts.py` | `45 passed in 1.12s` |
| `python -m compileall -q src tests`; `node --check src/kb2_runtime/workbench/static/workbench.js`; `git diff --check` | Passed |

**Acceptance-ready.** All S-024 acceptance criteria have passing direct
contract and Chrome evidence; the visual matrix is available and not blocked
by the environment.
