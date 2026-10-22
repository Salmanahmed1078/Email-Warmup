"""Render warm-up emails and replies from pool.yaml."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import Config, Inbox

POOL_PATH = Path(__file__).with_name("pool.yaml")
_FORBIDDEN = re.compile(r"(https?://|www\.|\.(com|net|org|io|ai)\b|<img|\[image|\btest\b)", re.I)
_SENTENCE = re.compile(r"[.!?](\s|$)")


@dataclass
class Email:
    template_id: str
    subject: str
    body: str


def load_pool(path: Path = POOL_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def signature(cfg: Config, sender: Inbox) -> str:
    return f"{sender.full_name}\n{sender.title}, {cfg.company}\n{cfg.address}"


def _fill(text: str, values: dict) -> str:
    return text.format(**values)


def check_clean(text: str) -> None:
    """Weeks 1-2 rule (applied always): no links, images or 'test' wording."""
    m = _FORBIDDEN.search(text)
    if m:
        raise ValueError(f"forbidden content {m.group(0)!r} in: {text[:60]}")


def sentence_count(text: str) -> int:
    return len(_SENTENCE.findall(text.strip()))


def render_email(cfg: Config, pool: dict, tpl: dict, sender: Inbox, recipient: Inbox,
                 rng: random.Random) -> tuple[Email, dict]:
    values = {k: rng.choice(v) for k, v in pool["fills"].items()}
    values["first"] = recipient.first_name
    subject = _fill(rng.choice(tpl["subjects"]), values)
    greeting = _fill(rng.choice(pool["greetings"]), values)
    body = " ".join(_fill(tpl["body"], values).split())
    text = f"{greeting}\n\n{body}\n\n{rng.choice(pool['signoffs'])}\n{signature(cfg, sender)}\n"
    check_clean(subject)
    check_clean(body)
    return Email(tpl["id"], subject, text), values


def render_reply(cfg: Config, pool: dict, template_id: str, values: dict, sender: Inbox,
                 recipient: Inbox, rng: random.Random) -> str:
    tpl = next(t for t in pool["templates"] if t["id"] == template_id)
    vals = dict(values, first=recipient.first_name)
    line = _fill(rng.choice(tpl["replies"]), vals)
    opener = rng.choice(["", f"Hi {recipient.first_name},\n\n", f"{recipient.first_name},\n\n"])
    text = f"{opener}{line}\n\n{rng.choice(pool['reply_signoffs'])}\n{signature(cfg, sender)}\n"
    check_clean(line)
    return text


def pick_email(cfg: Config, pool: dict, sender: Inbox, recipient: Inbox, rng: random.Random,
               used_subjects: set[str], recent_templates: list[str], weekday: int | None = None) -> tuple[Email, dict]:
    """Choose an email whose subject this sender has not used in the no-repeat window.

    Templates the sender used least recently are preferred, so topics rotate before subjects repeat.
    """
    templates = [t for t in pool["templates"] if weekday is None or weekday in t.get("weekdays", range(7))]
    rng.shuffle(templates)
    rank = {tid: i for i, tid in enumerate(recent_templates)}  # higher index = used more recently
    templates.sort(key=lambda t: rank.get(t["id"], -1))
    for tpl in templates:
        for _ in range(8):
            email, values = render_email(cfg, pool, tpl, sender, recipient, rng)
            if email.subject.lower() not in used_subjects:
                return email, values
    raise RuntimeError(f"no unused subject left for {sender.key}; enlarge pool.yaml")
