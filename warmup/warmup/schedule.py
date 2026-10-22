"""Warm-up calendar: today's per-inbox target range, shifted by start_date."""
from __future__ import annotations

import datetime as dt

from .config import Config


def week_number(cfg: Config, day: dt.date) -> int:
    """1-based warm-up week; 0 means before the start date."""
    delta = (day - cfg.start_date).days
    return 0 if delta < 0 else delta // 7 + 1


def is_working_day(cfg: Config, day: dt.date) -> bool:
    return not cfg.weekdays_only or day.weekday() < 5


def target_range(cfg: Config, day: dt.date) -> tuple[int, int]:
    """(min, max) emails per inbox for this day, never above the hard cap."""
    week = week_number(cfg, day)
    if week == 0 or not is_working_day(cfg, day):
        return (0, 0)
    rows = sorted(cfg.calendar, key=lambda r: r["week"])
    lo, hi = rows[-1]["range"]
    for row in rows:
        if week <= row["week"]:
            lo, hi = row["range"]
            break
    cap = cfg.hard_daily_cap
    return (min(lo, cap), min(hi, cap))
