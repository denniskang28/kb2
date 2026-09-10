---
name: story-pipeline
description: Coordinate one confirmed self-contained Story or a tightly coupled batch through context validation, just-in-time technical design, implementation, automated testing, bounded repair, review, and optional PR handoff. Use Story-local context by default and pause only for material decisions or contract conflicts.
---

# Story Pipeline

Require Story IDs or an explicit next eligible Story. Never infer all backlog
work.

## Pipeline

1. Read `AGENTS.md`, current state, target Stories, and direct dependencies.
2. Run a targeted `$harness-audit` to verify each Story is confirmed,
   self-contained, current, and unblocked.
3. Create or confirm the delivery branch before design or implementation. Start
   a one-Story run from the current local `main` HEAD on
   `feature/<story-id>-<short-name>`; use `feature/batch-<short-name>` for a
   tightly coupled batch. Do not base a new delivery branch on another feature
   branch or an arbitrary detached commit.
4. After the readiness and branch gates pass, create
   `docs/run-logs/<YYYY-MM-DDTHHMMSS>-<story-id>.md` from the run-log template,
   using the local delivery-start time and lowercase Story ID (for example,
   `2026-07-27T191733-s-070.md`), before delegating delivery work. For a batch,
   create one run log per Story.
5. Delegate technical design to `design-agent` with `$story-design` and current
   code. The pipeline coordinator must not substitute its own design work for
   this stage.
6. Treat the pipeline invocation as approval for the Story technical design and
   its implementation choices. Record material technical decisions in the
   design and continue directly to development; do not request a separate
   design approval.
7. Delegate implementation to `dev-agent` with `$story-development`.
8. Delegate verification to `test-agent` with `$test-and-regression`.
9. Return failures to the correct owner and repeat delegated development/test at most five
   rounds.
10. Delegate final review to `review-agent` with `$review`; repair and retest
    actionable findings through the owning agents.
11. Reconcile Story status and current state only after evidence passes. Before
    the delivery commit, make the run log explicit that verification and review
    passed and that it is ready for delivery close; do not claim a merge that
    has not happened.
12. For every successfully delivered Story, stage only that Story's owned
    delivery changes and create one descriptive delivery commit on its delivery
    branch. Switch to local `main` and fast-forward merge that exact commit.
    Verify with Git that the delivery commit is an ancestor of `main` and that
    `main` is clean. Never amend, rebase, reset, or otherwise rewrite the
    delivery branch or `main` after the delivery commit has been merged.
13. If the run log needs the resulting commit SHA, fast-forward result, or final
    main HEAD recorded after the merge, update it only on local `main` and make
    one normal, documentation-only reconciliation commit. It must state both
    the delivery commit and the reconciliation commit, if any. Verify again
    that `main` is clean and still contains the delivery commit. Do not amend
    the delivery commit to add post-merge evidence.
14. Stop before committing if the staged set includes unrelated changes, and
    stop before merging if the delivery branch cannot fast-forward onto local
    `main`. Stop if Git ancestry or a clean `main` cannot be demonstrated. Do
    not push or create a PR unless explicitly requested.
15. Before every turn ends, emit the structured checkpoint defined below. If a
    safe next step remains but the turn or delegated-round budget is ending,
    use `CONTINUE_SAFE`; do not imply that delivery is complete.

## Context Boundary

Delivery agents read the Story, approved Story design, exact referenced UI
regions, code, diff, and tests. They do not load complete PRD, Core Design,
Feature, or optional Feature Design documents unless a stale source or concrete
conflict requires provenance inspection.

## Required Stops

- Story is not confirmed or self-contained;
- stale or missing source snapshot;
- the delivery branch cannot be created or confirmed from the current local
  `main` HEAD;
- material open question or unmet dependency;
- scope or product-contract expansion;
- tests or review still fail after bounded repair;
- required verification is unavailable with no valid substitute.

## Structured Checkpoint

End every pipeline turn with exactly one fenced YAML block. Keep values concise
and omit raw logs, secrets, credentials, and sensitive document content.

```yaml
story_pipeline_checkpoint:
  story: S-001
  phase: design|development|test|review|delivery_close
  state: CONTINUE_SAFE|WAIT_USER|BLOCKED|DELIVERED
  reason_code: TURN_BUDGET_EXHAUSTED|SAFE_REPAIR_CONTINUATION|REDUNDANT_APPROVAL_GATE|USER_DECISION_REQUIRED|CONTRACT_CONFLICT|DEPENDENCY_BLOCKED|PERMISSION_OR_CREDENTIAL_REQUIRED|GIT_OR_OWNERSHIP_CONFLICT|DELIVERED
  last_completed_stage: concise stage name or none
  next_action: concise bounded action or none
  required_user_decision: true|false
  evidence_refs:
    - run-log section, test command, review result, or commit SHA
```

Use `CONTINUE_SAFE` only when the next action remains within the confirmed Story
and this pipeline's existing authorization. Use `WAIT_USER` for a material
product or contract decision. Use `BLOCKED` for an unmet dependency, permission,
credential, conflict, destructive action, or exhausted repair bound. Use
`DELIVERED` only after the delivery-close Git and clean-main gates pass.

## Run Evidence

Maintain a bounded run log only when a delivery run actually starts. The
canonical path is `docs/run-logs/<YYYY-MM-DDTHHMMSS>-<story-id>.md`, using the
local delivery-start time and lowercase Story ID.

Create the log after the readiness and branch gates pass. Update it after every
delegated design, development, test, review, and repair step. Each round must
name the responsible agent, its action, the relevant build/test evidence, and
any failure type and return target. Do not collapse a multi-stage delivery into
a single `pipeline` round. Complete its AC evidence, review, and pre-merge
reconciliation sections before the delivery commit. Record post-merge facts in
the delivery-close section only through the normal main reconciliation commit
described above. Use
[run-log-template.md](references/run-log-template.md).
