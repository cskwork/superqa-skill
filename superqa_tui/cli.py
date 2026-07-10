"""Headless CLI. The same engine the TUI uses, driveable by agents and cron.

  superqa                       -> TUI
  superqa run <name|path>       -> run one scenario (add --headless for CI)
  superqa run --all [--site s]  -> run every scenario (regression sweep)
  superqa auto <url>            -> one-button smoke QA on a URL
  superqa record <url>          -> record a scenario by clicking in the browser
  superqa vars set|list|delete  -> account/variable store (SQLite, masked)
  superqa schedule add|list|remove|daemon
  superqa report [open]         -> print/open latest report
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from urllib.parse import urlparse

from .diff import compute_diff, format_diff_lines
from .engine import Engine, RunResult
from .i18n import t
from .report import write_index, write_reports
from .scenario import broken_scenarios, find_scenario, list_scenarios
from .scheduler import add_schedule, load_schedules, remove_schedule, run_loop
from .store import Store


def _print_event(ev: dict) -> None:
    kind = ev.get("kind")
    if kind == "step_start":
        print(f"  [{ev['index'] + 1}] {ev.get('description') or ev.get('action')} ...")
    elif kind == "step_end":
        mark = "PASS" if ev["status"] == "pass" else ev["status"].upper()
        err = f" - {ev['error']}" if ev.get("error") else ""
        print(f"      -> {mark}{err}")
    elif kind == "effect" and ev.get("severity") == "error":
        print(f"      !! {ev.get('type')}: {str(ev.get('message'))[:120]}")
    elif kind == "recorded":
        print(f"  녹화 {ev.get('count')}단계: {ev.get('step', {}).get('description', '')}")
    elif kind == "record_done":
        print(f"저장됨: {ev.get('path')} ({ev.get('steps')}단계)")


def _finish(result: RunResult, store: Store, run_id: int) -> int:
    lang = result.scenario.language
    summary = result.summary_dict()
    prev = store.previous_run(result.scenario.name, run_id)
    diff = compute_diff(prev.get("summary") if prev else None, summary)
    diff_lines = format_diff_lines(diff, lang)
    _md, html_p = write_reports(result, store, diff_lines)
    store.finish_run(run_id, result.status, result.passed, result.failed,
                     len(result.visible_effects), str(html_p),
                     json.dumps(summary, ensure_ascii=False))
    write_index(store, lang)
    word = t("status_pass", lang) if result.status == "pass" else t("status_fail", lang)
    ignored_n = len(result.effects) - len(result.visible_effects)
    noise = f" (노이즈 {ignored_n}건 분리)" if ignored_n and lang == "ko" else (
        f" ({ignored_n} noise entries filtered)" if ignored_n else "")
    print(f"\n{t('result', lang)}: {word} | "
          + t("summary_line", lang, total=len(result.step_results),
              passed=result.passed, failed=result.failed)
          + " | " + t("effects_line", lang, count=len(result.visible_effects)) + noise)
    print(f"{t('diff_title', lang)}:")
    for ln in diff_lines:
        print(f"  {ln}")
    print(f"리포트: {html_p}")
    return 0 if result.status == "pass" else 1


async def _run_one(name: str, headed: bool, store: Store) -> int:
    sc = find_scenario(name)
    print(f"실행: {sc.name} ({sc.site})")
    run_id = store.start_run(sc.name, sc.site)
    engine = Engine(store=store, headed=headed, on_event=_print_event)
    result = await engine.run_scenario(sc)
    return _finish(result, store, run_id)


def cmd_run(args) -> int:
    store = Store()
    headed = not args.headless
    for path, err in broken_scenarios():
        print(f"[경고] 읽을 수 없는 시나리오(건너뜀): {path} - {err}")
    if args.all:
        scs = [s for s in list_scenarios() if not args.site or s.site == args.site]
        if not scs:
            print("실행할 시나리오가 없습니다.")
            return 1
        codes = [asyncio.run(_run_one(str(s.path), headed, store)) for s in scs]
        bad = sum(1 for c in codes if c != 0)
        print(f"\n전체 결과: {len(codes) - bad}/{len(codes)} 성공")
        return 0 if bad == 0 else 1
    if not args.scenario:
        print("시나리오 이름 또는 경로가 필요합니다. (superqa run <name> | --all)")
        return 2
    return asyncio.run(_run_one(args.scenario, headed, store))


def cmd_auto(args) -> int:
    store = Store()
    engine = Engine(store=store, headed=not args.headless, on_event=_print_event)
    # same name the engine gives the scenario, so run-to-run diff links up
    run_name = f"자동QA-{urlparse(args.url).netloc or 'local'}"
    run_id = store.start_run(run_name, args.site)
    result = asyncio.run(engine.auto_smoke(args.url, site=args.site,
                                           max_links=args.max_links, language=args.lang))
    return _finish(result, store, run_id)


def cmd_record(args) -> int:
    store = Store()
    engine = Engine(store=store, headed=True, on_event=_print_event)
    print(t("record_hint"))
    sc = asyncio.run(engine.record(args.url, site=args.site, name=args.name or "",
                                   language=args.lang))
    print(f"시나리오 저장: {sc.path}")
    return 0


def cmd_vars(args) -> int:
    store = Store()
    if args.vars_cmd == "set":
        store.set_var(args.site, args.key, args.value)
        print(f"{t('saved')}: {args.site}/{args.key}")
    elif args.vars_cmd == "delete":
        store.delete_var(args.site, args.key)
        print(f"삭제됨: {args.site}/{args.key}")
    else:
        rows = store.list_vars(args.site if hasattr(args, "site") else None)
        if not rows:
            print("저장된 변수가 없습니다. 예: superqa vars set myshop username myid")
        for r in rows:
            val = "******" if r["secret"] else r["value"]
            print(f"  {r['site']:12s} {r['key']:20s} {val}")
    return 0


def cmd_schedule(args) -> int:
    if args.sched_cmd == "add":
        e = add_schedule(args.scenario, args.every)
        print(t("schedule_armed", name=e.scenario, minutes=e.every_minutes))
        print(t("schedule_hint"))
    elif args.sched_cmd == "remove":
        ok = remove_schedule(args.scenario)
        print("삭제됨" if ok else "해당 스케줄 없음")
    elif args.sched_cmd == "daemon":
        store = Store()

        async def runner(name: str) -> None:
            await _run_one(name, headed=False, store=store)

        print("스케줄 데몬 시작 (Ctrl+C로 종료)")
        try:
            asyncio.run(run_loop(runner))
        except KeyboardInterrupt:
            pass
    else:
        entries = load_schedules()
        if not entries:
            print("등록된 스케줄이 없습니다. 예: superqa schedule add <시나리오> --every 30")
        for e in entries:
            state = "on" if e.enabled else "off"
            print(f"  [{state}] {e.scenario} - {e.every_minutes}분마다")
    return 0


def cmd_report(args) -> int:
    store = Store()
    if args.report_cmd == "list":
        idx = write_index(store)
        for r in store.recent_runs(15):
            import time as _t
            when = _t.strftime("%m-%d %H:%M", _t.localtime(r["started_at"]))
            print(f"  {when}  {r['status']:8s} {r['scenario']:28s} "
                  f"{r['passed']}/{r['passed'] + r['failed']}  부작용 {r['effects']}")
        print(f"이력 인덱스: {idx}")
        return 0
    runs = store.recent_runs(1)
    if not runs or not runs[0].get("report_path"):
        print("리포트가 없습니다.")
        return 1
    path = runs[0]["report_path"]
    print(path)
    if args.report_cmd == "open":
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", path],
                       check=False)
    return 0


def cmd_list(_args) -> int:
    scs = list_scenarios()
    if not scs:
        print(t("no_scenarios"))
    for s in scs:
        print(f"  {s.site:12s} {s.name:30s} {len(s.steps)}단계  {s.path}")
    for path, err in broken_scenarios():
        print(f"  [경고] 읽을 수 없는 시나리오: {path} - {err}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="superqa", description=t("app_title"))
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="시나리오 실행")
    r.add_argument("scenario", nargs="?", help="시나리오 이름 또는 YAML 경로")
    r.add_argument("--all", action="store_true", help="모든 시나리오 실행(회귀 테스트)")
    r.add_argument("--site", default="", help="사이트 필터")
    r.add_argument("--headless", action="store_true", help="브라우저 창 없이 실행")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("auto", help="URL 하나로 자동 스모크 QA")
    a.add_argument("url")
    a.add_argument("--site", default="default")
    a.add_argument("--lang", default="ko")
    a.add_argument("--max-links", type=int, default=8)
    a.add_argument("--headless", action="store_true")
    a.set_defaults(func=cmd_auto)

    rec = sub.add_parser("record", help="브라우저 클릭으로 시나리오 기록")
    rec.add_argument("url")
    rec.add_argument("--site", default="default")
    rec.add_argument("--name", default="")
    rec.add_argument("--lang", default="ko")
    rec.set_defaults(func=cmd_record)

    v = sub.add_parser("vars", help="계정/변수 저장소 (SQLite)")
    vsub = v.add_subparsers(dest="vars_cmd")
    vs = vsub.add_parser("set")
    vs.add_argument("site"); vs.add_argument("key"); vs.add_argument("value")
    vl = vsub.add_parser("list")
    vl.add_argument("site", nargs="?", default=None)
    vd = vsub.add_parser("delete")
    vd.add_argument("site"); vd.add_argument("key")
    v.set_defaults(func=cmd_vars, vars_cmd="list")

    s = sub.add_parser("schedule", help="QA 스케줄")
    ssub = s.add_subparsers(dest="sched_cmd")
    sa = ssub.add_parser("add")
    sa.add_argument("scenario"); sa.add_argument("--every", type=int, required=True,
                                                 help="간격(분)")
    sr = ssub.add_parser("remove"); sr.add_argument("scenario")
    ssub.add_parser("list"); ssub.add_parser("daemon")
    s.set_defaults(func=cmd_schedule, sched_cmd="list")

    rep = sub.add_parser("report", help="최근 리포트 / 이력")
    rep.add_argument("report_cmd", nargs="?", choices=["open", "list"], default=None)
    rep.set_defaults(func=cmd_report)

    ls = sub.add_parser("list", help="시나리오 목록")
    ls.set_defaults(func=cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "cmd", None):
        from .app import SuperQAApp  # lazy: textual import only for TUI
        SuperQAApp().run()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
