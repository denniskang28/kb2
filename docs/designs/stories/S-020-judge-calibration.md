# Story Design: S-020 - Judge Calibration And Semantic Metrics

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-020`, confirmed 2026-09-11.
- Sources checked: the confirmed Story; `REQ-015`, `REQ-016`; `DES-013`,
  `DES-014`, `DES-016`; `FD-010`; the FEAT-004 routing manifest; and delivered
  S-001, S-016, and S-019 designs, code, contracts, fixtures, Registry, and
  trace schema catalog.
- Material decisions requiring approval: None. The `story-pipeline` invocation
  authorizes the bounded contracts, Artifact schemas, and provider adapter
  boundary below. Calibration thresholds and rubric contents are mandatory,
  explicit inputs, never repository defaults.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add immutable Judge definition, reviewed calibration snapshot, Judge result, calibration report, and semantic metric bindings. Every result carries exact provider/plugin implementation, model, canonical prompt/rubric/configuration digests, case/snapshot IDs, and bounded structured rationale evidence. | Contract round trips and repeated canonical serialization assert all pins; reject loose model/prompt/parameter, case, Evidence, or calibration references and provider response bodies. |
| 2 | Compare every judged calibration case to its reviewed semantic label, calculate agreement plus FP/FN counts and rates for each applicable closed taxonomy slice, and preserve exact failed-case Artifact parents. | Fixtures cover perfect, partial, absent-label, and mixed taxonomy cohorts; aggregate and slice reports assert numerator/denominator, rates, report lineage, and deterministic ordering. |
| 3 | Emit `ELIGIBLE` only when a pinned non-empty calibration policy is satisfied for the full cohort and every selected slice. Missing, invalid, failed, policy-insufficient, definition-mismatched, or drifted calibration yields an advisory semantic metric. | Parameterized failure matrix proves no semantic metric can be hard-gate eligible for absent, invalid, stale, failed-provider, or insufficient calibration. |
| 4 | Bind eligibility to every policy-selected slice, including critical slices, rather than an overall average. A new evaluation using a changed Judge definition is drifted until recalibrated. | A deliberately biased critical-slice fixture has acceptable-looking aggregate agreement but a failed selected slice, producing `INELIGIBLE`; definition/model/prompt/parameter changes produce `DRIFTED`. |
| 5 | Register the initial DeepSeek adapter behind an allowlisted Judge Plugin and its existing external capability readiness. Its unavailable/failed path publishes no Judge result or semantic metric and leaves deterministic reports untouched. | Capability-isolation integration invokes deterministic S-019 metrics with no DeepSeek credential, then asserts a Judge-only invocation fails safely with no output Artifact and core readiness remains healthy. |

## Current Code Findings

- S-016 provides immutable `golden.dataset.snapshot/v1` Artifacts with reviewed
  cases, controlled eight-dimension taxonomy, source/Evidence identity, and
  explicit review provenance. Its `QueryCase` does not contain arbitrary
  semantic labels, so calibration labels need a separate immutable contract;
  changing Golden Dataset authoring semantics is unnecessary.
- S-019 publishes typed deterministic fact, citation, and decision metrics via
  registered Plugin descriptors. `MetricReport/v1` currently rejects every
  method except `deterministic`, deliberately excludes answer/Evidence text,
  and provides the reusable Artifact aggregation path.
- The Registry/Executor already validates closed descriptor ports and
  configuration before a Plugin can publish an Artifact. The trace schema
  catalog is closed, so each new Judge Artifact type must be explicitly
  registered.
- `generator.deepseek@1` demonstrates the existing provider readiness and
  credential boundary: a missing key is a scoped Plugin failure, not a core
  runtime failure. Its request construction is generation-specific and must
  not become the Judge contract.

## Proposed Approach

### Immutable Calibration Inputs

Add `kb2_runtime/evaluation/judges/` with frozen Pydantic contracts and
canonical ASCII JSON identity helpers. Keep human semantic labels in a new
`judge.calibration.snapshot/v1` Artifact, not in mutable dataset rows or the
existing Golden Dataset schema. A calibration snapshot is compiled from one
pinned `golden.dataset.snapshot/v1` and holds a bounded subset of its already
reviewed query cases. Each entry contains:

- the exact case ID, source/Evidence Artifact IDs and digests, taxonomy slices,
  reviewed-label provenance digest, and one human-reviewed label for a named
  semantic rubric;
- the only allowed labels for that rubric, with no automatic label generation;
  the initial binary calibration fixture uses `PASS` / `FAIL`; and
- a bounded reviewer/provenance record over the exact semantic-label digest.

The snapshot also contains one or more closed `JudgeDefinition/v1` values. A
definition pins a semantic metric/rubric ID and revision, provider-neutral
Judge Plugin ID and implementation digest, provider ID, model, a canonical
prompt template and digest, canonical non-secret parameters, allowed output
labels, and bounded input/output/rationale limits. Prompt templates are data,
not a filesystem path, executable code, endpoint, credential, or arbitrary
tool instruction. The definition requires an allowlisted Plugin whose typed
contract accepts only the configured source artifacts.

Publishing a calibration snapshot rechecks that every selected source case is
reviewed and that its case, Evidence, taxonomy, and source digests still agree
with the pinned Golden Dataset snapshot. It rejects duplicate case/rubric
labels, labels outside the definition, missing review provenance, unbounded
content, and an empty cohort. The snapshot parents the Golden Dataset snapshot
and distinct reviewed Evidence Artifacts in stable UUID order. Later dataset
edits or label edits require a new calibration snapshot; neither changes a
prior Artifact.

### Judge Invocation And Semantic Reports

Register a schema-exact `judge.deepseek@1` Plugin, with a provider-neutral
`JudgeConfig` that names a definition from its calibration snapshot and case
ID. It receives, in fixed order, calibration snapshot, reviewed EvidenceSet,
and the relevant S-015 final-response chain (final response plus optional
generated answer and verification result only when the final-response lineage
requires them). It validates every Artifact digest and cross-reference before
forming a request. The provider call receives only the selected case question,
the bounded configured Evidence excerpts, and the response necessary for the
rubric. It never receives a credential in configuration and never records raw
provider request/response content.

`JudgeResult/v1` is published only after a valid typed provider response. It
stores the exact definition/calibration/case identities, provider/model/prompt
and parameter digests, selected label, elapsed time, and bounded rationale
evidence as closed reason codes plus validated citation/evidence IDs. It does
not store query text, answer text, excerpts, hidden reasoning, HTTP payloads,
tokens containing source text, credentials, or endpoint details. Malformed or
unsupported provider output, unavailable capability, timeout, and failed
identity validation are safe invocation failures with no output Artifact.

Extend `MetricReport/v1` compatibly for `owner="judge"` and
`method="llm_judge"`. A Judge report references one `JudgeResult/v1`, its
definition, its calibration report, the frozen policy digest, and the same
case/snapshot/Evidence/final-response bindings used by S-019. Its value is
`1.0` for the selected positive label and `0.0` for the negative label; it
does not reinterpret or replace deterministic fact, citation, or decision
metrics. Existing deterministic validation and serialization, particularly
legacy ingestion bytes, remain unchanged. A Judge report has an explicit
eligibility state: `ELIGIBLE`, `ADVISORY`, `INELIGIBLE`, or `DRIFTED`.
S-021 may consume only `ELIGIBLE` Judge reports when deciding hard-gate
closure; S-020 introduces no gate, score combination, comparison, or default
semantic threshold.

### Calibration Run, Policy, And Drift

Add a small `JudgeCalibrationService` which invokes the definition over each
sorted calibration case through the existing `PluginExecutor`, then publishes
one `JudgeCalibrationReport/v1` through an `EngineKind.EVALUATION` Run. It
does not rerun generation, mutate a dataset, or call a Judge by metric-name
switch. The report parents its calibration snapshot and every JudgeResult in
stable case order.

A separate frozen `CalibrationPolicy/v1` is a required input to calibration
and semantic metric evaluation. It has no implicit thresholds. For every
selected taxonomy slice (including any `criticality=critical` selection), it
explicitly declares a minimum reviewed sample count, minimum agreement, and
maximum false-positive and false-negative rates. The policy digest is pinned
in both report types. The calibration report records overall and per-slice
confusion counts, agreement, and FP/FN rates, plus a status for each required
slice. A policy-selected slice with too few labels or a failed bound makes the
whole report `INELIGIBLE`; aggregate agreement cannot override it.

Calibration is `ELIGIBLE` only when all calls succeeded, the snapshot is
complete, every policy-selected slice is represented and passes, and the exact
Judge definition digest equals the definition requested for semantic scoring.
It is `ADVISORY` for missing/invalid/failed/insufficient calibration and
`DRIFTED` when any provider plugin implementation, provider, model, prompt,
parameters, rubric revision, or label/schema identity differs. "Stale" in
this Story therefore means an identity mismatch, not an invented calendar-age
window. A caller must calibrate a changed definition again before it can close
a hard gate. Policies are supplied by representative calibration work and
fixtures; the repository establishes no acceptable numeric values.

The common aggregation service will gain a Judge-compatible identity key that
includes definition, calibration report, policy, and semantic metric IDs. It
aggregates only reports with identical pins and taxonomy; it retains
advisory/ineligible/drifted state counts rather than treating them as a zero or
silently averaging them away.

## Relevant Impacts

- **Data and compatibility:** Adds `judge.calibration.snapshot/v1`,
  `judge.result/v1`, and `judge.calibration.report/v1` to the trace schema
  catalog and makes an additive, backward-compatible `MetricReport/v1` /
  `MetricAggregate/v1` extension. No catalog migration, source-data backfill,
  or change to S-016 Dataset authoring is needed.
- **Provider boundary:** DeepSeek is one allowlisted adapter selected by a
  pinned definition. Replacement providers implement the same typed Judge
  Plugin ports and conformance suite; no DeepSeek model or endpoint is baked
  into the semantic metric contract.
- **Reproducibility and observability:** Artifact lineage pins the Dataset,
  reviewed Evidence, final response, definition, policy, Judge results, and
  calibration report. Reports expose bounded label/count/reason-code evidence
  sufficient to navigate a failed slice without retaining sensitive payloads.
- **Security:** All definitions/policies are closed declarative JSON with
  bounds. Provider credentials stay in the configured secret boundary; raw
  provider data, prompts with secrets, source bodies, and arbitrary executable
  content are rejected or omitted from persisted outputs.

## Alternatives And Risks

- Extending `QueryCase` with free-form semantic truth was rejected. It would
  broaden S-016's reviewed Golden Dataset contract and allow semantics to be
  introduced without a rubric-specific reviewed label or calibration identity.
- Treating a calendar duration as staleness was rejected because no supported
  freshness threshold exists. Exact definition identity detects meaningful
  provider/model/prompt/parameter drift without inventing a time limit.
- A single aggregate eligibility boolean was rejected because it could hide
  the explicitly required critical-slice failure. The report keeps every
  policy-selected slice and fails eligibility closed.
- Persisting free-form model rationale or HTTP responses was rejected because
  it weakens the bounded evidence and credential/source-data boundary. Closed
  reason codes and validated Evidence identities retain diagnostic value.
- External Judge responses are nondeterministic. Reproducibility here means
  replayable inputs, definitions, policy, case identities, and recorded
  results, not byte-identical re-execution. A changed output is observable as
  a new result and calibration comparison, never silently substituted.

## Test Strategy

- Add `tests/contract/test_judge_calibration.py` for definition/policy/label
  bounds, canonical bytes/digests, calibration snapshot source validation,
  artifact schema registration, result/report shape, legacy deterministic
  metric-byte compatibility, and provider-neutral descriptor ports.
- Add calibration fixtures for reviewed correct/incorrect semantic labels,
  multiple document/question slices, a critical slice, incomplete labels,
  and a deliberately biased Judge result whose total agreement is acceptable
  while its critical slice fails its explicit policy.
- Add integration coverage with a fake allowlisted Judge adapter through the
  real Registry/Executor and trace services. Assert stable parent order,
  exact pin propagation, per-slice agreement/FP/FN arithmetic, advisory and
  drift state propagation, and no source/Dataset mutation.
- Exercise missing DeepSeek credential, capability unavailability, timeout,
  malformed label/rationale, forged Artifact/digest, changed model/prompt/
  parameter/plugin digest, missing policy slice, and insufficient sample
  paths. Assert no Judge-dependent output publishes and pre-existing S-019
  deterministic metric reports remain valid and unchanged.
- Run focused Judge, dataset, answer-metric, Registry/Executor, generation,
  trace, and aggregation tests, then the full suite. Run Docker persistence
  coverage when Compose can start; otherwise preserve the existing
  environment-blocked evidence rather than treating it as a product failure.

## Implementation Checklist

- [ ] Add frozen Judge definition, reviewed calibration snapshot, calibration
  policy, result/report/eligibility contracts, canonical serializers, and
  trace schema registrations.
- [ ] Implement the provider-neutral Judge Plugin port, initial DeepSeek
  adapter, bounded provider-response sanitization, and scoped capability
  failure behavior.
- [ ] Add calibration service/run publication, slice-aware confusion
  calculation, definition-identity drift detection, and fail-closed policy
  eligibility.
- [ ] Extend common metric contracts/aggregation compatibly for Judge report
  pins and advisory/ineligible/drifted state accounting; register descriptors
  and a typed service wrapper.
- [ ] Add contract/integration fixtures and tests for every acceptance and
  failure path, then run focused and full regression verification.

## Open Questions

None. Numeric policy values and concrete rubric content deliberately remain
caller-supplied, reviewed calibration inputs; this Story provides their typed,
reproducible, and fail-closed execution contract.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-020,
  direct anchors, and delivered S-001/S-016/S-019 implementation contracts.
