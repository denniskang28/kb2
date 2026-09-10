# Lean Story Template

```md
# S-###: Name

- Parent Feature:
- Status: Draft / Needs Confirmation / Confirmed / Blocked / In Development / Implemented / Superseded
- Phase:
- Priority:
- Dependencies:

## Outcome
## Context Manifest
| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ/DES/UI/FD | path#anchor | confirmed version or date |

## Inherited Requirements And Constraints
Self-contained statements needed by development, each tagged with source IDs.

## Relevant UI Reference
Exact prototype route, file, selector, state, or region; omit when not relevant.

## Scope
## Non-goals
## Acceptance Criteria
## Verification Intent
| AC | Evidence Needed | Test Level |
|---|---|---|

## Visual Acceptance Matrix
| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
## Open Questions
## Relationships And Blocks
## Change History
```

Omit irrelevant optional sections. `Visual Acceptance Matrix` is required when
a confirmed Visual Reference applies to the Story and omitted otherwise. Every
visual row must map to an observable AC and an exact UI anchor. Do not invent
missing viewports, responsive behavior, tolerances, or allowed deviations;
leave the Story at `Needs Confirmation` when an unresolved value materially
affects valid acceptance. Do not make the technical implementation part of the
product contract unless an inherited binding design constraint requires it.
