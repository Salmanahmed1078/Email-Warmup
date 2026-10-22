"""Command line: python -m warmup <command> [--live]. Everything is a dry run unless --live is given."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import shutil
import sys
import time

from . import config as config_mod
from . import content, gmail
from .logbook import Logbook
from .runner import Runner
from .schedule import target_range, week_number
from .state import State


def _clients(cfg, live: bool):
    clients = {}
    for key, inbox in cfg.inboxes.items():
        real = None
        if gmail.has_credentials(cfg, key):
            try:
                real = gmail.GmailClient(cfg, inbox)
            except Exception as exc:  # noqa: BLE001
                if live:
                    raise SystemExit(f"{key}: cannot open Gmail ({type(exc).__name__}). Re-run auth.") from None
                print(f"[dry-run] {key}: credentials unusable ({type(exc).__name__}); simulating reads as empty")
        elif live:
            raise SystemExit(f"{key}: no token. Run: python -m warmup auth --inbox {key}")
        clients[key] = real if live else gmail.DryRunClient(inbox, real)
    return clients


def _sheets(cfg, live: bool):
    sc = cfg.raw.get("sheets", {})
    if not (live and sc.get("enabled") and sc.get("spreadsheet_id")):
        return None
    from .logbook import SheetsSink
    return SheetsSink(cfg, gmail.load_credentials(cfg, sc["token_inbox"]))


def _paths(cfg, live: bool):
    d = cfg.data_dir / ("live" if live else "dry-run")
    return d, d / "state.json"


def cmd_tick(cfg, args, window=None) -> int:
    data_dir, state_path = _paths(cfg, args.live)
    clients, sheets = _clients(cfg, args.live), _sheets(cfg, args.live)
    with State(state_path) as st:
        r = Runner(cfg, clients, st.data, Logbook(data_dir), lambda: dt.datetime.now(cfg.tz), args.live,
                   sleep=time.sleep if args.live else (lambda s: None), sheets=sheets)
        return r.tick(args.window if window is None else window)


def cmd_run_day(cfg, args) -> int:
    """Long-running mode: tick until working hours end and nothing is left for today."""
    data_dir, state_path = _paths(cfg, args.live)
    clients, sheets = _clients(cfg, args.live), _sheets(cfg, args.live)
    while True:
        with State(state_path) as st:
            r = Runner(cfg, clients, st.data, Logbook(data_dir), lambda: dt.datetime.now(cfg.tz), args.live,
                       sleep=time.sleep if args.live else (lambda s: None), sheets=sheets)
            code = r.tick(0)
            nxt = r.next_due()
            stopped = bool(st.data["alert"])
        now = dt.datetime.now(cfg.tz)
        end = cfg.at(now.date(), cfg.work_end())
        if code == 2 or stopped:
            return code
        if not args.live:
            print("[dry-run] run-day does one pass in dry-run mode; use 'simulate' to see a whole day")
            return 0
        if now >= end and (nxt is None or nxt.date() > now.date()):
            return 0
        wake = min(x for x in [nxt, now + dt.timedelta(minutes=10)] if x is not None)
        time.sleep(max(30.0, (wake - now).total_seconds()))


def cmd_plan(cfg, args) -> int:
    """Preview a day's plan without saving anything."""
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(cfg.tz).date()
    lo, hi = target_range(cfg, day)
    print(f"{day} week {week_number(cfg, day)}: range {lo}-{hi} per inbox, hard cap {cfg.hard_daily_cap}")
    tmp = cfg.data_dir / "preview"
    r = Runner(cfg, {}, json.loads(json.dumps({"days": {}, "actions": [], "handled": {}, "bounces": [],
               "seen_bounces": {}, "paused": {}, "alert": None, "problems": {}})), Logbook(tmp),
               lambda: cfg.at(day, dt.time(6, 0)), False, rng=random.Random(args.seed))
    for a in r.plan_day(day, cfg.at(day, dt.time(6, 0))):
        print(f"  {a['at'][11:16]}  {a['inbox']:>7} -> {a['to']:<7} {a['subject']}")
        if args.show_body:
            print("    " + a["body"].replace("\n", "\n    "))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


def cmd_simulate(cfg, args) -> int:
    """Run whole days against an in-memory fake Gmail (no network, nothing saved outside data/sim)."""
    start = dt.date.fromisoformat(args.date) if args.date else cfg.start_date
    clock = [cfg.at(start, dt.time(8, 30))]
    world = gmail.FakeWorld(lambda: clock[0], spam_rate=args.spam_rate, rng=random.Random(args.seed),
                            bounce_to={cfg.inboxes[args.bounce].email} if args.bounce else None)
    clients = {k: gmail.FakeClient(world, i, cfg) for k, i in cfg.inboxes.items()}
    data_dir = cfg.data_dir / "sim"
    shutil.rmtree(data_dir, ignore_errors=True)

    def sleep(sec):
        clock[0] += dt.timedelta(seconds=sec)

    with State(data_dir / "state.json") as st:
        r = Runner(cfg, clients, st.data, Logbook(data_dir), lambda: clock[0], True,
                   out=lambda m: print("[sim] " + m), sleep=sleep, rng=random.Random(args.seed))
        for d in range(args.days):
            day = start + dt.timedelta(days=d)
            clock[0] = cfg.at(day, dt.time(8, 30))
            while clock[0] < cfg.at(day, dt.time(18, 0)):
                if r.tick(0) == 2 or st.data["alert"]:
                    print("[sim] stopped by alert")
                    break
                clock[0] += dt.timedelta(minutes=5)
            for row in r.daily_rows(day):
                print(f"[sim] {row}")
            if st.data["alert"]:
                break
    print(f"[sim] CSV logs in {data_dir}")
    return 0


