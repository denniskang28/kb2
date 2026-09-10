---
name: change-triage
description: "Read-only classify an unexpected behavior, product request, design adjustment, UI reference change, proposed fix, or refactor against Lean Harness evidence. Use when the correct owner is unclear: PRD, Core Design, UI reference, Feature shared rule, Story contract, Story technical design, or code."
---

# Change Triage

Inspect the strongest confirmed expectation and relevant code/test/runtime
evidence. Do not modify anything.

Classify:

1. Nature: `Defect`, `Correction`, `Enhancement`, `New`, `Refactor`, or
   `Investigation`.
2. Owner: PRD, Core Design, UI reference, Feature shared rule/optional design,
   Story contract, Story technical design, or code/test.
3. Impact: no upstream change, Story recompilation, Feature remapping, or global
   reapproval.

Use [classification-rules.md](references/classification-rules.md). Report
classification, confidence, evidence, affected IDs, risk gates, and one
recommended workflow. Stop before writes or implementation.
