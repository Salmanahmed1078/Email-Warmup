"""One warm-up 'tick': plan the day, check bounces, rescue spam, schedule replies, send what is due.

Safe to run as often as you like (cron every 5 minutes is the intended setup); every step is idempotent.
"""
from __future__ import annotations

import datetime as dt
import math
import random
import re
import time

from . import content
from .config import Config
from .logbook import Logbook
from .schedule import is_working_day, target_range, week_number

SPAM_REPORT = re.compile(r"spam|blocked|block list|blacklist|policy|5\.7\.\d|unsolicited", re.I)
KEEP_DAYS = 30


class Runner:
    def __init__(self, cfg: Config, clients: dict, state: dict, log: Logbook, clock, live: bool,
                 out=print, sleep=time.sleep, rng: random.Random | None = None, sheets=None):
        self.cfg, self.clients, self.s, self.log = cfg, clients, state, log
        self.clock, self.live, self.out, self.sleep = clock, live, out, sleep
        self.rng = rng or random.SystemRandom()
        self.sheets = sheets
        self.pool = content.load_pool()
        self.tag = "" if live else "[dry-run] "

    # ------------------------------------------------------------ helpers
    def now(self) -> dt.datetime:
        return self.clock().astimezone(self.cfg.tz)

    def _day(self, day: dt.date) -> dict:
        return self.s["days"].setdefault(day.isoformat(), {"targets": {}, "planned": False, "rescued": {}})

    def _problem(self, day: dt.date, inbox: str, text: str) -> None:
        self.s["problems"].setdefault(day.isoformat(), {}).setdefault(inbox, []).append(text)
        self.log.action(self.now(), inbox, "problem", status="problem", detail=text)
        self.out(f"{self.tag}PROBLEM {inbox}: {text}")

    def paused(self, inbox: str, day: dt.date) -> bool:
        until = self.s["paused"].get(inbox)
        return bool(until) and day < dt.date.fromisoformat(until)

    def _done_today(self, inbox: str, day: dt.date) -> int:
        d = day.isoformat()
        return sum(1 for a in self.s["actions"]
                   if a["inbox"] == inbox and a["status"] == "done" and a["done_at"][:10] == d)

    # ------------------------------------------------------------ planning
    def plan_day(self, day: dt.date, now: dt.datetime) -> list[dict]:
        cfg, rng = self.cfg, self.rng
        info = self._day(day)
        if info["planned"]:
            return []
        info["planned"] = True
        lo, hi = target_range(cfg, day)
        start = max(cfg.at(day, cfg.work_start()), now + dt.timedelta(minutes=2))
        end = cfg.at(day, cfg.work_end()) - dt.timedelta(minutes=45)  # leave room for same-day replies
        senders = []
        for key in cfg.inboxes:
            if self.paused(key, day) or hi == 0:
                info["targets"][key] = [0, lo, hi]
                continue
            target = rng.randint(lo, hi)
            info["targets"][key] = [target, lo, hi]
            senders += [key] * max(1, math.ceil(target * 0.6))  # the rest of the target is replies
        senders = _interleave(senders, rng)
        times = spread_times(len(senders), start, end, cfg.gap_minutes, rng)
        senders = senders[:len(times)]
        cutoff = (day - dt.timedelta(days=cfg.no_repeat_days)).isoformat()
        pair_count: dict = {}
        planned = []
        for i, (sender_key, at) in enumerate(zip(senders, times)):
            sender = cfg.inboxes[sender_key]
            others = [k for k in cfg.inboxes if k != sender_key]
            others.sort(key=lambda k: (pair_count.get((sender_key, k), 0), rng.random()))
            rcpt = cfg.inboxes[others[0]]
            pair_count[(sender_key, rcpt.key)] = pair_count.get((sender_key, rcpt.key), 0) + 1
            mine = [a for a in self.s["actions"] if a["inbox"] == sender_key and a["kind"] == "send"
                    and a["at"][:10] >= cutoff and a["status"] != "skipped"]
            used = {a["subject"].lower() for a in mine}
            recent = [a["template_id"] for a in sorted(mine, key=lambda a: a["at"])]
            email, values = content.pick_email(cfg, self.pool, sender, rcpt, rng, used, recent, day.weekday())
            action = {"id": f"{day:%Y%m%d}-{sender_key}-s{i}", "kind": "send", "inbox": sender_key,
                      "to": rcpt.key, "at": at.isoformat(), "subject": email.subject, "body": email.body,
                      "template_id": email.template_id, "values": values, "status": "planned"}
            self.s["actions"].append(action)
            planned.append(action)
        self.out(f"{self.tag}Plan {day} (week {week_number(cfg, day)}, range {lo}-{hi}): "
                 + ", ".join(f"{k} target {v[0]}" for k, v in info["targets"].items())
                 + f"; {len(planned)} new emails between {times[0]:%H:%M} and {times[-1]:%H:%M}"
                 if planned else f"{self.tag}Plan {day}: nothing to send (range {lo}-{hi})")
        return planned

    # ------------------------------------------------------------ safety
    def check_bounces(self, day: dt.date) -> None:
        cfg, new = self.cfg, []
        for key, client in self.clients.items():
            seen = self.s["seen_bounces"].setdefault(key, [])
            for m in client.bounces(cfg.lookback_days):
                if m.id in seen:
                    continue
                seen.append(m.id)
                kind = "spam_report" if SPAM_REPORT.search(f"{m.subject} {m.snippet}") else "bounce"
                self.s["bounces"].append({"inbox": key, "id": m.id, "at": self.now().isoformat(), "kind": kind})
                new.append((key, kind))
                self._problem(day, key, f"{kind} received: {m.subject[:60]}")
        if not new:
            return
        week_ago = (self.now() - dt.timedelta(days=7)).isoformat()
        for key in {k for k, _ in new}:
            sent = sum(1 for a in self.s["actions"] if a["inbox"] == key and a["status"] == "done"
                       and a["done_at"] >= week_ago)
            bounced = sum(1 for b in self.s["bounces"] if b["inbox"] == key and b["at"] >= week_ago)
            rate = bounced / max(sent, 1)
            if rate > cfg.bounce_pause_threshold:
                until = day + dt.timedelta(days=cfg.pause_days)
                self.s["paused"][key] = until.isoformat()
                self._problem(day, key, f"bounce rate {rate:.1%} > {cfg.bounce_pause_threshold:.0%}; paused until {until}")
        reason = "; ".join(f"{k}: {kind}" for k, kind in new)
        self.s["alert"] = {"at": self.now().isoformat(), "reason": reason}
        self._write_alert(reason)

    def _write_alert(self, reason: str) -> None:
        path = self.log.dir / "ALERT.txt"
        path.write_text(f"{self.now().isoformat()} STOPPED: {reason}\n"
                        "Investigate, then run: python -m warmup clear-alert\n")
        self.out(f"{self.tag}ALERT - all sending stopped: {reason}")

    # ------------------------------------------------------------ spam rescue
    def rescue(self, day: dt.date) -> None:
        info = self._day(day)
        emails = {k: i.email for k, i in self.cfg.inboxes.items()}
        for key, client in self.clients.items():
            peers = [e for k, e in emails.items() if k != key]
            found = client.misfiled_from(peers, 7)
            for m in found:
                client.rescue(m)
                where = "spam" if "SPAM" in m.labels else "promotions"
                self.log.action(self.now(), key, "rescue", m.sender, m.subject, "dry-run" if not self.live else "ok", where)
            info["rescued"][key] = info["rescued"].get(key, 0) + len(found)
            if found:
                self.out(f"{self.tag}{key}: rescued {len(found)} warm-up email(s) from Spam/Promotions")

    # ------------------------------------------------------------ replies
    def schedule_replies(self, day: dt.date) -> None:
        cfg, now = self.cfg, self.now()
        by_email = {i.email: k for k, i in cfg.inboxes.items()}
        for key, client in self.clients.items():
            handled = self.s["handled"].setdefault(key, {})
            peers = [i.email for k, i in cfg.inboxes.items() if k != key]
            for m in client.incoming_from(peers, cfg.lookback_days):
                if m.id in handled:
                    continue
                handled[m.id] = day.isoformat()
                if m.subject.lower().startswith("re:"):
                    continue  # one reply per thread, never reply to a reply
                sender_key = by_email.get(m.sender)
                orig = next((a for a in self.s["actions"] if a["kind"] == "send" and a["status"] == "done"
                             and a["inbox"] == sender_key and a["to"] == key
                             and a["subject"].lower() == m.subject.lower() and not a.get("reply_id")), None)
                if orig is None:
                    continue  # not a warm-up email we sent: leave it for a human
                due = m.received.astimezone(cfg.tz) + dt.timedelta(minutes=self.rng.uniform(*cfg.reply_delay_minutes))
                due = self._within_hours(max(due, now + dt.timedelta(minutes=self.rng.uniform(2, 10))))
                me, them = cfg.inboxes[key], cfg.inboxes[sender_key]
                body = content.render_reply(cfg, self.pool, orig["template_id"], orig["values"], me, them, self.rng)
                reply = {"id": f"{orig['id']}-r", "kind": "reply", "inbox": key, "to": sender_key,
                         "at": due.isoformat(), "subject": "Re: " + m.subject, "body": body,
                         "template_id": orig["template_id"], "thread_id": m.thread_id,
                         "in_reply_to": m.message_id, "status": "planned"}
                orig["reply_id"] = reply["id"]
                self.s["actions"].append(reply)
                self.out(f"{self.tag}{key}: reply to {sender_key} '{m.subject}' scheduled {due:%a %H:%M}")

    def _within_hours(self, t: dt.datetime) -> dt.datetime:
        cfg = self.cfg
        day = t.date()
        if is_working_day(cfg, day) and cfg.at(day, cfg.work_start()) <= t <= cfg.at(day, cfg.work_end()):
            return t
        if t >= cfg.at(day, cfg.work_start()):
            day += dt.timedelta(days=1)
        while not is_working_day(cfg, day):
            day += dt.timedelta(days=1)
        return cfg.at(day, cfg.work_start()) + dt.timedelta(minutes=self.rng.uniform(5, 90))

    # ------------------------------------------------------------ sending
    def execute_due(self, day: dt.date, window_min: float = 0) -> None:
        cfg = self.cfg
        deadline = self.now() + dt.timedelta(minutes=window_min)
        while True:
            if self.s["alert"]:
                return
            pending = sorted((a for a in self.s["actions"] if a["status"] == "planned"), key=lambda a: a["at"])
            a = next((x for x in pending if dt.datetime.fromisoformat(x["at"]) <= deadline), None)
            if a is None:
                return
            at = dt.datetime.fromisoformat(a["at"])
            if at.date() < day:
                self._finish(a, "skipped", "missed its day (runner was not running)")
                continue
            if at > self.now():
                self.sleep((at - self.now()).total_seconds())
            # spacing: never two sends closer than the minimum gap, even after downtime
            last = self.s.get("last_send_at")
            gap_lo = cfg.gap_minutes[0]
            if last and self.now() - dt.datetime.fromisoformat(last) < dt.timedelta(minutes=gap_lo):
                a["at"] = (dt.datetime.fromisoformat(last)
                           + dt.timedelta(minutes=self.rng.uniform(*cfg.gap_minutes))).isoformat()
                continue
            self._send(a, day)

    def _send(self, a: dict, day: dt.date) -> None:
        cfg = self.cfg
        key = a["inbox"]
        target, lo, hi = self._day(day)["targets"].get(key, [0, *target_range(cfg, day)])
        limit = min(cfg.hard_daily_cap, target if a["kind"] == "send" else max(hi, target))
        if self.paused(key, day):
            return self._finish(a, "skipped", "inbox paused")
        if self._done_today(key, day) >= limit:
            return self._finish(a, "skipped", f"daily limit {limit} reached")
        rcpt = cfg.inboxes[a["to"]]
        try:
            gid, tid = self.clients[key].send(rcpt, a["subject"], a["body"], a.get("thread_id"), a.get("in_reply_to"))
        except Exception as exc:  # noqa: BLE001
            self._problem(day, key, f"send failed: {type(exc).__name__}: {str(exc)[:120]}")
            return self._finish(a, "failed", type(exc).__name__)
        a["gmail_id"], a["sent_thread"] = gid, tid
        self.s["last_send_at"] = self.now().isoformat()
        self._finish(a, "done")
        self.out(f"{self.tag}{self.now():%H:%M} {key} -> {a['to']} {a['kind']}: {a['subject']!r} "
                 f"({len(a['body'].split())} words)")

    def _finish(self, a: dict, status: str, detail: str = "") -> None:
        a["status"], a["done_at"] = status, self.now().isoformat()
        if detail:
            a["detail"] = detail
        shown = status if self.live or status != "done" else "dry-run"
        self.log.action(self.now(), a["inbox"], a["kind"], self.cfg.inboxes[a["to"]].email, a["subject"], shown, detail)

    # ------------------------------------------------------------ reporting
    def daily_rows(self, day: dt.date) -> list[dict]:
        d, rows = day.isoformat(), []
        info = self._day(day)
        for key in self.cfg.inboxes:
            done = [a for a in self.s["actions"] if a["inbox"] == key and a["status"] == "done" and a["done_at"][:10] == d]
            rows.append({"date": d, "inbox": key,
                         "sent": sum(a["kind"] == "send" for a in done),
                         "replied": sum(a["kind"] == "reply" for a in done),
                         "rescued_from_spam": info["rescued"].get(key) or 0,
                         "problems": " | ".join(self.s["problems"].get(d, {}).get(key, []))})
        return rows

    def report(self, day: dt.date) -> None:
        rows = self.daily_rows(day)
        self.log.upsert_daily(rows)
        if not (self.sheets and self.live):
            return
        err = self.sheets.push(day, rows)
        if err:
            self.out(f"{self.tag}{err}")

    def prune(self) -> None:
        cutoff = (self.now() - dt.timedelta(days=KEEP_DAYS)).date().isoformat()
        self.s["actions"] = [a for a in self.s["actions"] if a["at"][:10] >= cutoff]
        for key in ("days", "problems"):
            self.s[key] = {d: v for d, v in self.s[key].items() if d >= cutoff}
        for key, h in self.s["handled"].items():
            self.s["handled"][key] = {m: d for m, d in h.items() if d >= cutoff}
        for key, seen in self.s["seen_bounces"].items():
            self.s["seen_bounces"][key] = seen[-500:]

    # ------------------------------------------------------------ entry point
    def tick(self, window_min: float = 0) -> int:
        """Returns 2 on the run that raises a new alert (so cron/CI reports a failure once), else 0."""
        now = self.now()
        day = now.date()
        if self.s["alert"]:
            self.out(f"{self.tag}STOPPED by alert ({self.s['alert']['reason']}). Run 'clear-alert' after checking.")
            return 0
        if not is_working_day(self.cfg, day) or week_number(self.cfg, day) == 0:
            self.out(f"{self.tag}{day} is not a warm-up day; nothing to do")
            return 0
        self.plan_day(day, now)
        self.check_bounces(day)
        if self.s["alert"]:
            self.report(day)
            return 2
        if now >= self.cfg.at(day, self.cfg.work_start()):
            self.rescue(day)
        self.schedule_replies(day)
        self.execute_due(day, window_min)
        self.report(day)
        self.prune()
        return 2 if self.s["alert"] else 0

    def next_due(self) -> dt.datetime | None:
        times = [dt.datetime.fromisoformat(a["at"]) for a in self.s["actions"] if a["status"] == "planned"]
        return min(times) if times else None


