# Story Pipeline Run Log Template

Create this file as `docs/run-logs/<YYYY-MM-DDTHHMMSS>-<story-id>.md` after the
readiness and delivery-branch gates pass, using the local delivery-start time
and lowercase Story ID, such as `2026-07-27T191733-s-070.md`. Add one round for
every delegated design, development, test, review, and repair action; never
summarize an entire delivery as one `pipeline` round.

```md
# Pipeline Run: RUN-ID

## Metadata
| Field | Value |
|---|---|
| Stories | |
| Started | |
| Branch | |
| Status | |

## Gates
| Gate | Evidence | Result |
|---|---|---|

## Rounds
| Round | Agent | Action | Build | Tests | Failure Type | Return Target |
|---:|---|---|---|---|---|---|

## AC Evidence
| AC | Code | Test | Result |
|---|---|---|---|

## Review
## Documentation Reconciliation
## Delivery Close
| Field | Value |
|---|---|
| Delivery commit | |
| Fast-forwarded into local main | |
| Reconciliation commit | Not required / |
| Final local main HEAD | |
## Final Status
```

Write `Final Status` before the delivery commit only as a verification result;
do not claim that the merge has occurred. After the fast-forward merge, record
the delivery-close facts with one normal documentation-only commit on local
`main` when an update is needed. Never amend or rewrite the merged delivery
commit to add this information.
