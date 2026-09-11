# S-020: Judge Calibration And Semantic Metrics

- **Parent Feature:** FEAT-004
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-001, S-016, S-019

## Outcome

Permit semantic answer metrics only through a pinned LLM Judge whose behavior is
calibrated against reviewed human labels and cannot silently close hard gates.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-015`, `REQ-016` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-013`, `DES-014`, `DES-016` | Confirmed through 2026-09-11 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-010` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-004-reproducible-quality-evaluation.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Judges are used only for criteria that cannot be evaluated deterministically.
  `[REQ-015][DES-014]`
- Judge provider, model, prompt, and parameters are pinned and evaluated against
  a reviewed calibration set. `[FD-010]`
- Reports expose agreement and material false-positive/false-negative behavior
  by relevant slice. `[FD-010]`
- An uncalibrated or drifted Judge cannot close a hard gate. `[FD-010]`
- DeepSeek is an initial provider adapter, not an engine-specific Judge
  contract. `[DES-016]`

## Scope

- Judge Plugin contract, calibration dataset binding, calibration Run/result,
  agreement/error reporting, eligibility state, and drift comparison.
- Provider-neutral invocation with external capability readiness and sanitized
  bounded evidence.

## Non-goals

- Replacing deterministic metrics, auto-generating human truth, hard-coding one
  provider, or inventing acceptable calibration thresholds.

## Acceptance Criteria

1. Every Judge result pins provider/model/prompt/parameters, metric rubric,
   calibration snapshot, case identity, and bounded rationale evidence.
2. Calibration reports agreement and false-positive/false-negative behavior by
   applicable slice against reviewed human labels.
3. Missing, insufficient, stale, or failed calibration marks Judge metrics
   advisory and ineligible for hard-gate closure.
4. A deliberately biased or drifted Judge fixture is detected and cannot pass
   by aggregate agreement that hides a failed critical slice.
5. Missing external provider configuration affects Judge-dependent runs only
   and does not corrupt deterministic metric results or core readiness.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-4 | Calibrated, uncalibrated, biased, and drift fixtures | Contract and integration |
| 5 | External capability isolation scenario | Resilience |

## Open Questions

None. Thresholds and rubric content require representative calibration during
Story design.

## Relationships And Blocks

- Enables semantic metrics and hard-gate decisions in S-021.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-004 sources.
- **2026-09-11:** Story boundary confirmed by the user.
