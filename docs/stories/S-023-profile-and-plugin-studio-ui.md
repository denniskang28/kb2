# S-023: Profile And Plugin Studio UI

- **Parent Feature:** FEAT-005
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-003, S-004, S-011, S-022

## Outcome

Let engineers inspect registered Plugin contracts and author declarative
Ingestion or Query Profiles through API-backed form and YAML workflows.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-002`, `DES-003` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-002-configurable-ingestion-engine.md#FD-001`, `FD-002`; `docs/designs/features/FEAT-003-configurable-query-engine.md#FD-005` | Approved 2026-09-10 |
| UI | `docs/ui/reference.md#UI-006`, `UI-007`, `UI-013` | Confirmed 2026-09-11 |
| Feature | `docs/features/FEAT-005-knowledge-engine-experiment-workbench.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Profile schemas, compatibility, compilation, and validation come exclusively
  from engine APIs. `[FEAT-005]`
- Editors cannot accept commands, script paths, code, credentials, arbitrary
  nodes, package installs, or container commands. `[DES-002][DES-003]`
- Working configurations and candidates are not approval, publication,
  rollback, or user-facing version management. `[UI-006]`

## Relevant UI Reference

- Profile Studio: `isStudio` route at archive entry line 465.
- Plugin Registry/detail: `isRegistry` route at line 660 and `plugOpen` drawer
  at line 1393.
- Shared visual language and responsive contexts: `UI-013`.

## Scope

- Searchable Ingestion/Query Profile lists, form/YAML editor, ordered stages,
  compatible Plugin choices, schema-generated fields, conditions, fallbacks,
  validation, compile preview, working save, dry run, and candidate copy.
- Search/filter Plugin Registry and contract/detail inspector backed by S-003.

## Non-goals

- Browser-side compiler, arbitrary code editor, remote installation, activation,
  publication, or adopting prototype Plugin/Profile data.

## Acceptance Criteria

1. Form and YAML modes round-trip one declarative Profile without losing typed
   stages, parameters, conditions, fallbacks, or engine-provided diagnostics.
2. Stage Plugin choices are filtered by Registry compatibility and parameter
   forms are generated from descriptor schemas.
3. Validation and compile preview show field-addressable errors and resolved
   plan/digest returned by the engine; invalid Profiles cannot be dry-run.
4. Registry search/filter/detail exposes implemented descriptors, readiness,
   schemas, resource hints, timeout, contract tests, safe examples, and Runs.
5. Desktop and narrow layouts preserve usable lists, editor/inspector hierarchy,
   accessible reorder actions, and no overlapping controls or text.
6. Profile and Registry states visibly follow UI-006, UI-007, and UI-013 with
   screenshot evidence for valid, invalid, draft, and unavailable states.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-4 | API contract, form/YAML, validation, and accessibility tests | Component and integration |
| 5-6 | Desktop/narrow state screenshots and overflow checks | Visual regression |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 5-6 | UI-006 | 1440 x 900 | Valid, invalid, draft | Dense Profile list, stable editor toolbar, stage order, and selected-stage inspector | State screenshots |
| 5-6 | UI-007 | 1440 x 900 | Available, degraded, unavailable; detail open | Dense Registry plus large contract drawer | State screenshots |
| 5 | UI-006, UI-007 | Narrow below 900 px; observed around 644 px | Editor and drawer | Content reflows or scrolls without overlap; actions remain reachable | Screenshots and overflow check |
| 6 | UI-013 | Desktop and narrow contexts above | Focus, hover, disabled, error | Adopted typography, rules, controls, icons, and semantic colors | Screenshot comparison |

## Open Questions

None. Editor and component libraries belong to Story design.

## Relationships And Blocks

- Depends on engine-owned Profile/Registry APIs and S-022 shell.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-005 and UI Reference sources.
- **2026-09-11:** Story boundary confirmed by the user.
- **2026-09-12:** Delivered Profile and Plugin Studio UI after API, browser,
  regression, and final-review evidence passed; delivery commit `b8af610` was
  fast-forwarded into local main.
- **2026-09-15:** Completed the UI-006/UI-013 Profile Studio parity repair with
  server-authoritative summaries and canonical YAML, three-level form editing,
  guarded async actions, exact diagnostic focus/ARIA, responsive desktop/narrow
  layouts, and ten reviewed visual baselines; independent review passed.
- **2026-09-15:** Repaired candidate copy so Query selection rules and
  Ingestion document-class/preflight rules follow the new Profile ID while
  unrelated business configuration and the saved source remain unchanged.
