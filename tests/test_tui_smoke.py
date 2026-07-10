"""TUI smoke via Textual pilot: mounts, lists scenarios, opens/cancels modals."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_TMP = tempfile.mkdtemp(prefix="superqa-tui-test-")
os.environ["SUPERQA_HOME"] = _TMP

from superqa_tui.scenario import Scenario, Step  # noqa: E402


def _seed_scenario() -> None:
    fixture = (REPO / "tests" / "fixtures" / "testsite.html").as_uri()
    Scenario(name="TUI-샘플", site="fixture", base_url=fixture,
             steps=[Step(action="goto", url=fixture, description="접속")]).save()


async def _run() -> None:
    _seed_scenario()
    from textual.widgets import DataTable

    from superqa_tui.app import AskScreen, SuperQAApp

    app = SuperQAApp()
    async with app.run_test(size=(120, 40)) as pilot:
        table = app.query_one("#scenario-table", DataTable)
        assert table.row_count == 1, f"expected 1 scenario, got {table.row_count}"

        await pilot.press("v")                      # open vars modal
        await pilot.pause()
        assert isinstance(app.screen, AskScreen), type(app.screen)
        await pilot.click("#ask-cancel")            # close it
        await pilot.pause()
        assert not isinstance(app.screen, AskScreen)

        await pilot.press("n")                      # record modal opens the same way
        await pilot.pause()
        assert isinstance(app.screen, AskScreen)
        await pilot.click("#ask-cancel")
        await pilot.pause()

        await pilot.press("q")                      # quit cleanly
    print("PASS test_tui_smoke")


if __name__ == "__main__":
    asyncio.run(_run())
    print("ALL TUI SMOKE TESTS PASSED")
