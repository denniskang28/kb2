---
name: feature-design
description: Optionally clarify and persist selected cross-Story product or experience design for one Feature. Use only when requested or when shared journeys, state, data semantics, permissions, UI behavior, or failure rules are too ambiguous for safe Story decomposition; never require exhaustive coverage.
---

# Optional Feature Design

Require one Feature ID and a design topic or a concrete cross-Story ambiguity.
Read the Feature manifest and only its relevant REQ/DES/UI anchors.

## Workflow

1. Define the bounded design question.
2. Discuss only material shared behavior and alternatives.
3. Assign stable `FD-###` IDs to confirmed shared decisions.
4. Keep proposals and open questions visibly non-authoritative.
5. Save to `docs/designs/features/FEAT-###-<slug>.md` using
   [feature-design-template.md](references/feature-design-template.md).
6. Require user confirmation before an FD item becomes a Story source.

Omit irrelevant UI, data, API, permissions, failure, NFR, testing, or slicing
sections. Do not attempt design completeness, create Stories, alter global
product/core design silently, or write code. Feature Design is never a default
gate.
