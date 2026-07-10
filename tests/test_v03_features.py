"""v0.3 features: visual regression, trace-on-failure, JUnit XML, doctor."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_TMP = tempfile.mkdtemp(prefix="superqa-v03-test-")
os.environ["SUPERQA_HOME"] = _TMP

from superqa_tui.engine import Engine  # noqa: E402
from superqa_tui.junit import write_junit  # noqa: E402
from superqa_tui.scenario import Scenario, Step  # noqa: E402
from superqa_tui.store import Store  # noqa: E402
from superqa_tui.visual import accept_baseline, baseline_dir, compare_images  # noqa: E402

FIXTURE = (REPO / "tests" / "fixtures" / "testsite.html").as_uri()


def _mk_scenario(name: str, extra_steps: list[Step] | None = None) -> Scenario:
    return Scenario(name=name, site="fixture", base_url=FIXTURE, steps=[
        Step(action="goto", url=FIXTURE, description="접속"),
        *(extra_steps or []),
    ])


def test_compare_images_unit() -> None:
    from PIL import Image
    a_path, b_path = Path(_TMP) / "a.png", Path(_TMP) / "b.png"
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    img.save(a_path)
    img2 = img.copy()
    for x in range(50):          # paint 50x100 red = 50% changed
        for y in range(100):
            img2.putpixel((x, y), (200, 0, 0))
    img2.save(b_path)
    diff_out = Path(_TMP) / "d.png"
    pct = compare_images(a_path, b_path, diff_out)
    assert 45 <= pct <= 55, pct
    assert diff_out.exists()
    assert compare_images(a_path, a_path) == 0.0
    print("PASS test_compare_images_unit")


def test_visual_regression_flow() -> None:
    """Identical page vs baseline -> no visual_change; DOM change -> flagged."""
    store = Store(Path(_TMP) / "v.db")
    engine = Engine(store=store, headed=False)
    sc = _mk_scenario("시각회귀", [Step(action="wait", value="0.5", description="대기")])

    r1 = asyncio.run(engine.run_scenario(sc))
    assert r1.run_dir is not None
    n = accept_baseline(sc.site, sc.name, r1.run_dir)
    assert n >= 1 and baseline_dir(sc.site, sc.name).exists()

    r2 = asyncio.run(engine.run_scenario(sc))
    assert not [e for e in r2.effects if e.type == "visual_change"], \
        [e.message for e in r2.effects]

    sc3 = _mk_scenario("시각회귀", [
        Step(action="click", selector="#theme-btn", description="배경색 변경"),
    ])
    r3 = asyncio.run(engine.run_scenario(sc3))
    changes = [e for e in r3.effects if e.type == "visual_change"]
    assert changes, "visual change not detected"
    assert r3.run_dir and list(r3.run_dir.glob("*-diff.png"))
    print(f"PASS test_visual_regression_flow ({changes[0].message})")


def test_trace_saved_only_on_failure() -> None:
    store = Store(Path(_TMP) / "tr.db")
    engine = Engine(store=store, headed=False)
    ok = asyncio.run(engine.run_scenario(_mk_scenario("트레이스-성공")))
    assert ok.run_dir and not (ok.run_dir / "trace.zip").exists()
    bad = asyncio.run(engine.run_scenario(_mk_scenario("트레이스-실패", [
        Step(action="click", selector="#no-such-element", timeout_ms=1500,
             description="없는 요소 클릭")])))
    assert bad.status == "fail"
    assert bad.run_dir and (bad.run_dir / "trace.zip").exists()
    print("PASS test_trace_saved_only_on_failure")


def test_junit_output() -> None:
    store = Store(Path(_TMP) / "j.db")
    engine = Engine(store=store, headed=False)
    good = asyncio.run(engine.run_scenario(_mk_scenario("junit-ok")))
    bad = asyncio.run(engine.run_scenario(_mk_scenario("junit-bad", [
        Step(action="click", selector="#no-such-element", timeout_ms=1500,
             description="없는 요소")])))
    out = write_junit([good, bad], Path(_TMP) / "junit.xml")
    text = out.read_text(encoding="utf-8")
    assert "<testsuites" in text and 'failures="1"' in text
    assert "junit-ok" in text and "junit-bad" in text and "<failure" in text
    import xml.etree.ElementTree as ET
    ET.parse(out)  # must be well-formed
    print("PASS test_junit_output")


def test_doctor_runs() -> None:
    from superqa_tui.cli import cmd_doctor
    code = cmd_doctor(None)
    assert code == 0, "doctor found problems on a known-good environment"
    print("PASS test_doctor_runs")


if __name__ == "__main__":
    test_compare_images_unit()
    test_visual_regression_flow()
    test_trace_saved_only_on_failure()
    test_junit_output()
    test_doctor_runs()
    print("ALL V0.3 FEATURE TESTS PASSED")
