# Test Report

## Story And Designs

- Story: `docs/stories/S-001-local-runtime-and-readiness.md`
- Approved amended design:
  `docs/designs/stories/S-001-local-runtime-and-readiness.md`
- Contract amendment: external DeepSeek generation provider confirmed
  2026-09-11; credential-independent local core readiness supersedes the prior
  local Ollama requirement.
- Branch: `feature/s-001-local-runtime-and-readiness`

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | No-key base-stack startup through the shared CLI; core readiness; no fixture service; forbidden external-probe contract | Contract / integration | Pass: core reached ready without a model key; `embedding.default`, `generation.default`, and `generation.high_precision` were `not_configured` |
| 2 | Component/capability health matrix; induced PostgreSQL, Worker heartbeat, Artifact probe, model, and provider failures; stable nonzero results; sanitization | Contract / integration / security | Pass |
| 3 | Process-only liveness, core-only readiness, no-key required generation, configured-but-unrequested `not_probed`, exact requested-model inventory, provider recovery | Contract / integration | Pass |
| 4 | Lexical state-path and ownership-marker validation, default/custom symlink rejection, unowned/retargeted state rejection, scoped lifecycle, persistence, isolation, and explicit clean | Contract / integration | Pass |
| 5 | Exact trusted endpoint, redirects/proxies disabled, file-mounted secrets, file modes, source/config scan, process/container/image/log/health/history/evidence redaction | Security / contract / integration | Pass |
| 6 | Unique disposable projects using the same CLI with base, test, and deterministic DeepSeek overlays; all required-component and provider failures/recovery; cleanup | Integration | Pass |

## Tests Added Or Updated

- Contract tests cover no-key core readiness without any DeepSeek probe,
  required generation without a key, one exact authenticated `/models`
  inventory, model-ID matching, provider error sanitization, and core readiness
  with a configured key but no external call.
- CLI/security tests cover empty and populated DeepSeek key-file handling,
  mode `0600`, invalid key-file states, key absence from command/environment
  values, working-tree credential scans, and core-only startup polling.
- Cleanup contract tests reject missing, malformed, permission-invalid,
  symlinked, non-regular, unowned, mismatched, and post-Compose-retargeted state
  ownership markers before any unsafe removal.
- Real `main -> parser -> options_from` regressions cover a default state-root
  leaf symlink plus custom parent and leaf symlinks. Each returns only
  `STATE_ROOT_INVALID`, leaves the external target untouched and empty, creates
  no ownership marker, and proves Compose was not invoked.
- Provider security tests allow only `https://api.deepseek.com` outside the
  exact test environment and only `http://deepseek-fixture:8080` in test;
  redirects and inherited proxy configuration are disabled.
- The integration lifecycle now starts the base no-key stack first, adds the
  deterministic provider only through `compose.deepseek-test.yaml`, exercises
  configured-but-unrequested zero-request behavior, one shared `/models` probe
  for explicitly requested generation, both model IDs, missing-model and
  provider failure/recovery, and proves the provider request log contains only
  authenticated `/models` requests. No chat, completions, or generation
  request is issued.
- Added integration failure/recovery coverage for `worker.default`: explicitly
  stop the Worker, poll to `HEARTBEAT_STALE`, restart it, and poll back to core
  readiness.
- Added integration failure/recovery coverage for `artifact.local`: use a root
  test exec only to remove write permission from the reserved `.health`
  directory, assert a sanitized required-component failure, restore the mode
  in a local `finally`, and poll back to readiness.
- Existing restart, persistence, required PostgreSQL failure/recovery,
  second-project isolation, image/runtime inspection, and cleanup regressions
  remain active.

## Commands And Results

- `/Users/denniskang/anaconda3/bin/python -m pytest -m 'not integration' tests/contract`
  - `65 passed in 0.28s`.
- Base Compose render using an empty generated DeepSeek key file:
  `docker compose ... --file deploy/local/compose.yaml config --quiet`
  - Passed.
- Deterministic-provider render:
  `docker compose ... --file deploy/local/compose.yaml --file deploy/local/compose.deepseek-test.yaml config --quiet`
  - Passed.
