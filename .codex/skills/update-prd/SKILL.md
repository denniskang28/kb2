---
name: update-prd
description: Reconcile an approved product-scope or business-rule change with the concise PRD, preserving stable REQ IDs and identifying only affected Features and compiled Stories. Use after change triage; route technical design changes to core-design-capture instead of expanding the PRD.
---

# Update PRD

Read current state, the changed REQ anchors, and only directly affected Feature
and Story manifests. Require the change to be accepted or leave it proposed.

## Workflow

1. Classify as `New`, `Enhancement`, `Correction`, `Replacement`,
   `Deprecation`, or `Phase Move`.
2. Update only `docs/prd.md`, preserving IDs, source, last-changed date, and
   history.
3. Route technology, architecture, data, API, class, or algorithm decisions to
   `$core-design-capture` unless they are observable product contracts.
4. Identify exact affected Features, Stories, UI references, and technical
   designs.
5. Mark material PRD changes `Needs Approval`.
6. After approval, reconcile Feature routing and recompile only affected
   unstarted Story contracts. Never rewrite implemented Story history.

Do not generate complete baseline documents, Feature designs, Stories, code,
tests, or migrations in this workflow.
