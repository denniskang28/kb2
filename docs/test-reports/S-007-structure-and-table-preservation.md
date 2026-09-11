# Test Report

## Story And Designs

- Story: `docs/stories/S-007-structure-and-table-preservation.md`
- Approved design: `docs/designs/stories/S-007-structure-and-table-preservation.md`
- Scope reviewed: the `structure.canonical@1` descriptor and implementation,
  Canonical contract/serializer, profile compiler, S-007 fixtures, and the
  relevant contract and integration regression surface.

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | `test_hierarchy_derives_links_without_changing_identity_or_locators`; `test_layout_normalizes_pdf_reading_order_without_rewriting_other_references` | Contract | Pass |
| 2 | `test_table_fixture_round_trips_losslessly_through_a_fresh_canonical_parse`; `test_table_structure_artifact_persists_and_restarts` | Contract / Integration | Pass |
| 3 | `test_table_semantics_fail_for_every_compatible_strategy`; `test_layout_strategy_validates_table_semantics_after_ordering`; `test_invalid_structure_fails_with_safe_evidence_and_no_commit`; `test_malformed_and_unbounded_canonical_inputs_fail_without_output`; `test_closed_strategy_configuration_rejects_unknown_or_undeclared_values` | Contract | Pass |
| 4 | `test_three_characteristics_reuse_the_same_structure_component_with_configuration_only` | Integration | Pass |
| 5 | `test_declared_fallback_order_and_acceptance_policy_are_serialized_without_execution`, plus direct safe-failure coverage above | Integration / Contract | Pass |

## Tests Added Or Updated

- Updated the layout golden to assert that, after deterministic PDF ordering,
  every field other than `reading_order` is preserved. This makes locator and
  relationship preservation executable evidence rather than an implication of
  the expected element IDs.
- Added repaired semantic coverage proving caption, relationship, and locator
  table failures are rejected after `hierarchy`, `layout`, and `table`
  strategies, with safe failure evidence and no output commit.
- Added profile-selected execution for hierarchy, layout, and table fixtures,
  asserting the compiled candidate's registered plugin ID produces each
  output.
- Added Docker-backed ArtifactService persistence/restart coverage for the
  table strategy.

## Commands And Results

| Command | Result |
|---|---|
| `pytest -q tests/contract/test_structure.py tests/integration/test_structure_profiles.py tests/contract/test_canonical_document.py tests/contract/test_plugins.py tests/contract/test_ingestion_profiles.py` | 50 passed |
| `pytest -q` in the restricted sandbox | 147 passed, 2 failed, 2 skipped; both failures were localhost bind attempts blocked by sandbox policy |
| `pytest -q -ra tests/contract/test_structure.py tests/integration/test_structure_profiles.py tests/contract/test_runtime_cli.py` with host permission | 41 passed |
| `pytest -q tests/contract/test_structure.py tests/integration/test_structure_profiles.py tests/integration/test_structure_persistence.py` | 17 passed, 1 skipped in the restricted sandbox because Docker socket access is denied there |
| `docker info` with host permission | Passed; the Docker daemon is available |
| `pytest -q -ra tests/integration/test_structure_persistence.py` with host permission | Passed; table Artifact persisted and passed readback after a real runtime restart |
| `pytest -q -ra` with host permission after repair | Passed; complete regression collection exited successfully |

## Visual Evidence

| AC | UI Anchor | Capture Conditions | Baseline | Diff Or Review Evidence | Result |
|---|---|---|---|---|---|
| N/A | N/A | No UI or visual acceptance matrix applies to this pure in-process Canonical Plugin. | None | N/A | N/A |

## Visual Baseline Changes

None.

## Build Status

Pass. The package imports and all focused tests execute against the changed
source without a build or migration requirement.

## Test Status

Pass. All S-007 focused, persisted-restart, and complete regression checks ran
successfully with the required host permissions.

## Failure Classification

- `tests/contract/test_runtime_cli.py::test_preflight_tolerates_transient_port_release`
  and `::test_preflight_rejects_sustained_port_conflict_with_sanitized_code`:
  environment constraint. Both fail in the restricted sandbox at
  `socket.bind(("127.0.0.1", 0))` with `PermissionError`, before runtime
  application behavior. Both pass when run with host permission.
- Docker checks in the restricted sandbox: environment constraint. The sandbox
  denies access to the Docker daemon socket. `docker info` succeeds with host
  permission, and the new S-007 restart integration passes there; this is not
  a missing daemon or an implementation failure.

## Feedback For Development

None. The repair closes the prior semantic-validation and persisted-restart
coverage gaps. The profile test invokes each compiled candidate directly;
runtime first-acceptable selection and persisted selection events remain S-010
ownership.

## Remaining Gaps

None for S-007 acceptance. Docker-backed verification requires host permission
in this environment, which was available for the new restart test and full
regression run.

## Regression Coverage

- Focused Canonical, Plugin Registry/Executor, Profile compilation, table
  semantic validation, and S-007 structure suites passed.
- The real Docker-backed persistence/restart test and the complete regression
  collection passed with host localhost and Docker permissions.
