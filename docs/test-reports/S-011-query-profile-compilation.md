# Test Report

## Story And Designs

- Story: `S-011: Query Profile Compilation`
- Approved design: `docs/designs/stories/S-011-query-profile-compilation.md`
- Scope: pure Query Profile parsing, compilation, plan identity, and
  deterministic selection. No UI or query execution is in scope.

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | JSON mapping-order identity, JSON/YAML equivalence, five family fixtures, typed stage binding and compiler diagnostics | Contract | Pass |
| 2 | Unknown Plugin, forward/cyclic binding, unsupported condition, missing final Evidence lineage, ambiguous selection-rule rejection, and raw-input repair rejection | Contract | Pass |
| 3 | `test_all_baseline_families_are_configuration_over_common_stages` compiles all five fixtures through the same fixture Registry descriptors | Architecture contract | Pass |
| 4 | Explicit, class-over-conditional, conditional, and default selection precedence; Artifact binding preservation; immutable resolution record | Unit | Pass |
| 5 | Stable identity for equivalent JSON/YAML inputs; changed Search Artifact or configuration changes digest | Contract | Pass |

## Tests Added Or Updated

- Added selection-rule overlap rejection and resolution-record immutability
  regressions.
- Added JSON/YAML equivalence and configuration-only digest-change coverage.
- Added class-over-conditional precedence and end-to-end raw-question repair
  input rejection coverage.

## Commands And Results

| Command | Result |
|---|---|
| `/Users/denniskang/anaconda3/bin/python3 -m pytest tests/contract/test_query_profiles.py tests/unit/test_query_profile_resolver.py` | Pass: 14 passed in 0.09s |
| `/Users/denniskang/anaconda3/bin/python3 -m pytest -m 'not integration' tests/contract tests/unit` | Pass: 212 passed in 0.55s |
| `python3 scripts/harness_check.py` | Pass: `REQ=17 DES=16 FEAT=5 FD=12 S=27` |
| `docker info --format 'server={{.ServerVersion}}'` | Pass: Docker daemon available, server 28.3.3 |
| `docker compose -f deploy/local/compose.yaml -f deploy/local/compose.test.yaml config --services` | Pass: merged Compose configuration resolves all six services |

## Visual Evidence

| AC | UI Anchor | Capture Conditions | Baseline | Diff Or Review Evidence | Result |
|---|---|---|---|---|---|
| N/A | N/A | S-011 has no UI scope | None | N/A | N/A |

## Visual Baseline Changes

None.

## Build Status

Pass for the Python test and harness surface. The available local interpreter
was Python 3.11.3, while `pyproject.toml` declares Python 3.12 or later; no
Python 3.12 interpreter was available in this workspace.

## Test Status

Pass. The focused S-011 suite and full non-integration regression pass.

## Failure Classification

Two initial focused failures were implementation defects and are resolved:

- The compiler initially allowed ambiguous conditional rules and deferred the
  ambiguity to resolution. It now rejects ambiguous pairs within each
  selection tier while preserving class-over-conditional precedence.
- `QueryResolutionRecord` exposed mutable mappings despite its immutable
  contract. Nested rule evidence and observables are now frozen.
- Final-review repairs are verified: a matching class rule has precedence over
  a matching conditional rule, and repair inputs cannot reintroduce raw query
  inputs.

## Feedback For Development

No remaining actionable implementation finding.

## Remaining Gaps

- Docker-backed integration tests were not run. They are not proportionate to
  S-011 because it has no persistence, service, Runner invocation, or query
  execution behavior. Docker availability and merged Compose configuration
  were verified instead.
- Exact Python 3.12 execution remains unverified because only Python 3.11.3
  was available locally.

## Regression Coverage

The non-integration contract and unit regression surface passed with 212 tests.
Existing ingestion Profile, Plugin Registry, indexing, trace, runtime, and
security coverage ran in that suite.
