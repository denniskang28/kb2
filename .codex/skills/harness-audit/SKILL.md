---
name: harness-audit
description: Perform a read-only Lean Harness audit of product analysis, a Feature route, or a Story contract. Use to find unsupported AI invention, missing source coverage, contradictions, stale anchors, material ambiguity, or untestable acceptance without requiring exhaustive document sections.
---

# Lean Harness Audit

Infer scope from the target: no ID means product-analysis sources, `FEAT-*`
means Feature routing, and `S-*` means Story readiness. Read
[audit-rules.md](references/audit-rules.md), then inspect only the target and its
direct anchors.

## Report

Lead with severity-ordered findings. For each finding include evidence, impact,
owner, and return path. Then report readiness as `Passed`, `Failed`, or
`Blocked`, plus unsupported facts, missing coverage, stale sources, open
questions, and the next workflow.

Do not fail an artifact because an irrelevant template dimension is absent.
Do not modify files, statuses, code, or tests. Audit success never grants user
approval.
