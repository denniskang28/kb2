---
name: review
description: Review a Story branch, diff, or PR against its self-contained Story contract, approved technical design, implementation, and tests. Use for final delivery review; inspect upstream PRD, Core Design, Feature, or UI sources only when staleness, contradiction, or unapproved behavior requires provenance.
---

# Story Review

Read the Story, approved Story design, current diff, test report, and relevant
code. Do not load complete upstream planning documents by default.

## Priorities

1. Behavioral regressions and missing ACs.
2. Security, privacy, authorization, tenant, data, transaction, idempotency,
   migration, and compatibility risks.
3. Deviation from the approved Story technical design.
4. Product decisions introduced in code but absent from the Story contract.
5. Missing tests, unrelated scope, or stale Story/design evidence.

Lead with severity-ordered findings and exact file/line evidence. If an upstream
conflict is suspected, inspect only the named source anchors and report the
correct return path. Default to read-only findings.
