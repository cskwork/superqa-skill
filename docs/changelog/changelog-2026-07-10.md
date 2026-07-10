# Changelog 2026-07-10

## v0.2.0 - regression diff, noise control, retry (same day, from live-usage pain)

- **Run-to-run diff**: every run persists a summary (failed steps + digit-normalized
  effect digests) in the runs table; the next run of the same scenario prints and
  embeds "지난 실행과 비교" - new failures, resolved failures, new/gone effect types.
  Rationale: the post-feature regression question is "what CHANGED", not raw counts.
  Rejected: diffing full reports - too brittle; URLs carry tokens/timestamps, so
  digests collapse digits instead.
- **Effect dedupe + ignore rules**: identical effects collapse into one row with a
  count; site-level `sites/<site>/ignore.yaml` + scenario `policy.ignore_effects`
  demote known noise into a separate report section (never deleted). Live effect:
  viewer run went from 27 raw effects to 4 meaningful + 5 noise rows.
- **Step retry**: `retry: N` re-attempts flaky steps (viewer swallowed first click).
- **Recorder var mapping**: recorded fill values equal to stored vars are saved as
  `{{key}}` references - portable scenarios, no personal values in YAML.
- **Visibility fixes**: broken scenario YAMLs now warn in list/run --all/TUI
  (previously silently skipped); `superqa report list` + auto-refreshed
  `reports/index.html` run history.
- Verified: 5 new feature tests + existing suites green; live double-run on the
  internal test bed showed first-run notice then "회귀 없음" verdict.

## v0.1.0 initial build

## Decisions and reasoning

### One engine, two lanes
Agent lane (SKILL.md + playwright-cli exploration) and human lane (Textual TUI +
recorder) share the same Playwright-based engine and YAML scenario format. Rejected:
separate pytest codegen per site (the prior per-site pytest QA project's approach) -
code-per-site does not generalize to "any site" and non-developers cannot maintain it. YAML scenarios are the
portable middle: agents generate them, humans record them, both replay identically.

### playwright-cli for exploration, Playwright Python for execution
playwright-cli is token-efficient for agent exploration (snapshot/refs) but is
interactive by design; deterministic replay, context-wide side-effect listeners,
recording bindings, and TUI integration need the library API. Rejected: driving
everything through playwright-cli subprocess calls from the TUI - no event listeners,
no dialog policy hooks.

### Side effects as first-class run output
Collectors attach at BrowserContext level so popups are covered automatically:
console errors, page errors, requestfailed, HTTP >= 400 (deduped), dialogs, popups,
downloads - each tagged with the step index. Steps decide pass/fail by default;
policy flags (fail_on_console_error / fail_on_http_error) opt into strict gates.
Rejected: failing runs on any console error by default - real prod sites are too
noisy (verified: third-party analytics DNS failures on a public site).

### Recording via injected shadow-DOM overlay + expose_binding
The recorder is an init script (capture-phase listeners, selector inference chain
testid > id > role+name > text > css path) with a floating panel (record/pause,
add-assertion, save). Password inputs are recorded as {{password}} placeholders -
recording never persists plain secrets. Rejected: Playwright codegen - emits code,
not human-readable YAML, and cannot inject the assertion UX.

### SQLite var store with secret masking
Per-site key/value store (~/.superqa/superqa.db); {{key}} substitution at run time,
site scope then global. Keys matching pass/pw/secret/token/pin auto-flagged secret and
masked in report text and error messages. Rejected: .env files per site - non-devs
edit them badly, and values leak into YAML diffs.

### All site knowledge local (~/.superqa), never in the repo
Scenarios, reports, site rules, DB live in the user home. The repo ships only the
generic engine + docs; .gitignore additionally blocks accidental in-repo scenario or
site-rule files. Reason: the skill must stay publishable while test targets are
internal.

### Scheduling: simple interval loop
schedules.yaml + asyncio loop armed by the TUI, plus `superqa schedule daemon` for
background use. Rejected: APScheduler/cron integration in v0.1 - extra dependency and
platform-specific setup for marginal gain at this stage.

## Verification evidence

- tests/test_engine_smoke.py: replay with dialogs/popups/errors, record-then-replay,
  auto smoke - all pass headless on local fixtures.
- tests/test_tui_smoke.py: Textual pilot - mount, list, modals - pass.
- Live site A (public QA practice site): 3 scenarios (login via stored vars, failed
  login validation, JS dialogs + new-window) x 3 consecutive rounds - 9/9 pass;
  collector surfaced the site's real third-party analytics failures.
- Live site B (internal test bed, details local-only): 3 scenarios covering a
  double new-tab chain (entry -> auth tab -> dashboard; dashboard -> viewer tab)
  x 3 consecutive rounds - 9/9 pass; collector surfaced a real uncaught JS exception
  in the viewer plus a Canvas2D performance warning.
- report.html visually verified via headless render (badges, inline screenshots,
  Korean labels).
