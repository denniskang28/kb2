# S-015: Grounded Generation And Final-State Validation

- **Parent Feature:** FEAT-003
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-001, S-003, S-011, S-014

## Outcome

Produce an evidence-grounded response through the configured external DeepSeek
provider, verify its citations, and return one authoritative final state.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-009` through `REQ-011` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-009`, `DES-012`, `DES-016` | Confirmed through 2026-09-11 |
| FD | `docs/designs/features/FEAT-003-configurable-query-engine.md#FD-005`, `FD-006` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-003-configurable-query-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Generation receives only declared question/session input and assembled
  Evidence, using answer-visible citation keys. `[REQ-011][FD-006]`
- Verification checks citations, evidence support, forbidden content, and
  Profile answerability rules. `[DES-012][FD-006]`
- Repair is bounded and traceable, uses the same Evidence, and cannot retrieve
  or widen context unless the resolved plan explicitly includes that loop.
  `[DES-012][FD-006]`
- Final state is `ANSWERED`, `CLARIFICATION_REQUIRED`, `ABSTAINED`, or `FAILED`;
  only `ANSWERED` requires valid supporting citations. `[DES-012]`
- External DeepSeek is one provider adapter; missing credentials gate only a
  plan requiring generation and never core readiness. `[DES-016]`

## Scope

- Provider-neutral generation port and external DeepSeek adapter integrated
  with S-001 capability readiness and sanitized diagnostics.
- Verification, bounded repair, clarification/abstention decisions, final
  response contract, and complete bounded Query trace.
- Executable baseline Query Profiles over fixed indexed Artifacts.

## Non-goals

- Chat history, unsupported model knowledge, silent retrieval, provider-specific
  engine contracts, local Ollama hosting, or Azure model integration.

## Acceptance Criteria

1. Generation sends only the declared bounded question/session fields and
   Evidence, and records pinned provider/model/prompt/parameter identity without
   storing credentials in traces.
2. A supported answer returns `ANSWERED` only when every required citation key
   resolves to supporting Evidence under the active Profile.
3. Ambiguous, insufficient, invalid-citation, provider-failed, repair-success,
   and repair-exhausted fixtures produce the declared final states and traces.
4. Repair attempts are bounded, preserve Evidence identity, and cannot silently
   add retrieval or general-knowledge support.
5. Missing DeepSeek configuration reports the required capability as unavailable
   and fails only generation-dependent Query plans with a safe action.
6. At least two Query Profiles execute against the same indexed Artifacts
   without code or index mutation and preserve stage-level attribution.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1, 5 | Sanitized provider boundary and readiness scenarios | Security and integration |
| 2-4 | Supported/ambiguous/insufficient/repair fixtures | Contract |
| 6 | Fixed-artifact multi-Profile execution | End-to-end |

## Open Questions

None. Exact model, prompts, parameters, and thresholds belong to Story design
and evaluation calibration.

## Relationships And Blocks

- Completes FEAT-003 and enables answer evaluation and Query Lab UI.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-003 sources and external
  DeepSeek provider decision.
- **2026-09-11:** Story boundary confirmed by the user.
