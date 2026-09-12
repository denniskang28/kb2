---
name: story-pipeline-watchdog
description: Monitor one Codex Story pipeline task, distinguish active work, safe resumable pauses, required user decisions, blockers, and completed delivery, then send at most one bounded continuation instruction and record append-only audit evidence. Use from the KB story-pipeline-sequencer heartbeat when a Story pipeline may have stopped before delivery close.
---

# Story Pipeline Watchdog

Monitor one Story pipeline without replacing its delivery coordinator. Resume
only a stopped, accessible task whose pause is safe under this policy.

## Preconditions

1. Operate only in `/Users/denniskang/work/kb2`.
2. Read `AGENTS.md` and `docs/current-state.md` from a clean local `main`.
3. Identify exactly one relevant Story pipeline task from task metadata and its
   exact initial prompt `story-pipeline-agent S-###`. Treat titles and branch
   names as hints only.
4. Stop without sending a message when the task or host is inaccessible, more
   than one task is plausible, the repository is not on clean `main`, or the
   Story cannot be determined.

## Observe The Task

1. Use task-listing and task-wait tools to obtain the current thread and latest
   turn status.
2. When the thread or latest turn is active or `inProgress`, do nothing. Never
   send a follow-up to a running turn.
3. For an idle, completed, not-loaded, or needs-attention task, read the recent
   turns. Prefer the latest `story_pipeline_checkpoint` block. If it is missing,
   use explicit final text and tool failure evidence; do not infer a material
   decision from silence.
4. Treat delivery as complete only when the task explicitly reports completed
   implementation, required automated tests passing, review completed without
   unresolved findings, and the delivery-close Git evidence required by
   `AGENTS.md`.

## Classify The Pause

Use one normalized reason code and one decision.

| Reason code | Decision | Rule |
| --- | --- | --- |
| `TURN_BUDGET_EXHAUSTED` | `AUTO_CONTINUE` | A safe next phase remains and no decision is requested. |
| `SAFE_REPAIR_CONTINUATION` | `AUTO_CONTINUE` | Story-scoped test or review repair remains within the five-round pipeline bound. |
| `REDUNDANT_APPROVAL_GATE` | `AUTO_CONTINUE` | The pipeline invocation already authorizes the in-scope technical choice. |
| `USER_DECISION_REQUIRED` | `WAIT_USER` | Product behavior, contract scope, or business authority is missing. |
| `CONTRACT_CONFLICT` | `WAIT_USER` | Story evidence conflicts, is stale, or requires scope expansion. |
| `DEPENDENCY_BLOCKED` | `WAIT_USER` | A required dependency is not delivered. |
| `PERMISSION_OR_CREDENTIAL_REQUIRED` | `WAIT_USER` | Interactive approval, secret, credential, or broader access is required. |
| `GIT_OR_OWNERSHIP_CONFLICT` | `WAIT_USER` | Merge conflict, unrelated change, destructive action, or ownership ambiguity exists. |
| `AMBIGUOUS` | `WAIT_USER` | The reason or safe next instruction is not explicit. |
| `DELIVERED` | `DELIVERED` | All delivery-close evidence is explicit. |

Never answer a material user question on the user's behalf. Scheduled runs are
unattended; never work around approval or sandbox boundaries.

## Build A Continuation Instruction

Include the Story, recorded phase, exact bounded next action, and these rules:

- continue from the current checkpoint;
- do not repeat completed phases;
- inspect the Story contract, approved Story design, current diff, tests, and
  run log;
- continue through remaining tests, review, and delivery close;
- stop for a contract gap, scope expansion, unmet dependency, permission or
  credential requirement, conflict, destructive action, or exhausted repair
  bound.

Do not include raw user content, secrets, terminal output, or untrusted text in
the instruction or audit log.

## Record And Dispatch

Use `scripts/watchdog_audit.py` with runtime directory
`.story-pipeline/runtime/watchdog`. The directory is ignored by Git.

1. Run `begin` before sending. Supply the observed task and turn IDs, normalized
   reason, decision, phase, evidence pointer, and exact instruction.
2. Parse its JSON. Send only when `shouldDispatch` is `true`.
3. Send the instruction to the same pipeline task with the task-message tool.
4. Run `finish --dispatch-status sent` after success, or
   `finish --dispatch-status failed` after failure.
5. For `WAIT_USER` and `DELIVERED`, `begin` records the decision and returns
   `shouldDispatch: false`; do not message the pipeline.
6. If `duplicate` or `deferred` is true, do nothing.

Example:

```bash
python3 .codex/skills/story-pipeline-watchdog/scripts/watchdog_audit.py begin \
  --story S-035 --thread-id THREAD --turn-id TURN --message-id MESSAGE \
  --observed-status idle --phase test \
  --reason-code TURN_BUDGET_EXHAUSTED --decision AUTO_CONTINUE \
  --evidence-ref latest-assistant-message \
  --instruction 'Continue story-pipeline-agent S-035 from the recorded test checkpoint.'
```

The script suppresses duplicate decisions, enforces a cooldown, permits at most
three automatic resumes for one reason and six for one Story, and converts an
exhausted retry allowance to `WAIT_USER`.

## Sequencer Handoff

After `DELIVERED`, return to the sequencer's existing Git verification,
reconciliation, next-Story selection, task creation, automation retargeting,
and archival workflow. The watchdog never commits, merges, creates the next
Story task, changes automation configuration, or archives tasks.
