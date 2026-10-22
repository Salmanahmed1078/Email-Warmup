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
    assert target_range(CFG, dt.date(2026, 11, 5)) == (15, 25)
    assert target_range(CFG, dt.date(2026, 12, 1)) == (25, 35)
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
        assert int(r["sent"]) + int(r["replied"]) <= min(hi, CFG.hard_daily_cap)
    acts = list(csv.DictReader(open(CFG.data_dir / "sim" / "actions.csv")))
    sends = [(a["inbox"], a["subject"].lower()) for a in acts if a["action"] == "send" and a["status"] == "ok"]
    assert len(sends) == len(set(sends))  # 15 days < 14-day window + weekends: no subject repeats at all
    assert any(a["action"] == "reply" for a in acts)


def test_bounce_stops_everything(capsys):
    main(["simulate", "--days", "2", "--bounce", "kinza"])
    out = capsys.readouterr().out
    assert "ALERT" in out and "stopped by alert" in out
