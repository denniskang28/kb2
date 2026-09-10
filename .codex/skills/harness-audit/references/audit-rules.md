# Lean Harness Audit Rules

## Product Analysis

- Every confirmed product fact has a user or approved-source basis.
- PRD remains concise and phased; technical detail is routed to DES records.
- Confirmed DES records state strength and applicability.
- Prototype behavior is not treated as adopted without confirmation.
- Blocking questions and contradictions are visible.

## Feature Routing

- Every listed REQ/DES/UI/FD anchor exists and belongs in the Feature boundary.
- No detailed behavior was invented to make the Feature look complete.
- Cross-Story rules are confirmed and concise.
- Optional Feature Design is recommended only for a material shared ambiguity.

## Story Readiness

- The Context Manifest contains only relevant, current, confirmed anchors.
- Inherited requirements and constraints make the Story self-contained.
- Compiled statements do not contradict their sources.
- Scope is coherent and ACs are observable and testable.
- Exact relevant UI locations are included when UI behavior matters.
- No material product decision is left for coding.
- Missing irrelevant UI, API, data, security, failure, or NFR sections are not
  findings.

## Severity

- Critical: unsafe authority, privacy, destructive, tenant, credential, or
  contradictory binding behavior.
- Major: unsupported accepted fact, missing required source behavior, stale
  contract, material unresolved question, or untestable AC.
- Minor: navigation, wording, or non-blocking provenance defect.
