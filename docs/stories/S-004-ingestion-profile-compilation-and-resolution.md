# S-004: Ingestion Profile Compilation And Resolution

- **Parent Feature:** FEAT-002
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-002, S-003

## Outcome

Let an engineer author a declarative Ingestion Profile that is validated and
deterministically compiled into one immutable, executable plan snapshot.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-002` through `REQ-005` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-002`, `DES-003`, `DES-006`, `DES-007` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-002-configurable-ingestion-engine.md#FD-001`, `FD-004` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-002-configurable-ingestion-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Profiles are JSON or YAML data and contain no command, script path, code,
  credential, or unrestricted environment reference. `[REQ-002][DES-002]`
- A Profile composes extraction, structure, chunking, enrichment, embedding,
  and indexing axes through allowlisted Plugin IDs. `[DES-003][DES-006]`
- Each expanded stage has typed named inputs/outputs, validated configuration,
  optional bounded conditions, and explicit fallback candidates. `[FD-001]`
- Compilation resolves defaults and references, rejects invalid graph order,
  cycles, unbound inputs, and incompatible Artifact schemas, then emits an
  immutable plan and digest. `[REQ-003][FD-001]`
- Selection precedence is explicit Profile, explicit document-class rule,
  deterministic preflight rules, then configured default. `[REQ-004][DES-007]`

## Scope

- Profile schema, parser, semantic validator, compiler, plan digest, and safe
  validation diagnostics.
- Deterministic resolver over declared document features with recorded
  candidates, matched rules, conditions, and final selection.
- Extension proof that a registered component can be referenced without
  changing compiler or resolver source.

## Non-goals

- Running the plan, implementing processing Plugins, generic DAG authoring, or
  UI editing.
- Hidden provider switching or runtime-generated executable expressions.

## Acceptance Criteria

1. A valid Profile expands all six component axes into a complete typed plan
   whose canonical serialization and digest are stable for identical inputs.
2. Unknown Plugins, invalid parameters, cycles, unbound inputs, incompatible
   schemas, unsupported conditions, and executable content are rejected with
   bounded field-addressable errors before execution.
3. Explicit selection and deterministic rules follow the confirmed precedence
   and record every considered rule, observable input, match, and final choice.
4. Conditions can read only allowlisted document features and prior declared
   quality signals; fallback order and acceptance rules are explicit in plan.
5. Adding a compatible registered component requires Profile data and Plugin
   registration only, with no compiler/resolver modification.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-2 | Valid/invalid Profile fixtures and stable digest snapshots | Contract |
| 3-4 | Resolver precedence and condition/fallback matrices | Unit and contract |
| 5 | Synthetic extension fixture | Architecture regression |

## Open Questions

None. Exact syntax and validation library belong to Story design.

## Relationships And Blocks

- Depends on S-002 Artifact identities and S-003 Registry descriptors.
- Enables S-005 through S-010 and FEAT-005 Profile editing.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-002 sources.
- **2026-09-11:** Story boundary confirmed by the user.
- **2026-09-11:** Implemented, independently verified, reviewed, and ready for
  delivery close through the S-004 Story Pipeline.
