# S-024: Document, Ingestion Run, And Artifact UI

- **Parent Feature:** FEAT-005
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-010, S-022

## Outcome

Let engineers submit representative documents, understand Profile resolution,
inspect every ingestion stage, and trace typed Artifacts back to source.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-004`, `DES-005`, `DES-007`, `DES-008`, `DES-016` | Confirmed through 2026-09-11 |
| FD | `docs/designs/features/FEAT-002-configurable-ingestion-engine.md#FD-003`, `FD-004` | Approved 2026-09-10 |
| UI | `docs/ui/reference.md#UI-003`, `UI-004`, `UI-005`, `UI-013` | Confirmed 2026-09-11 |
| Feature | `docs/features/FEAT-005-knowledge-engine-experiment-workbench.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Preflight, Profile resolution, plan, stage, Artifact, metrics, and recovery
  state come from engine/control APIs. `[FEAT-005]`
- Automatic selection shows deterministic inputs, matched rules, candidates,
  and final Profile. `[DES-007][UI-003]`
- Retry preserves the plan; changed configuration creates a new Run.
  `[DES-008][UI-004]`
- Copy distinguishes local persistence from data sent by an externally backed
  selected stage before execution. `[DES-016][UI-003]`

## Relevant UI Reference

- Documents and upload: `isDocs` line 265; `upOpen` line 1312.
- Ingestion Run: `isIng` line 332.
- Artifact Inspector: `artOpen` line 1451.
- Shared visual language: `UI-013`.

## Scope

- Document list, upload/preflight, explicit/automatic Profile selection, new Run
  routing, stage flow/inspector, plan/routing detail, valid recovery actions.
- Artifact tabs for applicable raw, Canonical, tree, table, Chunk, metadata, and
  lineage views with synchronized source locator highlighting.

## Non-goals

- Browser parsing, raw vector display, arbitrary retry, fake format support,
  lifecycle governance, or the prototype's absolute no-remote-data claim.

## Acceptance Criteria

1. File selection presents API-backed preflight and explicit/automatic Profile
   controls, including matched-rule rationale, before starting a new Run.
2. Any selected external stage is disclosed before execution; local-only plans
   are not described using broader unsupported privacy claims.
3. Run detail renders only resolved stages and exposes state, Plugin, inputs,
   outputs, timing, metrics, quality, attempts, and structured safe failures.
4. Stop, retry, rerun, and Artifact actions appear only when the Run contract
   permits them and preserve the immutable-plan rules.
5. Artifact views are schema-conditional and synchronize stable Canonical/table
   or Chunk identity with real source locators and lineage.
6. Desktop and narrow screenshots cover upload, automatic selection, running,
   failed, fallback/retry, and Artifact-source inspection without overlap.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-5 | API-state, resolution, recovery, source-sync, and accessibility tests | Integration and end-to-end |
| 6 | Reference-state screenshots and overflow/source-highlight checks | Visual regression |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 1-2, 6 | UI-003 | 1440 x 900 and narrow below 900 px, observed around 644 px | Preflight and automatic match | Dense document surface and compact modal with clear rationale/disclosure | State screenshots |
| 3-4, 6 | UI-004 | 1440 x 900 and narrow context above | Running, failed, skipped, fallback, retry | Stable stage flow and persistent diagnostic inspector | State screenshots |
| 5-6 | UI-005 | Desktop and narrow contexts above | Canonical, table, Chunk, lineage | Large inspector, schema tabs, synchronized source highlight | Screenshots and interaction recording |
| 6 | UI-013 | All contexts above | Interactive/exception states | Adopted dense ruled layout and semantic status language | Screenshot comparison |

## Open Questions

None. Renderer and upload implementation belong to Story design.

## Relationships And Blocks

- Enables Artifact reuse in S-025 and cross-run diagnosis in S-027.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-005 and UI Reference sources.
- **2026-09-11:** Story boundary confirmed by the user.
