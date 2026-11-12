import datetime as dt
import random

from warmup import config, content
from warmup.__main__ import main
from warmup.runner import spread_times
from warmup.schedule import target_range, week_number

CFG = config.load()


def test_calendar_and_shift():
    assert target_range(CFG, dt.date(2026, 10, 22)) == (5, 10)
    assert target_range(CFG, dt.date(2026, 10, 29)) == (10, 15)
    assert target_range(CFG, dt.date(2026, 11, 5)) == (20, 30)
    assert target_range(CFG, dt.date(2026, 12, 1)) == (20, 30)
    assert target_range(CFG, dt.date(2026, 10, 24)) == (0, 0)  # Saturday
    CFG.start_date = dt.date(2026, 10, 26)
    try:
        assert week_number(CFG, dt.date(2026, 11, 2)) == 2
        assert target_range(CFG, dt.date(2026, 10, 23)) == (0, 0)
    finally:
        CFG.start_date = dt.date(2026, 10, 22)


def test_spread_times_gaps_and_hours():
    start, end = CFG.at(dt.date(2026, 11, 12), dt.time(9)), CFG.at(dt.date(2026, 11, 12), dt.time(16, 15))
    for seed in range(20):
        times = spread_times(50, start, end, [5, 15], random.Random(seed))
        assert all(start <= t <= end for t in times)
        assert all((b - a).total_seconds() >= 5 * 60 - 1 for a, b in zip(times, times[1:]))


def test_pool_is_clean_and_signed():
    pool = content.load_pool()
    assert len(pool["templates"]) >= 40
    a, b = CFG.inboxes["awais"], CFG.inboxes["kinza"]
    email, values = content.render_email(CFG, pool, pool["templates"][0], a, b, random.Random(1))
    assert email.body.rstrip().endswith("St. Petersburg, FL 33702")
    assert f"{a.title}, Trilles AI" in email.body
    assert main(["check"]) == 0


def test_simulation_respects_caps_and_no_repeats(capsys):
    import csv
    main(["simulate", "--days", "15", "--seed", "3"])
    rows = list(csv.DictReader(open(CFG.data_dir / "sim" / "daily.csv")))
    for r in rows:
        lo, hi = target_range(CFG, dt.date.fromisoformat(r["date"]))
        assert int(r["sent"]) <= min(hi, CFG.hard_daily_cap)
        assert int(r["replied"]) <= CFG.reply_daily_cap
        if lo >= 20:
            assert int(r["sent"]) >= lo  # per-inbox spacing leaves room for the whole target
    acts = list(csv.DictReader(open(CFG.data_dir / "sim" / "actions.csv")))
    sends = [(a["inbox"], a["subject"].lower()) for a in acts if a["action"] == "send" and a["status"] == "ok"]
    assert len(sends) == len(set(sends))  # 15 days < 14-day window + weekends: no subject repeats at all
    assert any(a["action"] == "reply" for a in acts)


def test_bounce_stops_everything(capsys):
    main(["simulate", "--days", "2", "--bounce", "kinza"])
    out = capsys.readouterr().out
    assert "ALERT" in out and "stopped by alert" in out


def test_old_plan_is_topped_up_midday():
    from warmup import gmail
    from warmup.logbook import Logbook
    from warmup.runner import Runner
    day = dt.date(2026, 11, 12)
    clock = [CFG.at(day, dt.time(10, 15))]
    world = gmail.FakeWorld(lambda: clock[0], spam_rate=0, rng=random.Random(1))
    clients = {k: gmail.FakeClient(world, i, CFG) for k, i in CFG.inboxes.items()}
    old = {"id": "20261112-awais-s0", "kind": "send", "inbox": "awais", "to": "kinza", "subject": "x",
           "at": CFG.at(day, dt.time(9, 30)).isoformat(), "done_at": CFG.at(day, dt.time(9, 30)).isoformat(),
           "status": "done", "template_id": "t", "values": {}, "body": "b"}
    pending = dict(old, id="20261112-awais-s1", status="planned", at=CFG.at(day, dt.time(11)).isoformat())
    state = {"days": {"2026-11-12": {"targets": {}, "planned": True, "rescued": {}}}, "actions": [old, pending],
             "handled": {}, "bounces": [], "seen_bounces": {}, "alert": None, "paused": {}}
    r = Runner(CFG, clients, state, Logbook(CFG.data_dir / "sim"), lambda: clock[0], True,
               out=lambda m: None, sleep=lambda s: None, rng=random.Random(2))
    planned = r.plan_day(day, clock[0])
    assert pending["status"] == "skipped"
    for key in CFG.inboxes:
        target = state["days"]["2026-11-12"]["targets"][key][0]
        mine = [a for a in planned if a["inbox"] == key]
        assert len(mine) == target - (1 if key == "awais" else 0)
        assert all(clock[0] < dt.datetime.fromisoformat(a["at"]) <= CFG.at(day, CFG.work_end()) for a in mine)
    assert r.plan_day(day, clock[0]) == []  # only once
