# Trilles AI inbox warm-up

Automates inbox-to-inbox warm-up between awais@, salman@ and kinza@trilles-ai.com through the Gmail API.
Each email has one recipient. Sends go out in short bursts with 5-15 minute gaps, spread across working
hours. Every email gets an in-thread reply 20 minutes to 4 hours later. Warm-up mail found in Spam or
Promotions is moved back to Inbox. Any bounce or spam report stops all sending.
The emails come from a fixed pool (`warmup/pool.yaml`), so running costs no LLM tokens.

**Everything is a dry run unless you pass `--live`.**

## Setup

```bash
cd warmup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m warmup check          # validates pool, config, shows which tokens are missing
```

1. Fill in names and titles in `config.yaml` (they are used in the signature).
2. Put the OAuth client file in `secrets/client_secret.json` (Desktop-app OAuth client, Gmail API enabled).
3. Sign in once per inbox (opens a browser, sign in as that inbox):
   ```bash
   .venv/bin/python -m warmup auth --inbox awais
   .venv/bin/python -m warmup auth --inbox salman
   .venv/bin/python -m warmup auth --inbox kinza
   ```
   Tokens land in `secrets/token_<inbox>.json` (gitignored, mode 600). On hosted runners you can instead
   set `WARMUP_CLIENT_SECRET_JSON` and `WARMUP_TOKEN_<INBOX>_JSON` env vars (raw or base64 JSON).

## Try it without sending anything

```bash
python -m warmup plan --date 2026-10-23 --show-body   # preview a day's plan
python -m warmup simulate --days 10                   # whole days against a fake Gmail
python -m warmup simulate --days 2 --bounce kinza     # see the bounce alert stop everything
python -m warmup tick                                 # dry run against real inboxes (reads only)
python -m pytest -q tests
```

## Go live

```bash
python -m warmup tick --live         # run every 5 minutes from cron/systemd (see deploy/)
python -m warmup status --live       # today's planned/done actions
python -m warmup clear-alert --live  # resume after you have investigated an alert
```

Cron: `deploy/crontab.txt`. Systemd: copy `deploy/warmup.service` and `deploy/warmup.timer` to
`/etc/systemd/system/` and run `systemctl enable --now warmup.timer`. You can also run `run-day --live`
once each morning as a single long-running process.

## Rules it enforces

| Rule | Where |
|---|---|
| Daily target from the calendar, shifted by `start_date` | `schedule.py`, `config.yaml` |
| About 60% of the target is new emails and the rest is replies. Hard cap per inbox per day | `runner.plan_day`, `runner._send` |
| One recipient per email, plain text only, no links/images/attachments, signature on every mail | `gmail._build_mime`, `content.py` |
| Bursts with 5-15 min gaps spread over working hours. Minimum gap also enforced after downtime | `runner.spread_times`, `execute_due` |
| No repeated subject per inbox within 14 days | `content.pick_email` |
| Replies only to warm-up mail we sent, in-thread, 20 min-4 h later, inside working hours | `runner.schedule_replies` |
| Spam/Promotions rescue every run ("Not spam" + Inbox) | `runner.rescue` |
| Any bounce or spam report stops all sending and writes `data/live/ALERT.txt`. Bounce rate above 2% over 7 days pauses that inbox for 7 days | `runner.check_bounces` |

"Spam report" is detected from bounce/rejection notices (5.7.x, blocked, policy). Gmail does not expose
recipient spam complaints through the API. For those, watch Google Postmaster Tools.

## Logs

- `data/live/actions.csv`: every send, reply, rescue and problem.
- `data/live/daily.csv`: one row per inbox per day: date, inbox, sent, replied, rescued_from_spam, problems.
- Google Sheets (optional): set `sheets.enabled: true` and `spreadsheet_id` in `config.yaml`, then re-run
  `auth` for `sheets.token_inbox` so its token carries the Sheets scope.
