"""Load and validate config.yaml."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Inbox:
    key: str
    email: str
    full_name: str
    title: str

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0]


@dataclass
class Config:
    raw: dict
    tz: ZoneInfo
    start_date: dt.date
    inboxes: dict[str, Inbox]
    root: Path = ROOT
    secrets_dir: Path = field(default=ROOT / "secrets")
    data_dir: Path = field(default=ROOT / "data")

    def __getattr__(self, name):  # convenience: cfg.hard_daily_cap etc.
        try:
            return self.raw[name]
        except KeyError:
            raise AttributeError(name) from None

    def work_start(self) -> dt.time:
        return dt.time.fromisoformat(self.raw["working_hours"]["start"])

    def work_end(self) -> dt.time:
        return dt.time.fromisoformat(self.raw["working_hours"]["end"])

    def at(self, day: dt.date, t: dt.time) -> dt.datetime:
        return dt.datetime.combine(day, t, tzinfo=self.tz)


def load(path: str | Path | None = None) -> Config:
    path = Path(path) if path else ROOT / "config.yaml"
    raw = yaml.safe_load(path.read_text())
    inboxes = {k: Inbox(k, v["email"], v["full_name"], v["title"]) for k, v in raw["inboxes"].items()}
    if len(inboxes) < 2:
        raise ValueError("need at least two inboxes")
    start = raw["start_date"]
    if isinstance(start, str):
        start = dt.date.fromisoformat(start)
    base = path.resolve().parent
    paths = raw.get("paths", {})
    return Config(
        raw=raw,
        tz=ZoneInfo(raw["timezone"]),
        start_date=start,
        inboxes=inboxes,
        root=base,
        secrets_dir=base / paths.get("secrets_dir", "secrets"),
        data_dir=base / paths.get("data_dir", "data"),
    )
