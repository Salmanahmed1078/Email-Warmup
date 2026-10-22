"""Gmail access: real API client, dry-run wrapper, and an in-memory fake for simulation.

Secrets are read from secrets/ (client_secret.json, token_<inbox>.json) or, for hosted runners,
from env vars WARMUP_CLIENT_SECRET_JSON / WARMUP_TOKEN_<INBOX>_JSON (raw JSON or base64).
Nothing in this module prints or logs credential contents.
"""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import itertools
import json
import os
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path

from .config import Config, Inbox

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


@dataclass
class Msg:
    id: str
    thread_id: str
    sender: str          # bare email address
    to: str
    subject: str
    message_id: str      # RFC 822 Message-ID header
    received: dt.datetime
    labels: set[str] = field(default_factory=set)
    snippet: str = ""


# ---------------------------------------------------------------- credentials

def _env_json(name: str) -> dict | None:
    val = os.environ.get(name)
    if not val:
        return None
    val = val.strip()
    if not val.startswith("{"):
        try:
            val = base64.b64decode(val).decode()
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError(f"{name} is neither JSON nor base64 JSON") from exc
    return json.loads(val)


def scopes_for(cfg: Config, inbox_key: str) -> list[str]:
    s = list(GMAIL_SCOPES)
    sheets = cfg.raw.get("sheets", {})
    if sheets.get("enabled") and sheets.get("token_inbox") == inbox_key:
        s.append(SHEETS_SCOPE)
    return s


def token_path(cfg: Config, inbox_key: str) -> Path:
    return cfg.secrets_dir / f"token_{inbox_key}.json"


def has_credentials(cfg: Config, inbox_key: str) -> bool:
    return token_path(cfg, inbox_key).exists() or bool(os.environ.get(f"WARMUP_TOKEN_{inbox_key.upper()}_JSON"))


