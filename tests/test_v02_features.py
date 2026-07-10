"""v0.2 features: effect dedupe+count, ignore rules, step retry, run diff."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_TMP = tempfile.mkdtemp(prefix="superqa-v02-test-")
os.environ["SUPERQA_HOME"] = _TMP

from superqa_tui.diff import compute_diff, format_diff_lines, is_clean  # noqa: E402
from superqa_tui.engine import Engine  # noqa: E402
from superqa_tui.report import write_index, write_reports  # noqa: E402
from superqa_tui.scenario import Policy, Scenario, Step  # noqa: E402
from superqa_tui.store import Store  # noqa: E402

FIXTURE = (REPO / "tests" / "fixtures" / "testsite.html").as_uri()


def test_effect_dedupe_and_count() -> None:
    """The same console error fired 3x becomes ONE effect with count=3."""
    store = Store(Path(_TMP) / "t1.db")
    sc = Scenario(name="dedupe", site="fixture", base_url=FIXTURE, steps=[
        Step(action="goto", url=FIXTURE),
        Step(action="click", selector="#consoleerr-btn"),
        Step(action="wait", value="1"),
    ])
    result = asyncio.run(Engine(store=store, headed=False).run_scenario(sc))
    errs = [e for e in result.effects if e.type == "console_error"]
    assert len(errs) == 1, [e.to_dict() for e in errs]
    assert errs[0].count == 3, errs[0].to_dict()
    print("PASS test_effect_dedupe_and_count")


def test_ignore_rules_split_noise() -> None:
    """Effects matching policy.ignore_effects are kept but marked ignored."""
    store = Store(Path(_TMP) / "t2.db")
    sc = Scenario(name="ignore", site="fixture", base_url=FIXTURE,
                  policy=Policy(ignore_effects=["의도된 콘솔 오류"]),
                  steps=[
                      Step(action="goto", url=FIXTURE),
                      Step(action="click", selector="#consoleerr-btn"),
                      Step(action="wait", value="1"),
                  ])
    result = asyncio.run(Engine(store=store, headed=False).run_scenario(sc))
    ignored = [e for e in result.effects if e.ignored]
    assert ignored and all("의도된" in e.message for e in ignored)
    assert not any("의도된" in e.message for e in result.visible_effects)
    md, html_p = write_reports(result, store)
    text = html_p.read_text(encoding="utf-8")
    assert "무시된 부작용" in text
    print("PASS test_ignore_rules_split_noise")


def test_step_retry_recovers() -> None:
    """A step that fails on attempt 1 passes when retry allows a second try.

    #delayed appears 1.2s after the button click; a 900ms timeout fails the
    first attempt, and the retry (after 1s pause) finds it.
    """
    store = Store(Path(_TMP) / "t3.db")
    sc = Scenario(name="retry", site="fixture", base_url=FIXTURE, steps=[
        Step(action="goto", url=FIXTURE),
        Step(action="click", selector="#delay-btn"),
        Step(action="expect_visible", selector="#delayed", timeout_ms=900, retry=2),
    ])
    result = asyncio.run(Engine(store=store, headed=False).run_scenario(sc))
    assert result.status == "pass", [
        (r.index, r.status, r.error) for r in result.step_results]
    print("PASS test_step_retry_recovers")


def test_diff_detects_new_failure_and_effects() -> None:
    prev = {"status": "pass", "passed": 5, "failed": 0,
            "failed_steps": [], "effect_digests": ["dialog:confirm: 진행할까요?"]}
    cur = {"status": "fail", "passed": 4, "failed": 1,
           "failed_steps": ["로그인 버튼 클릭"],
           "effect_digests": ["dialog:confirm: 진행할까요?", "http_error:# https://x/api"]}
    d = compute_diff(json.dumps(prev, ensure_ascii=False), cur)
    assert d["new_failed_steps"] == ["로그인 버튼 클릭"]
    assert d["new_effects"] == ["http_error:# https://x/api"]
    assert not is_clean(d)
    lines = format_diff_lines(d, "ko")
    assert any("새 실패" in ln for ln in lines), lines

    same = compute_diff(json.dumps(cur, ensure_ascii=False), cur)
    assert is_clean(same)
    assert format_diff_lines(same, "ko") == ["지난 실행과 동일합니다 - 회귀 없음"]

    first = compute_diff(None, cur)
    assert first.get("first_run")
    print("PASS test_diff_detects_new_failure_and_effects")


def test_run_summary_roundtrip_and_index() -> None:
    """summary persists to the runs table; previous_run feeds the next diff."""
    store = Store(Path(_TMP) / "t4.db")
    sc = Scenario(name="라운드트립", site="fixture", base_url=FIXTURE, steps=[
        Step(action="goto", url=FIXTURE, description="접속"),
        Step(action="click", selector="#alert-btn", description="알림"),
    ])
    engine = Engine(store=store, headed=False)

    r1 = asyncio.run(engine.run_scenario(sc))
    id1 = store.start_run(sc.name, sc.site)
    store.finish_run(id1, r1.status, r1.passed, r1.failed,
                     len(r1.visible_effects), None,
                     json.dumps(r1.summary_dict(), ensure_ascii=False))

    r2 = asyncio.run(engine.run_scenario(sc))
    id2 = store.start_run(sc.name, sc.site)
    prev = store.previous_run(sc.name, id2)
    assert prev and prev["id"] == id1
    d = compute_diff(prev["summary"], r2.summary_dict())
    assert is_clean(d), d
    idx = write_index(store)
    assert idx.exists() and "라운드트립" in idx.read_text(encoding="utf-8")
    print("PASS test_run_summary_roundtrip_and_index")


if __name__ == "__main__":
    test_effect_dedupe_and_count()
    test_ignore_rules_split_noise()
    test_step_retry_recovers()
    test_diff_detects_new_failure_and_effects()
    test_run_summary_roundtrip_and_index()
    print("ALL V0.2 FEATURE TESTS PASSED")
