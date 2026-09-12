# Test Report

## Story And Designs

- Story: `S-022: Workbench Shell And Runtime Overview`
- Approved design: `docs/designs/stories/S-022-workbench-shell-and-overview.md`
- Scope verified: bounded read-only overview projection, static workbench shell,
  keyboard routing, runtime/capability presentation, and responsive navigation.

## AC-to-Test Mapping

| AC | Test | Level | Result |
|---|---|---|---|
| 1 | Eight static routes/assets, Chinese entry point, semantic links, URL-derived bounded workspace preservation | API/source/browser | Pass after repair |
| 2 | Non-probing health request and separate core/optional/plugin projections | API contract/source | Pass |
| 3 | Persisted Run projection, active count, safe failed-Run action, bounded comparison projection, malformed/digest-mismatch comparison filtering | API contract | Pass after repair |
| 4 | Empty/dependency/refresh-error rendering, fixed shell, loading skeleton source path | Browser/source | Pass for error/empty/loading structure |
| 5 | 1440x900 and 644x900 scroll-width checks; drawer open/closed and keyboard focus loop | Browser responsive | Pass |
| 6 | UI-013 neutral ruled/square-control/status token implementation and focus/hover CSS | Source/browser | Pass for exercised error and drawer states; populated-state evidence pending |

## Tests Added Or Updated

- `tests/contract/test_workbench.py` covers route asset serving, non-probing
  overview health, safe bounded persisted Run projection, verified comparison
  output, and malformed/digest-mismatched comparison filtering.
- `tests/contract/test_workbench_browser.py` starts FastAPI and captures the
  supplied error shell at desktop and narrow viewports when
  `KB2_BROWSER_TESTS=1`. Its test-only `fixture_app` serves implementation
  static assets byte-for-byte with isolated populated/dependency/loading API
  response fixtures; no production endpoint has synthetic defaults.
- The browser regression now launches `fixture_app` itself for populated,
  dependency-unavailable, and delayed-loading response states; it validates the
  live fixture payload before capturing each desktop and narrow shell.

## Commands And Results

| Command | Result |
|---|---|
| `pytest -q tests/contract/test_workbench.py` | Pass: `5 passed in 0.33s` after comparison-digest repair |
| `pytest -q tests/contract/test_workbench.py tests/contract/test_health.py tests/contract/test_trace_contracts.py tests/contract/test_plugins.py` | Pass: `45 passed in 0.57s` before the final added comparison regression; the final S-022-only rerun above is green |
| `KB2_BROWSER_TESTS=1 pytest -q -s tests/contract/test_workbench_browser.py` | Environment-limited: isolated Chrome produced a valid desktop `1440x900` PNG (57 KB) but did not terminate before command transport timeout, preventing its pytest terminal result and second CLI capture. |
| `pytest -q tests/contract/test_workbench.py tests/contract/test_workbench_browser.py` | Pass: `5 passed, 1 skipped`; browser execution remains opt-in because its Chrome process does not reliably exit. |
| `KB2_BROWSER_TESTS=1 pytest -q -s tests/contract/test_workbench_browser.py` | Pass: `3 passed in 21.00s`; isolated fixture app was started for populated, dependency-unavailable, and delayed-loading API responses, each captured at `1440x900` and `644x900`. |
| `pytest -q tests/contract/test_workbench.py tests/contract/test_health.py` | Pass: `19 passed in 0.36s`; includes workspace-at-boot, container-runner readiness, and invalid comparison response regressions. |
| `KB2_BROWSER_TESTS=1 pytest -q -s tests/contract/test_workbench_browser.py` (repair 6 rerun) | Pass: `3 passed in 21.50s`; fixture-backed populated, dependency, and loading browser capture remains green after drawer-inert repair. |
| `pytest -q` | Environment-running/blocked by existing Docker Compose lifecycle startup; non-Docker progress completed before Compose stalled. No S-022 assertion failure was observed from this command. |

## Visual Evidence

| AC | UI Anchor | Capture Conditions | Baseline | Diff Or Review Evidence | Result |
|---|---|---|---|---|---|
| 5 | UI-001 | Isolated headless Chrome, `1440x900`; zh-CN, `workspace=local_demo`, refresh-error from unavailable local overview API; browser-default DPR; no animations/masks | No approved raster baseline | Valid `1440x900` 57 KB PNG: persistent 220px sidebar, compact context bar, fixed commands, no visual overlap | Pass |
| 5 | UI-001 | In-app Chromium, `644x900`, browser-default DPR, zh-CN, same fixture; drawer closed then opened | No approved raster baseline | Closed/open `scrollWidth=644`; drawer width `220px`; first-link Shift+Tab focuses last link and last-link Tab focuses first; Escape closes and returns focus to `打开导航`; breadcrumb preserves `local_demo` | Pass |
| 4, 6 | UI-002 | Isolated test-only fixture API, Chrome `1440x900`, populated and dependency-unavailable; zh-CN, browser-default DPR, no animation/masks | No approved raster baseline | `/tmp/s022-populated-1440.png` (63 KB) and `/tmp/s022-dependency-final-1440.png` (64 KB) retain command row, status groups, failed-Run triage and comparisons without layout shift | Pass |
| 4 | UI-002 | Test-only loading API delays response; CDP inspected before response completion | No approved raster baseline | DOM evidence: `skeleton=true`, `正在加载运行时状态…`, stable overview landmarks. CDP page target exposed an unusable `1px` viewport, so its 87-byte capture is excluded from visual review. | Pass structural/loading; visual capture environment-limited |
| 6 | UI-013 | Fixture-backed populated desktop and narrow `644x900`; system fallback font because Archivo is not bundled; no dynamic masks | No approved raster baseline | `/tmp/s022-populated-644.png` (46 KB) confirms narrow density/no page overlap. Desktop captures confirm neutral rules, square controls, red primary action, teal/amber semantic states | Pass |

## Visual Baseline Changes

None.

## Build Status

Python focused contract and regression surface passes. No JavaScript build is
required by the approved dependency-free static-shell design.

## Test Status

Pass for the executable S-022 API/service and focused browser regression
surface. The comparison Artifact digest binding is verified. Fixture-backed
populated, dependency-unavailable, loading, desktop, and narrow response paths
are exercised by the actual browser test process.

## Failure Classification

- **Resolved implementation defect:** `WorkbenchOverviewService._comparison`
  now validates SHA-256 bytes against `content_digest`; valid content is
  retained and malformed/digest-mismatched records are skipped by regression.
- **Resolved test defect:** the original browser test declared `fixture_app`
  but launched the production app. It now launches the test-only fixture
  transport and verifies populated, dependency-unavailable, and loading API
  responses before browser capture.
- **Environment limitation:** the full suite reaches existing Docker Compose
  lifecycle startup/build, which remains stalled. This is separate from the
  focused S-022 failures and is not treated as a pass.

## Feedback For Development

No remaining S-022 implementation defect. Add executable browser coverage for
all eight keyboard activations and command URL routing in a browser automation
runtime with interaction locators; the current browser process validates each
fixture state visually, while eight route availability remains contract-tested.

## Remaining Gaps

- The implementation has no approved raster baseline, so no baseline diff was
  created. Capture artifacts created in pytest temporary paths are not retained
  after the test run; the manually retained fixture captures remain documented
  in the Visual Evidence table.
- Complete `pytest -q` where Docker Compose can finish startup and report its
  terminal summary.

## Regression Coverage

Focused coverage ran the S-001 health, S-002 trace, S-003 Plugin, and S-022
contract surfaces unchanged. The complete suite was attempted; its Docker
lifecycle tail remains environment-blocked.
