"""CSV logging (every action + one daily row per inbox) and optional Google Sheets scoreboard."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

ACTION_FIELDS = ["timestamp", "date", "inbox", "action", "counterpart", "subject", "status", "detail"]
DAILY_FIELDS = ["date", "inbox", "sent", "replied", "rescued_from_spam", "problems"]


class Logbook:
    def __init__(self, data_dir: Path):
        self.dir = data_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.actions = self.dir / "actions.csv"
        self.daily = self.dir / "daily.csv"

    def action(self, when: dt.datetime, inbox: str, action: str, counterpart: str = "",
               subject: str = "", status: str = "ok", detail: str = "") -> None:
        new = not self.actions.exists()
        with self.actions.open("a", newline="") as f:
            w = csv.DictWriter(f, ACTION_FIELDS)
            if new:
                w.writeheader()
            w.writerow({"timestamp": when.isoformat(timespec="seconds"), "date": when.date().isoformat(),
                        "inbox": inbox, "action": action, "counterpart": counterpart, "subject": subject,
                        "status": status, "detail": detail})

    def upsert_daily(self, rows: list[dict]) -> None:
        """Replace today's rows (keyed by date+inbox) and keep the rest."""
        keys = {(r["date"], r["inbox"]) for r in rows}
        old = []
        if self.daily.exists():
            with self.daily.open(newline="") as f:
                old = [r for r in csv.DictReader(f) if (r["date"], r["inbox"]) not in keys]
        with self.daily.open("w", newline="") as f:
            w = csv.DictWriter(f, DAILY_FIELDS)
            w.writeheader()
            w.writerows(sorted(old + rows, key=lambda r: (r["date"], r["inbox"])))


class SheetsSink:
    """Writes the daily numbers to the 'Daily Scoreboard' sheet. Errors are reported, never raised."""

    def __init__(self, cfg, creds):
        from googleapiclient.discovery import build

        self.cfg = cfg.raw["sheets"]
        self._new = lambda: build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

    def push(self, day: dt.date, rows: list[dict]) -> str | None:
        try:
            self.svc = self._new()  # fresh connection: pushes can come after long idle waits
            sid, tab = self.cfg["spreadsheet_id"], self.cfg["tab"]
            if self.cfg.get("mode", "upsert") == "upsert":
                rng = f"'{tab}'!A1:F2000"
                grid = self.svc.values().get(spreadsheetId=sid, range=rng).execute().get("values", [])
                if not grid:
                    grid = [DAILY_FIELDS]
                where = {(r[0], r[1]): i for i, r in enumerate(grid) if len(r) >= 2}
                for r in rows:
                    vals = [r[k] for k in DAILY_FIELDS]
                    i = where.get((r["date"], r["inbox"]))
                    if i is None:
                        grid.append(vals)
                    else:
                        grid[i] = vals
                self.svc.values().update(spreadsheetId=sid, range=f"'{tab}'!A1", valueInputOption="RAW",
                                         body={"values": grid}).execute()
                return None
            grid = self.svc.values().get(spreadsheetId=sid, range=f"'{tab}'!A1:ZZ200").execute().get("values", [])
            if not grid:
                return "scoreboard tab is empty"
            labels = {day.isoformat(), f"{day.month}/{day.day}", f"{day.month}/{day.day}/{day.year}",
                      day.strftime("%d-%b"), day.strftime("%b %d"), day.strftime("%-d %b")}
            col = next((i for i, v in enumerate(grid[0]) if str(v).strip() in labels), None)
            row = next((i for i, r in enumerate(grid) if r and str(r[0]).strip().lower() == self.cfg["row_label"].lower()), None)
            if col is None or row is None:
                return f"scoreboard: could not find row '{self.cfg['row_label']}' or a column for {day}"
            tot = {k: sum(int(r[k]) for r in rows) for k in ("sent", "replied", "rescued_from_spam")}
            probs = sum(1 for r in rows if r["problems"])
            cell = f"S {tot['sent']} / R {tot['replied']} / Sp {tot['rescued_from_spam']} / P {probs}"
            a1 = f"'{tab}'!{_col(col)}{row + 1}"
            self.svc.values().update(spreadsheetId=sid, range=a1, valueInputOption="USER_ENTERED",
                                     body={"values": [[cell]]}).execute()
            return None
        except Exception as exc:  # noqa: BLE001 - logging must never stop the warm-up
            return f"sheets error: {type(exc).__name__}"


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s
