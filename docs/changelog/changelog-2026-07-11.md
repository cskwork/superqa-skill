# Changelog 2026-07-11 - SuperQA v0.3.0

## Visual regression (screenshot baseline diff)

`superqa baseline <scenario|--all>` accepts the latest run's step screenshots as the
baseline (copies from the run dir - no re-run needed). Every later run pixel-compares
each step against it; changes above `policy.visual_threshold` (default 1.0%) surface
as `visual_change` side effects with a red-overlay `step-NN-diff.png` showing exactly
where the screen changed. Live-verified on a real dashboard: the diff overlay
correctly isolated an animated character, changed copy, and a widget layout shift
(2.2-4.1% per step).

- Rationale: assertion-based steps cannot see layout breakage; screenshots already
  exist per step, so the marginal cost is one pixel compare.
- Implementation: Pillow histogram-based mask (per-channel delta > 24), red composite
  overlay. Comparison runs post-steps in the engine; failures in the visual layer can
  never fail a run.
- Rejected: perceptual hashing (too coarse to localize), Playwright's built-in
  toHaveScreenshot (Node test-runner only, not available from Python).
- Caveats documented: baseline must be captured in the same headed/headless mode;
  dynamic pages need a higher threshold or re-baselining.

## Trace on failure

Playwright tracing (screenshots + DOM snapshots) records every run; kept as
`trace.zip` only when a step failed, discarded otherwise. Report links the replay
command (`npx playwright show-trace trace.zip`). Rejected: always keeping traces -
tens of MB per run of dead weight on green runs.

## JUnit XML (`run --junit results.xml`)

One testsuite per scenario, one testcase per step, failures/skips mapped natively,
visible side effects attached as suite system-out. Makes SuperQA a drop-in CI gate
(Jenkins/GitHub Actions/GitLab render it without plugins).

## superqa doctor

Plain-language environment check (Python version, textual/playwright/pyyaml/pillow,
Chromium binary, playwright-cli, data-dir writability) with exact fix commands.
Exists because non-developers hit environment problems first, not scenario problems.

## Verification

- New suite tests/test_v03_features.py: image-compare unit (50% change case + zero
  case), baseline accept -> identical run clean -> DOM change flagged with diff file,
  trace kept only on failure, JUnit well-formed with failure mapping, doctor green.
- All prior suites re-run green (engine smoke, v0.2 features, TUI pilot).
- Live: internal test bed (details local-only) 6-scenario headed sweep 6/6 green
  (user-visible browser), baselines accepted for all 6, headless rerun surfaced
  expected dynamic-content visual diffs.

## Pillow dependency

pillow added to pyproject dependencies and the launcher bootstrap; without it the
visual layer degrades silently (doctor marks it optional).