def cmd_check(cfg, args) -> int:
    pool = content.load_pool()
    ok = True
    print(f"Pool: {len(pool['templates'])} templates")
    for t in pool["templates"]:
        n = content.sentence_count(" ".join(t["body"].split()))
        if not 3 <= n <= 5 or not 3 <= len(t["replies"]) <= 4:
            ok = False
            print(f"  {t['id']}: {n} sentences, {len(t['replies'])} replies (want 3-5 / 3-4)")
        for s in t["subjects"] + [t["body"]] + t["replies"]:
            try:
                content.check_clean(s)
            except ValueError as e:
                ok = False
                print(f"  {t['id']}: {e}")
    for key, inbox in cfg.inboxes.items():
        has = gmail.has_credentials(cfg, key)
        print(f"{key:>7} {inbox.email:<26} token: {'present' if has else 'MISSING'}  signature: {inbox.full_name} / {inbox.title}")
    client = (cfg.secrets_dir / "client_secret.json").exists() or bool(gmail.os.environ.get("WARMUP_CLIENT_SECRET_JSON"))
    print(f"OAuth client file: {'present' if client else 'MISSING'}")
    today = dt.datetime.now(cfg.tz).date()
    print(f"Today {today}: week {week_number(cfg, today)}, range {target_range(cfg, today)}")
    return 0 if ok else 1


def cmd_status(cfg, args) -> int:
    _, path = _paths(cfg, args.live)
    if not path.exists():
        print("no state yet")
        return 0
    s = json.loads(path.read_text())
    today = dt.datetime.now(cfg.tz).date().isoformat()
    print(f"alert: {s.get('alert')}")
    print(f"paused: {s.get('paused')}")
    for a in sorted((a for a in s["actions"] if a["at"][:10] == today), key=lambda a: a["at"]):
        print(f"  {a['at'][11:16]} {a['status']:<8} {a['kind']:<5} {a['inbox']:>7} -> {a['to']:<7} {a['subject']}")
    return 0


def cmd_clear_alert(cfg, args) -> int:
    data_dir, path = _paths(cfg, args.live)
    with State(path) as st:
        st.data["alert"] = None
    (data_dir / "ALERT.txt").unlink(missing_ok=True)
    print("alert cleared (inbox pauses stay in place until they expire)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="warmup", description=__doc__)
    p.add_argument("--config", help="path to config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("--live", action="store_true", help="really send/modify mail (default: dry run)")
        return sp

    a = sub.add_parser("auth", help="OAuth sign-in for one inbox (opens a browser)")
    a.add_argument("--inbox", required=True)
    a.add_argument("--port", type=int, default=0)
    add("check", help="validate config, content pool and credentials")
    t = add("tick", help="do everything that is due now (run from cron every 5 minutes)")
    t.add_argument("--window", type=float, default=0, help="also wait for actions due in the next N minutes")
    add("run-day", help="long-running: keep ticking until the working day is done")
    add("rescue", help="spam/promotions rescue only")
    pl = sub.add_parser("plan", help="preview a day's plan (nothing saved)")
    pl.add_argument("--date")
    pl.add_argument("--seed", type=int)
    pl.add_argument("--show-body", action="store_true")
    sm = sub.add_parser("simulate", help="run whole days against a fake Gmail")
    sm.add_argument("--date")
    sm.add_argument("--days", type=int, default=1)
    sm.add_argument("--seed", type=int, default=1)
    sm.add_argument("--spam-rate", type=float, default=0.2)
    sm.add_argument("--bounce", help="make mail to this inbox bounce (tests the alert)")
    add("status", help="show today's actions")
    add("clear-alert", help="resume after investigating a bounce/spam alert")
    args = p.parse_args(argv)
    cfg = config_mod.load(args.config)

    if args.cmd == "auth":
        gmail.run_auth(cfg, args.inbox, args.port)
        return 0
    if args.cmd == "rescue":
        args.window = 0
        data_dir, path = _paths(cfg, args.live)
        with State(path) as st:
            r = Runner(cfg, _clients(cfg, args.live), st.data, Logbook(data_dir),
                       lambda: dt.datetime.now(cfg.tz), args.live)
            r.rescue(dt.datetime.now(cfg.tz).date())
        return 0
    return {"check": cmd_check, "tick": cmd_tick, "run-day": cmd_run_day, "plan": cmd_plan,
            "simulate": cmd_simulate, "status": cmd_status, "clear-alert": cmd_clear_alert}[args.cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