- `PYTHONPYCACHEPREFIX=/tmp/kb2-s001-lexical-pycache /Users/denniskang/anaconda3/bin/python -m compileall -q src scripts tests`
  - Passed.
- `git diff --check`
  - Passed.
- `make test PYTHON=/Users/denniskang/anaconda3/bin/python`
  - `65 passed in 0.23s`.
  - Harness passed: `REQ=17 DES=16 FEAT=5 FD=11 S=3`.
- `/Users/denniskang/anaconda3/bin/python -m pytest -m integration tests/integration/test_local_runtime.py -vv`
  - `1 passed in 106.84s`.
  - The same runtime CLI completed base no-key startup, health, stop, restart,
    configured-provider startup, PostgreSQL/Worker/Artifact/provider/model
    failures and recovery, second-project isolation, and cleanup.
- Independent post-test Docker/state inventory
  - No `kb2-it-*` containers, volumes, networks, generated state directories,
    or secret files remained.

## Visual Evidence

| AC | UI Anchor | Capture Conditions | Baseline | Diff Or Review Evidence | Result |
|---|---|---|---|---|---|
| N/A | None | S-001 has no UI or Visual Acceptance Matrix | None | None required | N/A |

## Visual Baseline Changes

None.

## Build Status

Pass. The base application image built from its pinned Python 3.12 base, and
both the core-only and deterministic-provider Compose configurations rendered
and executed successfully. The base stack contains no Ollama or other model
service.

## Test Status

Pass. S-001 is signed off against the amended 2026-09-11 Story and approved
design. All six acceptance criteria have automated evidence.

## Failure Classification

No current implementation, test, environment, Story, design, architecture, or
dependency failure remains.

Historical results that do not affect the current verdict:

- The earlier raw-bind API-port preflight defect was repaired with an active
  listener probe; focused tests and repeated complete lifecycle runs pass.
- The earlier Ollama image-download environment blocker belonged to the
  superseded local-model contract. Ollama is absent from the amended runtime
  and is not required evidence for this report.

Review findings resolved in this final round:

- State cleanup now requires an exact, private, regular ownership marker and
  revalidates it after Compose teardown; retargeting and unowned paths are
  rejected by focused tests.
- CLI parsing preserves the lexical state path until symlink-component checks
  complete. Default-leaf and custom parent/leaf symlink attacks are rejected
  before state initialization, marker creation, or Compose invocation, and
  their external targets remain untouched.
- DeepSeek keys are confined to a closed endpoint policy; redirects and proxy
  inheritance are disabled and tested.
- A configured key alone performs no external request. Plain health reports
  generation as `not_probed`; an explicit generation requirement authorizes
  one shared `/models` probe and leaves unrequested generation `not_probed`.
- Worker heartbeat and Artifact probe failure/recovery now have real Compose
  integration evidence in addition to PostgreSQL/provider coverage.

## Feedback For Development

None.

## Remaining Gaps

- Tests deliberately do not call real DeepSeek and use no real key. The fixture
  verifies only this runtime's minimal OpenAI-compatible `/models` adapter,
  exact model matching, authentication placement, and failure semantics; it is
  not DeepSeek conformance, generation quality, or billing evidence.
- Host-side tests used the available Python 3.11.3 environment. The actual
  application image and successful Docker lifecycle use the pinned Python 3.12
  runtime required by the design.

## Regression Coverage

Coverage includes health schema and ordering, liveness/readiness separation,
credential-independent core startup, unconfigured embedding and generation,
configured-but-unrequested generation, selected capability gating, unknown
capabilities, exact DeepSeek model IDs, single `/models` inventory behavior,
trusted endpoint/redirect/proxy controls, provider and probe sanitization,
secret and cleanup-marker validation, scoped Compose operations, restart
persistence, lexical state-path/default/custom symlink rejection,
PostgreSQL/Worker/Artifact/provider failure and recovery, project isolation,
localhost-only API exposure, non-root application execution, absence of Docker
socket mounts, image/history/log/health redaction, and deterministic cleanup.
