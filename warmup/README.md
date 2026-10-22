# Trilles AI inbox warm-up

Automates inbox-to-inbox warm-up between awais@, salman@ and kinza@trilles-ai.com through the Gmail API.
Each email has one recipient. Sends go out in short bursts with 5-15 minute gaps, spread across working
hours. Every email gets an in-thread reply 20 minutes to 4 hours later. Warm-up mail found in Spam or
Promotions is moved back to Inbox. Any bounce or spam report stops all sending.
The emails come from a fixed pool (`warmup/pool.yaml`), so running costs no LLM tokens.

**Everything is a dry run unless you pass `--live`.**

## Setup (one time, about 20 minutes)

### 1. Google Cloud (no billing needed)
Sign in to console.cloud.google.com as salman@trilles-ai.com. If a "set up organization/billing" wizard
appears, close it.
1. Create a project, for example `trilles-warmup`.
2. APIs & Services > Library: enable **Gmail API** and **Google Sheets API**.
3. OAuth consent screen: User type **Internal**, with the app name, support email and developer email.
   Scopes: `.../auth/gmail.modify` and `.../auth/spreadsheets`.
4. Credentials > Create credentials > OAuth client ID > **Desktop app**. Download the JSON.
5. If Workspace Admin > Security > API controls blocks unconfigured apps, mark this app as **Trusted**.

### 2. Sign in each inbox (on your own computer, Python 3.10+)
```bash
git clone https://github.com/Salmanahmed1078/Email-Warmup && cd Email-Warmup/warmup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# save the downloaded JSON as warmup/secrets/client_secret.json
.venv/bin/python -m warmup auth --inbox salman   # browser opens: sign in as salman@, click Allow
.venv/bin/python -m warmup auth --inbox awais    # sign in as awais@ (use a private window if needed)
.venv/bin/python -m warmup auth --inbox kinza    # sign in as kinza@
.venv/bin/python -m warmup check                 # all three tokens should show "present"
.venv/bin/python -m warmup tick                  # dry run against the real inboxes: reads only
```
Tokens are written to `secrets/token_<inbox>.json` (gitignored, mode 600). Never paste them into chat.

### 3. GitHub Actions secrets (the runner that sends without you)
GitHub > repo **Settings > Secrets and variables > Actions > New repository secret**. Add four secrets.
Each value is the full content of the file:

| Secret name | Value |
|---|---|
| `WARMUP_TOKEN_SALMAN_JSON` | contents of `secrets/token_salman.json` |
| `WARMUP_TOKEN_AWAIS_JSON` | contents of `secrets/token_awais.json` |
| `WARMUP_TOKEN_KINZA_JSON` | contents of `secrets/token_kinza.json` |
| `WARMUP_STATE_KEY` | any long random password (it encrypts the saved state and logs) |

The token files hold the OAuth client ID and secret, so no separate client secret is needed.
The workflow `.github/workflows/warmup.yml` runs every 5 minutes on weekdays. It starts in **dry-run**.
To send for real, set `github_actions_live: true` in `config.yaml`. State and logs go to the
`warmup-state` branch, encrypted. The public Actions log only shows counts. The Google Sheet
("warm-up" tab) gets one row per inbox per day.

### Running on your own server instead
Use `deploy/crontab.txt` or the systemd units in `deploy/`, with `tick --live` every 5 minutes.

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
