"""Web admin: server serves the page, lists scenarios, runs one, serves report."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_TMP = tempfile.mkdtemp(prefix="superqa-admin-test-")
os.environ["SUPERQA_HOME"] = _TMP

from superqa_tui import admin  # noqa: E402
from superqa_tui.scenario import Scenario, Step  # noqa: E402

FIXTURE = (REPO / "tests" / "fixtures" / "testsite.html").as_uri()


def _seed() -> None:
    Scenario(name="admin-샘플", site="fixture", base_url=FIXTURE, steps=[
        Step(action="goto", url=FIXTURE, description="접속"),
        Step(action="click", selector="#alert-btn", description="알림"),
        Step(action="expect_visible", selector="#login-btn", description="로그인 버튼 확인"),
    ]).save()


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_admin_end_to_end() -> None:
    _seed()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), admin.Handler)
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        # page renders
        with urllib.request.urlopen(f"{base}/", timeout=10) as r:
            html = r.read().decode()
        assert "SuperQA" in html and "Admin" in html

        # scenario listed
        state = _get(f"{base}/api/state")
        names = [s["name"] for s in state["scenarios"]]
        assert "admin-샘플" in names, names

        # run it headless
        resp = _post(f"{base}/api/run", {"scenario": "admin-샘플", "headless": True})
        assert resp.get("token"), resp

        # poll until finished (or timeout)
        report_url = None
        for _ in range(60):
            st = _get(f"{base}/api/state")
            active = st["active"]
            done = [a for a in active if a["status"] != "running"]
            if done and done[0].get("report"):
                report_url = st["runs"][0].get("report_url")
                assert done[0]["status"] == "pass", done[0]
                break
            time.sleep(1)
        assert report_url, "run did not finish with a report"

        # report served through the admin, with its screenshot.
        # report_url from the API is already percent-encoded; request it as-is.
        with urllib.request.urlopen(f"{base}{report_url}", timeout=10) as r:
            rep_html = r.read().decode()
        assert "admin-샘플" in rep_html
        shot_url = report_url.rsplit("/", 1)[0] + "/step-00.png"
        with urllib.request.urlopen(f"{base}{shot_url}", timeout=10) as r:
            assert r.read()[:4] == b"\x89PNG"
        print("PASS test_admin_end_to_end")
    finally:
        httpd.shutdown()


def test_admin_path_traversal_blocked() -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), admin.Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        code = 0
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/report/../../../etc/passwd", timeout=10)
        except urllib.error.HTTPError as e:
            code = e.code
        assert code in (403, 404), code
        print("PASS test_admin_path_traversal_blocked")
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    test_admin_end_to_end()
    test_admin_path_traversal_blocked()
    print("ALL ADMIN TESTS PASSED")
