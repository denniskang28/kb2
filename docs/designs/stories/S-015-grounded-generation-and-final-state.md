# Story Design: S-015 - Grounded Generation And Final-State Validation

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-015`, confirmed 2026-09-11.
- Sources checked: the Story contract; direct `FD-005` and `FD-006` records;
  `DES-012` and `DES-016`; S-011 and S-014 designs; existing Query Profile,
  Evidence, Plugin Registry/Executor, trace, capability, and test contracts.
- Material decisions requiring approval: None. The pipeline invocation
  authorizes the bounded provider, prompt, verification, and state choices
  below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add typed generated-answer, verification, and final-response Artifacts. A DeepSeek adapter receives only the question/session Artifact and a bounded rendered `EvidenceSet`; its closed config pins capability, model, prompt revision, and decoding bounds. | Provider mock asserts the request whitelist, canonical identities, and no credential in Artifacts, metrics, traces, or errors. |
| 2 | Parse a constrained structured answer with answer-visible citation keys; deterministic verification resolves every cited/required key against the input Evidence, checks support/forbidden content/answerability, and makes `ANSWERED` contingent on pass. | Supported, omitted, forged, duplicate, and unsupported-citation fixtures prove valid `ANSWERED` and rejection of every invalid claim/citation path. |
| 3 | Add a fixed-order query executor plus final-state plugin to produce one `FinalResponse/v1` with `ANSWERED`, `CLARIFICATION_REQUIRED`, `ABSTAINED`, or `FAILED`; execute bounded repair from verifier failures. | Contract fixtures cover supported, ambiguous, insufficient, invalid citation, provider failure, repair success, and repair exhaustion with terminal trace assertions. |
| 4 | Repair reinvokes generation with the same question/session and Evidence binding plus the previous verification result, up to the compiled `max_attempts`; no retrieval, index, or context input is reachable from the loop. | Attempt count, identical Evidence ID/digest, unchanged upstream Artifacts, and no extra retrieval/context attempts are asserted for repair paths. |
| 5 | Register DeepSeek generation descriptors with their existing `generation.*` capability requirement; resolve capability availability before invoking the plan and return a safe `FAILED` final response/action only for plans that declare generation. | No-key/configuration, unavailable model, provider timeout, and provider error tests assert safe diagnostics and unchanged core readiness. |
| 6 | Replace S-011 fixture-only final/generation descriptors with the real typed descriptors and execute at least `text-hybrid` and `high-precision-fact` against one immutable indexed Artifact. | End-to-end fixed-index tests compare plan/Artifact identities, stage attribution, and inputs before/after both Profile runs. |

## Current Code Findings

- S-011 compiles a fixed, typed stage order and only permits a repair stage
  after verification, with `max_attempts` in `1..3`. Its fixtures currently end
  in the placeholder `query.final@1`; no Query execution package exists.
- S-014 supplies an immutable `EvidenceSet/v1`: unique citation keys map to
  bounded excerpts, exact locators, source/index identity, contributor facts,
  and an explicit shortage record. It intentionally has no retrieval call
  path.
- `PluginExecutor` already records each invocation attempt, validates exact
  schema ports/configuration, pins descriptor/configuration identities in
  Artifact manifests, preserves parent Artifact lineage, and publishes only
  after the plugin finishes successfully.
- S-001's capability catalog already distinguishes `generation.default` and
  `generation.high_precision`, uses allowlisted DeepSeek URLs and key files,
  and sanitizes readiness failures. It has only a `/models` probe, not a chat
  completion adapter.
- Trace supports Evidence but has no schemas for generated/verified/final query
  results. Existing query fixtures can compile but cannot yet run.

## Proposed Approach

### Query Artifact Contracts

Add `kb2_runtime/generation/` for provider-neutral generation and verification
contracts, deterministic serializers, local deterministic verifier/finalizer,
and Plugin Registry adapters. Add a small `kb2_runtime/query_engine/` that
executes one previously compiled/resolved Query plan; it does not parse or
mutate Profiles.

Use these bounded schemas:

- `generated.answer/v1`: `answer_id`, source `evidence_set_id` and Artifact
  binding, question/session Artifact binding, resolved generation plugin,
  implementation/configuration identity, bounded answer text, ordered unique
  citation keys, and attempt number. Provider raw request/response, key, URL,
  token logprobs, and hidden reasoning are excluded.
- `verification.result/v1`: `verification_id`, generated-answer/evidence
  bindings, outcome (`pass`, `repairable`, `clarification_required`,
  `abstain`, or `failed`), bounded reason/failure codes, resolved and missing
  citation keys, and the active answerability result. It contains no alternate
  evidence or unbounded provider diagnostics.
- `final.response/v1`: one terminal state, optional bounded answer/citations
  only for `ANSWERED`, a safe user action for non-answered states, and bindings
  to Evidence plus the terminal verification/generation artifacts. It has a
  deterministic ID derived from those complete fields.

All IDs and canonical bytes use compact sorted ASCII JSON and SHA-256 inputs.
The Artifact schemas are registered with trace. Pydantic validators require
finite/bounded data, compatible bindings, unique citation keys, and prohibit
an answer payload for every non-`ANSWERED` terminal state. No database migration
is needed: Artifacts are already schema/versioned and persisted generically.

### Allowlisted Generation And Verification Plugins

Register two real DeepSeek generation descriptors, such as
`generator.deepseek@1` and `generator.deepseek-high-precision@1`, using the
in-process runner and respectively requiring `generation.default` and
`generation.high_precision`. Their frozen configuration has only an exact
allowed model for that capability, a repository-owned prompt revision label,
`max_answer_chars` (at most 4096), a low bounded output token limit, and a
closed temperature range. Model/prompt/parameter values are therefore included
in the compiled Query plan and Artifact configuration digest. A profile cannot
supply a URL, credential, arbitrary prompt, command, or provider payload.

The provider-neutral port accepts `opaque.bytes/v1` question/session input and
`evidence.set/v1`. It renders a repository-owned structured request with only:
the declared question/session bytes interpreted as bounded UTF-8, each
Evidence item's citation key and excerpt, and instructions to return a JSON
object containing `answer` and `citation_keys`. The adapter validates the
trusted DeepSeek base URL before reading its secret, uses an `httpx` client
with `trust_env=False`, redirects disabled, and the descriptor deadline. It
maps authentication, network, timeout, HTTP, and malformed response failures
to stable `PluginErrorCode` values and never surfaces provider bodies.

The verifier is a separate allowlisted local plugin with closed Profile rules:
minimum evidence items, required citation policy (`all_claims` for the initial
profiles), optional allowed/forbidden phrase lists, and closed answerability
policy. It deterministically rejects empty/oversized answers, insufficient
Evidence, citations absent from Evidence, duplicate citations, missing required
citations, and configured forbidden content. Initial lexical support is
conservative: every answer sentence containing a citation must share a
normalized non-stopword token with at least one cited Evidence excerpt; any
unsupported sentence becomes a repairable failure. The verifier never uses
model knowledge or fetches content. This intentionally narrow, transparent
check is the S-015 baseline; later evaluation Stories calibrate thresholds.

`query.final-state@1` consumes Evidence plus verification (and generated
answer when present). It maps validation outcomes deterministically:

- pass -> `ANSWERED`, only with the validated answer and citations;
- ambiguous answerability -> `CLARIFICATION_REQUIRED` with a fixed safe action;
- insufficient Evidence or explicit non-answerability -> `ABSTAINED`;
- provider, configuration, timeout, malformed output, or exhausted repair ->
  `FAILED` with a safe retry/configuration action.

Register explicit generation input/response errors alongside existing plugin
codes. Plugin metrics/signals expose bounded attempt count, answer length,
citation count, validation outcome, repair reason, and duration; they do not
expose question text, excerpts, keys, headers, or provider text.

### Bounded Execution And Repair

`QueryEngine.execute(resolution, question_artifact, executor)` verifies the
compiled Search Artifact binding against the supplied Artifact manifest, creates
a `query` Run from the frozen resolved plan, then follows the plan's declared
stage order. It maps named Profile bindings to prior output Artifact IDs and
delegates every Plugin stage to `PluginExecutor`; it has no Plugin-ID dispatch
or dynamic graph capability.

The executor treats `repair` as the one compiler-authorized loop. On a
repairable verification result it invokes the declared generation plugin again
with the original question/session Artifact, the exact prior Evidence Artifact,
and the bounded verification Artifact. It then verifies the replacement answer.
There are at most the compiled `max_attempts` repair invocations (and one
initial generation). It records distinct stage keys/attempts and explicit
parent bindings for every generation/verification Artifact. The loop cannot
bind `search.index`, retrieve/fuse/rerank/context output, or invoke a stage not
already in the compiled plan. A final-state stage runs exactly once after the
terminal verification outcome; the Run success indicates engine completion,
not that the final response is `ANSWERED`.

Capability availability is checked through the Registry before the relevant
generation stage. A missing DeepSeek key, unavailable exact model, or provider
failure affects only a selected plan containing that descriptor. The engine
records the safe failed generation attempt and emits `FAILED` final state; it
does not call `/health/ready`, alter global capability status, or make an
unconfigured profile fail.

Update the five baseline Query Profile fixtures to select real generation,
verification, optional bounded repair, and final-state ports as appropriate.
`high-precision-fact` uses the high-precision capability plus strict
verification; `text-hybrid` uses the default capability. Retain existing
retrieval/context configuration and select deterministic fixtures/providers in
tests, so fixed Artifact behavior remains reproducible without external
credentials.

## Relevant Impacts

- **API/data:** Adds internal Artifact schemas, plugin descriptors, a
  programmatic Query Engine entry point, and real fixture stage bindings. No
  HTTP endpoint or UI is introduced.
- **Lineage/reproducibility:** Each result binds to one frozen question/session,
  Evidence, Search Artifact through existing Evidence lineage, plan digest,
  provider/model/prompt/parameter identity, and stage attempts. Repair records
  the identical Evidence binding for every attempt.
- **Security:** Credentials remain in the configured secret file and are read
  only inside the trusted provider adapter. Inputs/outputs are bounded; provider
  bodies, headers, secret values, arbitrary prompts, endpoint overrides, and
  general-knowledge retrieval are excluded from traces and diagnostics.
- **Compatibility:** Existing Evidence and retrieval Artifacts are read-only
  inputs. Profile fixtures intentionally change from compiler-only placeholders
  to runnable real typed stages. No persisted payload migration is necessary.

## Alternatives And Risks

- Treating a provider's prose response as an answer was rejected: structured
  output and local validation are needed to prove citation binding and safely
  classify malformed responses.
- Combining generation, verification, repair, and finalization in one plugin
  was rejected because it would hide attempt lineage and make the compiler's
  repair bound unenforceable.
- Giving repair direct search/index/context ports was rejected: it would permit
  undeclared retrieval or widened context. The loop gets the same Evidence
  Artifact only.
- Lexical support checking is deliberately conservative and may abstain on
  well-supported paraphrases. That false-negative tradeoff preserves grounded
  behavior for the initial executable baseline; S-019/S-020 own evaluation and
  calibration rather than silently weakening this gate.

## Test Strategy

- Add generation contract tests for canonical IDs/bytes, schema bounds,
  compatible binding validation, citation uniqueness, final-state invariants,
  and rejection of provider/credential-like content in declarative config or
  persisted metadata.
- Use `httpx.MockTransport` and a fake capability checker to verify DeepSeek
  request method/path/headers/body whitelist, trusted URL enforcement, timeout
  behavior, malformed/HTTP response sanitization, and no-secret traces.
- Add verifier fixtures for supported, ambiguous, insufficient, invalid
  citation, forbidden content, repairable unsupported claim, and non-answerable
  outcomes. Assert exact final states and absence of an answer for non-answered
  results.
- Add Query Engine integration coverage with fake deterministic generators:
  successful answer, repair success, repair exhaustion, provider failure,
  cancellation, and no-publication failure. Assert bounded attempts, stage
  trace ordering, fixed Evidence binding, and no added retrieval/context stage.
- Recompile and execute `text-hybrid` and `high-precision-fact` over the same
  fixture index twice; assert input/index immutability, different pinned Profile
  identities where configured, and preserved retrieval/fusion/context stage
  attribution. Run focused generation/query/evidence/health tests and the full
  project regression suite.

## Implementation Checklist

- [ ] Add generation, verification, and final-response contracts, canonical
  serialization/identity, trace schema registration, and safe error codes.
- [ ] Implement the provider-neutral DeepSeek adapter, local verifier/finalizer,
  registry descriptors, capabilities, metrics, and sanitization.
- [ ] Implement the fixed-plan Query Engine and bounded repair execution.
- [ ] Update Query Profile descriptors/fixtures and add deterministic provider
  fakes plus contract/integration/end-to-end coverage.
- [ ] Run focused acceptance/regression suites and the full test suite.

## Open Questions

None. Initial prompt revision, maximum answer length, and verifier policy are
closed Profile configuration and will be concrete, pinned values in the
implementation; calibration remains owned by later evaluation Stories.

## Approval

Approved by the `story-pipeline` invocation for immediate implementation.

## Change History

- **2026-09-12:** Created just-in-time technical design from confirmed S-015
  and its direct code/contracts.
