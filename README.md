# SuperQA

Browser QA on any website - dev, staging, or prod - for anyone.

Give it a URL and a one-line prompt, and SuperQA explores the site, generates test
scenario cases, drives a real browser through them, detects side effects the flow
itself would never assert (console errors, JS exceptions, failed requests, unexpected
dialogs/popups/tabs), and writes a report a non-developer can read - in your language.

Two ways to use it:

- **As a Claude Code skill** - the agent reads `SKILL.md`, explores with
  `playwright-cli`, writes scenario YAMLs, runs them deterministically, and triages the
  findings for you.
- **As a standalone app** - a Textual TUI plus CLI. Record a scenario by clicking
  through the site in a real browser, then run, schedule, and automate it. No code.

## Why

- QA after every feature: a developer finishes a backend/frontend change, you run the
  site's saved cases (`superqa run --all --site myshop`) and get a regression verdict
  with evidence in minutes.
- Non-developers own the tests: recording is literally clicking through the site while
  a floating SuperQA panel captures each step with a human-readable description.
- Side effects are first-class: every run watches the whole browser context - including
  popups - so a 500 on an API, an uncaught exception, or an unexpected new tab shows up
  even when every asserted step passed. Duplicates are counted, known noise is split
  out via per-site ignore rules.
- Every run auto-compares against the previous run of the same scenario: new failures
  and newly appeared side-effect types are flagged as regressions; identical runs get
  a clean "no regression" verdict.

## Install

```bash
git clone https://github.com/cskwork/superqa-skill ~/.claude/skills/superqa
cd ~/.claude/skills/superqa
pip3 install textual playwright pyyaml && python3 -m playwright install chromium
# optional: pip3 install -e .   ->  gives you the `superqa` command
```

Requirements: Python 3.10+, Chromium via Playwright (installed above).

## Quick start (no code)

```bash
bash scripts/superqa.sh              # opens the TUI
```

- `n` - record: a Chrome window opens with a SuperQA panel (bottom-right). Click
  through the site; every click/input becomes a step. Passwords are stored as
  `{{password}}` placeholders, never plain text. Press "저장 후 종료" to save.
- `r` - run the selected scenario and watch the browser replay it.
- `a` - run everything (regression sweep). `u` - one-button smoke QA for any URL.
- `s` - schedule a scenario every N minutes. `v` - manage accounts/variables.
- `o` - open the latest HTML report.

## Quick start (CLI / CI)

```bash
superqa record https://myshop.example.com --site myshop --name 로그인-정상
superqa vars set myshop username myid
superqa vars set myshop password s3cret          # auto-masked in reports
superqa run --all --site myshop --headless        # exit code 0 = green
superqa auto https://myshop.example.com           # smoke QA, zero setup
superqa schedule add 로그인-정상 --every 30 && superqa schedule daemon
```

## What a run produces

`~/.superqa/reports/<stamp>-<scenario>/`:

- `report.html` - pass/fail badges, step table with inline screenshots, side-effect
  table. Self-contained; send it to anyone.
- `report.md` - the same, paste-ready.
- `step-NN.png` - screenshot after every step.

Report language follows the scenario's `language:` field (Korean and English built in).

## Scenario format

Plain YAML that non-developers can read and edit - see
[reference/scenario-format.md](reference/scenario-format.md):

```yaml
name: 로그인-정상
site: myshop
language: ko
policy: { dialogs: accept, popups: follow }
steps:
  - { action: goto, url: "{{entry_url}}", description: 사이트 접속 }
  - { action: fill, selector: "#username", value: "{{username}}", description: 아이디 입력 }
  - { action: click, selector: { role: button, name: 로그인 }, description: 로그인 버튼 클릭 }
  - { action: expect_text, selector: "#welcome", value: "{{username}}", description: 환영 문구 확인 }
```

Dialogs (alert/confirm/prompt) are auto-handled by policy; clicks that open new tabs
are followed automatically (`expect_popup: true` makes the tab mandatory).

## Site data stays local

Everything site-specific lives under `~/.superqa/` - never in this repo:

```
~/.superqa/
├── superqa.db               # accounts/vars (SQLite; secret keys masked in reports)
├── scenarios/<site>/*.yaml  # your test cases
├── reports/                 # run evidence
└── sites/<site>/rules.md    # per-site playbook the agent maintains
```

## Architecture

```
SKILL.md + reference/        agent lane: explore -> generate cases -> run -> triage
superqa_tui/
├── engine.py                Playwright driver: replay, record, auto-smoke,
│                            side-effect collectors (context-wide, incl. popups)
├── recorder_overlay.js      injected shadow-DOM panel: record / assert / save
├── scenario.py  store.py    YAML models; SQLite vars + run history
├── report.py    i18n.py     md/html reports, ko/en strings, secret masking
├── scheduler.py             interval schedules (TUI-armed or daemon)
├── app.py                   Textual TUI
└── cli.py                   headless CLI (CI-friendly exit codes)
```

## Tests

```bash
python3 tests/test_engine_smoke.py   # replay + record + auto QA on local fixtures
python3 tests/test_tui_smoke.py      # Textual pilot smoke
```

Verified against live sites: full pipeline (scenarios, dialogs, multi-tab popup
chains, login via stored vars) ran 3 consecutive green rounds on two independent
sites, and the side-effect collector surfaced a real uncaught JS exception on one
of them.

## License

MIT
