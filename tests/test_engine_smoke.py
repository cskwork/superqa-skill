"""End-to-end smoke: replay, side effects, recording, reports - on local fixtures.

Runs fully headless. SUPERQA_HOME points at a temp dir so the user DB is untouched.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_TMP = tempfile.mkdtemp(prefix="superqa-test-")
os.environ["SUPERQA_HOME"] = _TMP

from superqa_tui.engine import Engine  # noqa: E402
from superqa_tui.report import write_reports  # noqa: E402
from superqa_tui.scenario import Scenario, Step, load_scenario  # noqa: E402
from superqa_tui.store import Store  # noqa: E402

FIXTURE = (REPO / "tests" / "fixtures" / "testsite.html").as_uri()


def make_store() -> Store:
    store = Store(Path(_TMP) / "test.db")
    store.set_var("fixture", "username", "tester01")
    store.set_var("fixture", "password", "secret-pw-123")
    return store


def test_run_scenario_with_dialogs_popups_and_effects() -> None:
    store = make_store()
    sc = Scenario(
        name="픽스처-전체흐름", site="fixture", base_url=FIXTURE, language="ko",
        steps=[
            Step(action="goto", url=FIXTURE, description="테스트 사이트 접속"),
            Step(action="fill", selector="#username", value="{{username}}",
                 description="아이디 입력"),
            Step(action="fill", selector="#password", value="{{password}}",
                 description="비밀번호 입력"),
            Step(action="click", selector={"role": "button", "name": "로그인"},
                 description="로그인 버튼 클릭"),
            Step(action="expect_text", selector="#welcome", value="tester01",
                 description="환영 문구 확인"),
            Step(action="click", selector="#alert-btn", description="알림 팝업 열기"),
            Step(action="click", selector="#consoleerr-btn", description="콘솔 오류 유발"),
            Step(action="click", selector="#jserr-btn", description="JS 예외 유발"),
            Step(action="click", selector="#fetch404-btn", description="깨진 요청 유발"),
            Step(action="click", selector="#delay-btn", description="지연 표시 버튼"),
            Step(action="expect_visible", selector="#delayed", description="지연 내용 표시 확인"),
            Step(action="click", selector="#newtab-link", expect_popup=True,
                 description="새 탭 열기"),
            Step(action="expect_visible", selector="#second-title",
                 description="새 탭 내용 확인"),
        ],
    )
    engine = Engine(store=store, headed=False)
    result = asyncio.run(engine.run_scenario(sc))

    assert result.status == "pass", [
        (r.index, r.status, r.error) for r in result.step_results]
    types = {e.type for e in result.effects}
    assert "dialog" in types, types
    assert "console_error" in types, types
    assert "page_error" in types, types
    assert "request_failed" in types or "http_error" in types, types
    assert "popup" in types, types

    # a request URL carrying the secret must be masked in the report
    from superqa_tui.engine import SideEffect
    result.effects.append(SideEffect(
        "http_error", "warning", "401 https://api.example.com/login?pw=secret-pw-123"))
    md, html_p = write_reports(result, store)
    assert md.exists() and html_p.exists()
    html_text = html_p.read_text(encoding="utf-8")
    assert "secret-pw-123" not in html_text, "secret leaked into report"
    assert "api.example.com" in html_text
    print("PASS test_run_scenario_with_dialogs_popups_and_effects "
          f"(effects: {sorted(types)})")
    print(f"  report: {html_p}")


def test_record_via_driver_then_replay() -> None:
    store = make_store()
    engine = Engine(store=store, headed=False)

    async def driver(page) -> None:
        await page.wait_for_selector("#superqa-host")
        await page.fill("#username", "tester01")
        await page.fill("#password", "secret-pw-123")
        await page.click("#login-btn")
        await page.wait_for_selector("#welcome", state="visible")
        await asyncio.sleep(0.3)
        await page.evaluate("window.__superqa_emit({kind:'save'})")

    sc = asyncio.run(engine.record(FIXTURE, site="fixture", name="기록-스모크",
                                   driver=driver))
    actions = [s.action for s in sc.steps]
    assert actions[0] == "goto"
    assert "fill" in actions and "click" in actions, actions
    pw_steps = [s for s in sc.steps if s.action == "fill"
                and s.value == "{{password}}"]
    assert pw_steps, "password fill was not masked to {{password}}"
    assert sc.path and sc.path.exists()

    reloaded = load_scenario(sc.path)
    result = asyncio.run(engine.run_scenario(reloaded))
    assert result.status == "pass", [
        (r.index, r.status, r.error) for r in result.step_results]
    print(f"PASS test_record_via_driver_then_replay (steps: {actions})")


def test_auto_smoke() -> None:
    store = make_store()
    engine = Engine(store=store, headed=False)
    result = asyncio.run(engine.auto_smoke(FIXTURE, site="fixture"))
    assert result.status == "pass"
    assert result.run_dir and (result.run_dir / "step-00.png").exists()
    print("PASS test_auto_smoke")


if __name__ == "__main__":
    test_run_scenario_with_dialogs_popups_and_effects()
    test_record_via_driver_then_replay()
    test_auto_smoke()
    print("ALL ENGINE SMOKE TESTS PASSED")