def _interleave(items: list[str], rng: random.Random) -> list[str]:
    """Shuffle so the same inbox rarely sends twice in a row."""
    rng.shuffle(items)
    out: list[str] = []
    rest = items[:]
    while rest:
        choices = [i for i, x in enumerate(rest) if not out or x != out[-1]] or [0]
        out.append(rest.pop(rng.choice(choices)))
    return out


def spread_times(n: int, start: dt.datetime, end: dt.datetime, gap: list[float],
                 rng: random.Random) -> list[dt.datetime]:
    """n send times in [start, end]: short bursts with 5-15 min gaps, bursts spread over the day."""
    if n <= 0 or end <= start:
        return []
    avail = (end - start).total_seconds() / 60
    lo, hi = gap
    n = min(n, int(avail // lo) + 1)
    gaps = [rng.uniform(lo, hi) for _ in range(n - 1)]
    if sum(gaps) > avail:  # very full day: squeeze gaps towards the minimum
        excess, room = sum(gaps) - avail, sum(g - lo for g in gaps)
        gaps = [g - (g - lo) * excess / room for g in gaps]
    slack = avail - sum(gaps)
    bursts = max(1, math.ceil(n / 3))
    weights = [rng.uniform(0.3, 1.0) for _ in range(bursts + 1)]  # lead-in, breaks between bursts, tail
    parts = [slack * w / sum(weights) for w in weights]
    breaks = {round(i * n / bursts) - 1: parts[i] for i in range(1, bursts)}
    t = start + dt.timedelta(minutes=parts[0])
    times = [t]
    for i, g in enumerate(gaps):
        t += dt.timedelta(minutes=g + breaks.get(i, 0))
        times.append(t)
    return [x.replace(microsecond=0) for x in times]
