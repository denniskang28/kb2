# S-022: Workbench Shell And Runtime Overview

- **Parent Feature:** FEAT-005
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-001, S-002, S-003

## Outcome

Give engineers a responsive local workbench shell and operational overview that
routes into engine workflows and distinguishes core readiness from optional
external capabilities.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-001`, `DES-016` | Confirmed through 2026-09-11 |
| UI | `docs/ui/reference.md#UI-001`, `UI-002`, `UI-013` | Confirmed 2026-09-11 |
| Feature | `docs/features/FEAT-005-knowledge-engine-experiment-workbench.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- The browser calls control APIs and contains no engine compilation, execution,
  validation, or metric domain logic. `[DES-001][FEAT-005]`
- Core runtime readiness is separate from optional DeepSeek or Plugin capability
  readiness; the UI cannot claim the complete system is offline. `[DES-016]`
- Simplified Chinese is the product locale; prototype controls and language
  switching are excluded. `[UI-001][UI-013]`

## Relevant UI Reference

- Shell: `docs/ui/kb_ui.zip!/Knowledge Engine Lite.dc.html:50`, route definition
  near line 2584.
- Overview: `isOv` route at archive entry line 121.
- Visual language: `UI-013`; desktop 1440 x 900 and narrow below 900 px,
  observed around 644 px.

## Scope

- Eight-destination navigation, breadcrumbs, workspace context, runtime and
  capability status, active-Run status, responsive drawer, and overview.
- Recent Runs, dependency band, failed-Run triage, recent comparisons, primary
  route commands, and populated/empty/dependency/error states.

## Non-goals

- Authentication, administration, browser-owned domain state, prototype control
  bar, synthetic values as defaults, or implementing destination workflows.

## Acceptance Criteria

1. All eight destinations are keyboard-operable and preserve current workspace
   context while routing without duplicating engine state in the browser.
2. Core, optional provider, and Plugin capability states are separately labelled
   from liveness, with safe actionable diagnostics.
3. Overview renders API-backed recent Runs, dependency status, failed-Run
   actions, recent comparisons, and the four adopted primary commands.
4. Populated, first-use empty, dependency-unavailable, loading, and recoverable
   refresh-error states are distinguishable and do not shift primary layout
   incoherently.
5. At 1440 x 900 the shell preserves the 220 px navigation and compact work
   surface; below 900 px it uses the adopted drawer navigation without overlap.
6. Typography, rules, status colors, actions, focus, hover, disabled states, and
   density visibly follow UI-013 without the prototype toolbar.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-4 | Navigation, API-state, failure, and accessibility tests | Component and end-to-end |
| 5-6 | Reference-state screenshots and layout/overflow checks | Visual regression |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 5 | UI-001 | 1440 x 900 | Populated | Persistent 220 px nav and compact sticky context bar | Screenshot comparison |
| 5 | UI-001 | Narrow below 900 px; observed around 644 px | Navigation open/closed | Drawer replaces persistent nav with no content overlap | Screenshots and overflow check |
| 4, 6 | UI-002 | 1440 x 900 | Populated, empty, dependency unavailable, refresh error | Dense status band/table/triage hierarchy and stable commands | State screenshots |
| 6 | UI-013 | Desktop and narrow contexts above | Interactive states | Adopted neutral, ruled, zero-radius, semantic-status visual language | Screenshot comparison |

## Open Questions

None. Component framework belongs to Story design.

## Relationships And Blocks

- Establishes shared FEAT-005 shell; S-023 through S-027 depend on it.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-005 and UI Reference sources.
- **2026-09-11:** Story boundary confirmed by the user.
