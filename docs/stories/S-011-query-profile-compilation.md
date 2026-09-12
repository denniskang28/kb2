# S-011: Query Profile Compilation

- **Parent Feature:** FEAT-003
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-002, S-003, S-004, S-009

## Outcome

Let an engineer declaratively compose a typed Query Profile and compile it into
one immutable plan suitable for reproducible execution and comparison.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-009` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-002`, `DES-009` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-003-configurable-query-engine.md#FD-005`, `FD-007` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-003-configurable-query-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Query Profiles select typed stages from analyze, rewrite, route, retrieve,
  fuse, rerank, context, generate, verify, repair, and abstain. `[DES-009]`
- Optional stages may be omitted and branches are bounded by declared question
  or document characteristics. `[FD-005]`
- Profiles cannot introduce code or bypass common Evidence and final-state
  validation. `[DES-002][FD-005]`
- A Run pins the plan, Search Artifact, Plugins, model, prompt, and parameters;
  traces use bounded values or Artifact references. `[FD-005]`

## Scope

- Query Profile schema, semantic validator, compiler, deterministic digest, and
  compatibility checks against Registry and indexed Artifact contracts.
- Baseline configuration fixtures for text-hybrid, hierarchy-aware,
  table-aware, high-precision-fact, and section-summary families.

## Non-goals

- Executing retrieval or generation, generic DAGs, runtime model routing, or UI.

## Acceptance Criteria

1. Valid Profiles compile to stable ordered plans with typed ports, bounded
   branches, resolved Plugin/model/prompt parameters, and deterministic digest.
2. Unknown or incompatible Plugins, unbound inputs, invalid ordering, cycles,
   unsafe expressions, missing final validation, and unbounded repair loops are
   rejected with field-addressable errors.
3. The five baseline families are expressed as configuration over common stages
   rather than separate services.
4. Explicit and deterministic Profile selection records the chosen plan and
   does not mutate indexed Artifacts.
5. Identical plan inputs reproduce the same manifest identity; changed model,
   prompt, Plugin, parameter, or Search Artifact changes the snapshot identity.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-2, 5 | Valid/invalid fixtures and digest snapshots | Contract |
| 3-4 | Profile-family and selection scenarios | Architecture regression |

## Open Questions

None. Exact syntax and compilation library belong to Story design.

## Relationships And Blocks

- Enables S-012 through S-015 and Query Profile editing in FEAT-005.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-003 sources.
- **2026-09-11:** Story boundary confirmed by the user.
- **2026-09-12:** Implemented, independently verified, and reviewed through
  the Story Pipeline; ready for delivery close.
