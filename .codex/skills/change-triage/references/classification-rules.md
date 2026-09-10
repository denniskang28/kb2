# Lean Change Classification

| Evidence | Default Owner And Path |
|---|---|
| Code violates clear Story AC | Story pipeline repair |
| Story contract is unclear or incomplete | Story planning and reconfirmation |
| Shared behavior affects multiple Stories | Feature shared rule or optional Feature design |
| Product scope or business rule changes | `$update-prd` |
| Confirmed architecture/data/API/algorithm direction changes | `$core-design-capture`, then affected Story recompilation |
| Prototype visual guidance changes only | `$partial-ui-reference-intake` |
| Adopted UI behavior changes | UI intake plus Story or PRD update as classified |
| Observable behavior is unchanged | Technical design or code refactor |
| Evidence conflicts or is insufficient | Investigation only |

Never treat prototype implementation, AI suggestion, client-provided identity,
or request data as approved authority.