def load_credentials(cfg: Config, inbox_key: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = token_path(cfg, inbox_key)
    info = _env_json(f"WARMUP_TOKEN_{inbox_key.upper()}_JSON")
    from_file = info is None
    if from_file:
        if not path.exists():
            raise FileNotFoundError(f"no token for {inbox_key}; run: python -m warmup auth --inbox {inbox_key}")
        info = json.loads(path.read_text())
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if from_file:
                _write_private(path, creds.to_json())
        else:
            raise RuntimeError(f"token for {inbox_key} is invalid; re-run auth")
    return creds


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def run_auth(cfg: Config, inbox_key: str, port: int = 0) -> None:
    """Interactive OAuth consent for one inbox. Sign in as that inbox's account."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client = _env_json("WARMUP_CLIENT_SECRET_JSON")
    scopes = scopes_for(cfg, inbox_key)
    if client:
        flow = InstalledAppFlow.from_client_config(client, scopes)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(cfg.secrets_dir / "client_secret.json"), scopes)
    email = cfg.inboxes[inbox_key].email
    creds = flow.run_local_server(port=port, login_hint=email, prompt="consent", open_browser=True)
    _write_private(token_path(cfg, inbox_key), creds.to_json())
    print(f"Saved token for {inbox_key} ({email}) to {token_path(cfg, inbox_key).name}")


# ---------------------------------------------------------------- real client

def _build_mime(sender: Inbox, recipient: Inbox, subject: str, body: str,
                in_reply_to: str | None, references: str | None) -> EmailMessage:
    m = EmailMessage()
    m["From"] = formataddr((sender.full_name, sender.email))
    m["To"] = formataddr((recipient.full_name, recipient.email))
    m["Subject"] = subject
    m["Message-ID"] = make_msgid(domain=sender.email.split("@")[1])
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = references or in_reply_to
    m.set_content(body)  # text/plain only: no HTML, links, images or attachments
    return m


class GmailClient:
    def __init__(self, cfg: Config, inbox: Inbox):
        from googleapiclient.discovery import build

        self.inbox = inbox
        self.svc = build("gmail", "v1", credentials=load_credentials(cfg, inbox.key), cache_discovery=False)

    def _ids(self, q: str, spam: bool = False) -> list[str]:
        out, token = [], None
        while True:
            r = self.svc.users().messages().list(userId="me", q=q, includeSpamTrash=spam,
                                                 pageToken=token, maxResults=100).execute()
            out += [m["id"] for m in r.get("messages", [])]
            token = r.get("nextPageToken")
            if not token:
                return out

    def _meta(self, mid: str) -> Msg:
        r = self.svc.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["From", "To", "Subject", "Message-ID"]).execute()
        h = {x["name"].lower(): x["value"] for x in r["payload"].get("headers", [])}
        return Msg(
            id=r["id"], thread_id=r["threadId"],
            sender=parseaddr(h.get("from", ""))[1].lower(), to=parseaddr(h.get("to", ""))[1].lower(),
            subject=h.get("subject", ""), message_id=h.get("message-id", ""),
            received=dt.datetime.fromtimestamp(int(r["internalDate"]) / 1000, dt.timezone.utc),
            labels=set(r.get("labelIds", [])), snippet=r.get("snippet", ""))

    def search(self, q: str, spam: bool = False) -> list[Msg]:
        return [self._meta(i) for i in self._ids(q, spam)]

    def incoming_from(self, peers: list[str], days: int) -> list[Msg]:
        return self.search(f"from:({' OR '.join(peers)}) newer_than:{days}d")

    def misfiled_from(self, peers: list[str], days: int) -> list[Msg]:
        frm = f"from:({' OR '.join(peers)}) newer_than:{days}d"
        found = {m.id: m for m in self.search(f"in:spam {frm}", spam=True)}
        found.update({m.id: m for m in self.search(f"category:promotions {frm}")})
        return list(found.values())

    def bounces(self, days: int) -> list[Msg]:
        return self.search(f"from:(mailer-daemon OR postmaster) newer_than:{days}d", spam=True)

    def rescue(self, msg: Msg) -> None:
        """'Not spam' + move to Inbox (and out of Promotions into Primary)."""
        remove = [l for l in ("SPAM", "CATEGORY_PROMOTIONS") if l in msg.labels]
        self.svc.users().messages().modify(userId="me", id=msg.id, body={
            "addLabelIds": ["INBOX", "CATEGORY_PERSONAL"], "removeLabelIds": remove}).execute()

    def send(self, recipient: Inbox, subject: str, body: str, thread_id: str | None = None,
             in_reply_to: str | None = None) -> tuple[str, str]:
        mime = _build_mime(self.inbox, recipient, subject, body, in_reply_to, None)
        payload = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
        if thread_id:
            payload["threadId"] = thread_id
        r = self.svc.users().messages().send(userId="me", body=payload).execute()
        return r["id"], r["threadId"]


# ---------------------------------------------------------------- dry run

class DryRunClient:
    """Reads from a real client when credentials exist; never writes. Prints every write it skips."""

    _ids = itertools.count(1)

    def __init__(self, inbox: Inbox, inner=None, out=print):
        self.inbox, self.inner, self.out = inbox, inner, out

    def incoming_from(self, peers, days):
        return self.inner.incoming_from(peers, days) if self.inner else []

    def misfiled_from(self, peers, days):
        return self.inner.misfiled_from(peers, days) if self.inner else []

    def bounces(self, days):
        return self.inner.bounces(days) if self.inner else []

    def rescue(self, msg):
        self.out(f"[dry-run] {self.inbox.key}: would mark Not spam + move to Inbox: {msg.subject!r}")

    def send(self, recipient, subject, body, thread_id=None, in_reply_to=None):
        n = next(self._ids)
        return f"dry{n}", thread_id or f"drythread{n}"


# ---------------------------------------------------------------- simulation

class FakeWorld:
    """Shared in-memory mail system for `simulate` and tests."""

    def __init__(self, clock, spam_rate: float = 0.2, rng=None, bounce_to: set[str] | None = None):
        import random
        self.clock, self.spam_rate = clock, spam_rate
        self.rng = rng or random.Random(0)
        self.boxes: dict[str, list[Msg]] = {}
        self.bounce_to = bounce_to or set()
        self._n = itertools.count(1)

    def deliver(self, sender: Inbox, recipient: Inbox, subject, thread_id, rfc_id):
        n = next(self._n)
        if recipient.email in self.bounce_to:
            self.boxes.setdefault(sender.email, []).append(Msg(
                f"b{n}", f"bt{n}", "mailer-daemon@googlemail.com", sender.email,
                "Delivery Status Notification (Failure)", f"<b{n}@x>", self.clock(), {"INBOX"},
                "Address not found"))
            return
        labels = {"SPAM"} if self.rng.random() < self.spam_rate else {"INBOX", "CATEGORY_PERSONAL"}
        self.boxes.setdefault(recipient.email, []).append(Msg(
            f"m{n}", thread_id or f"t{n}", sender.email, recipient.email, subject, rfc_id, self.clock(), labels))


class FakeClient:
    def __init__(self, world: FakeWorld, inbox: Inbox, cfg: Config):
        self.world, self.inbox, self.cfg = world, inbox, cfg

    def _box(self):
        return self.world.boxes.setdefault(self.inbox.email, [])

    def _recent(self, days):
        cutoff = self.world.clock() - dt.timedelta(days=days)
        return [m for m in self._box() if m.received >= cutoff]

    def incoming_from(self, peers, days):
        return [m for m in self._recent(days) if m.sender in peers and "SPAM" not in m.labels]

    def misfiled_from(self, peers, days):
        return [m for m in self._recent(days) if m.sender in peers and m.labels & {"SPAM", "CATEGORY_PROMOTIONS"}]

    def bounces(self, days):
        return [m for m in self._recent(days) if m.sender.startswith("mailer-daemon")]

    def rescue(self, msg):
        msg.labels -= {"SPAM", "CATEGORY_PROMOTIONS"}
        msg.labels |= {"INBOX", "CATEGORY_PERSONAL"}

    def send(self, recipient, subject, body, thread_id=None, in_reply_to=None):
        n = next(self.world._n)
        rfc = f"<sim{n}@{self.inbox.email.split('@')[1]}>"
        self.world.deliver(self.inbox, recipient, subject, None, rfc)
        return f"s{n}", thread_id or f"st{n}"
