# Gmail Warm-Up Playbook

How we warm up new Google Workspace mailboxes for cold outreach: fully automatic, free to run, no third-party warm-up tool, and no LLM tokens at run time.

> Written from a live build (Oct–Nov 2026) for three mailboxes on one domain. Every number, rule and mistake below comes from that run.

---

## 1. What this is, in one minute

Cold email only lands in the inbox if the sending domain and mailboxes have a **reputation**. A brand-new mailbox has none, so Gmail, Outlook and Yahoo treat its first emails with suspicion.

**Warm-up** builds that reputation before any cold email is sent. A small group of our own mailboxes send each other (and a few outside addresses) believable business emails, reply to each other, and rescue anything that lands in spam, ramping volume up slowly over about four weeks.

What we built:

| Piece | What it does |
|---|---|
| **Gmail API + OAuth** | Sends and reads mail from each mailbox as the real user. No SMTP passwords. |
| **Template pool** | 45 hand-written emails with several replies each. Fixed text means zero AI cost at run time. |
| **Python tool** (`warmup/`) | Plans each day, sends, replies, rescues spam, watches for bounces. |
| **GitHub Actions** | Runs the tool on a schedule. Free. |
| **cron-job.org** | A free external timer that triggers GitHub Actions every hour, because GitHub's own cron is unreliable. |
| **Google Sheet** | One row per mailbox per day: sent, replied, rescued, problems. |
| **Claude (monitor)** | Checks the runs and the sheet every ~hour and alerts on any failure. |

Cost: **$0** beyond the Workspace seats you already pay for.

---

## 2. The plan (per mailbox, per day)

| Week | Emails per mailbox per day | Notes |
|---|---|---|
| 1 | 5–10 | No links, attachments or images. |
| 2 | 10–15 | Still no links, attachments or images. |
| 3 | 15–25 *(we raised it to 20–30)* | Cold email allowed by the plan, but start small. |
| 4+ | 25–35 *(we run 20–30 new emails + replies on top)* | Hard caps: **30** new emails and **25** replies. |

From week 4 we count **new emails only**; replies come on top. Each mailbox keeps its own 5–15 minute gap between its sends (a gap shared by all mailboxes limits the whole group to ~45 emails a day).

Working days only, Monday to Friday, 09:00–17:00 in the company timezone.

Expect **about four weeks** from the first send until the mailboxes are ready for small cold campaigns.

---

## 3. The safety rules (these matter more than the volume)

1. **One recipient per email.** Never mass-send.
2. **5–15 minute gaps** between sends from the same mailbox, randomised.
3. **Replies come 20 minutes to 4 hours later**, only inside working hours, and only to mail the tool itself sent.
4. **No subject repeated** by the same mailbox within 14 days.
5. **Every email ends with a plain-text signature**: name, title, company, postal address.
6. **No links, images or attachments** in weeks 1–2.
7. **Daily spam rescue**: anything the tool sent that lands in Spam or Promotions is moved to the Inbox and marked "Not spam".
8. **Hard stop on trouble**: any bounce or spam-report notice stops *all* sending and raises an alert. If the bounce rate goes above **2%**, that mailbox is paused for 7 days.
9. **Dry-run first.** The tool never sends for real unless it is told to (`--live`). Test before going live.
10. **Never speed up to "catch up".** If days are missed, the schedule slips; it does not jump.

---

## 4. How it works

```
cron-job.org (hourly)
        │  POST  /actions/workflows/warmup.yml/dispatches
        ▼
GitHub Actions run (50-minute window)
        │  1. restore encrypted state
        │  2. plan today's emails (if not planned yet)
        │  3. check bounces  → stop + alert if any
        │  4. rescue spam, schedule replies
        │  5. send whatever is due, with random gaps
        │  6. write the day's row to the Google Sheet
        │  7. save encrypted state
        ▼
Gmail API  →  the mailboxes  →  (replies come back, next run answers them)
```

Key design choices:

- **State is encrypted** (AES-256) and kept on a separate branch. The public log shows only counts, never addresses or subjects.
- **Secrets live only in GitHub encrypted secrets**: one OAuth refresh token per mailbox, plus the state key. Nothing secret is in the repo.
- **No double-sending**: runs are serialised (a concurrency group), so two overlapping runs wait in line.
- **Time zones**: the schedule is in the company timezone. Remember the daylight-saving change, which shifts the UTC window by one hour.
- **Outside addresses ("seeds")**: a share of new sends (25% for us) goes to extra addresses we own, such as a few Gmail accounts and mailboxes on our other domains. They are send-only: a human replies by hand. The tool never logs in to them.

---

## 5. Setup checklist (about 2 hours the first time)

### A. Domain and mailboxes
- [ ] Domain bought and Google Workspace set up with the mailboxes.
- [ ] MX records point to Google. Use the standard five (`ASPMX.L.GOOGLE.COM` and the four ALT hosts), or Google's single `SMTP.GOOGLE.COM`.
- [ ] **SPF**: `v=spf1 include:_spf.google.com ~all`
- [ ] **DKIM**: generated in Google Admin (Apps → Google Workspace → Gmail → Authenticate email), published as **one** TXT record at `google._domainkey`, then **Start authentication**.
- [ ] **DMARC**: start with `v=DMARC1; p=none; rua=mailto:<a mailbox you read>`.

### B. Google Cloud OAuth (no billing needed)
- [ ] Create a Google Cloud project (Workspace users get one without an organisation or billing).
- [ ] Enable the **Gmail API** and the **Google Sheets API**.
- [ ] Consent screen: set it to **Internal**.
- [ ] Create an **OAuth client ID** of type *Web application*. Add `https://developers.google.com/oauthplayground` as an authorised redirect URI.
- [ ] Scopes: `gmail.modify` and `spreadsheets`.

### C. One refresh token per mailbox
- [ ] Open the Google **OAuth Playground**, use your own client ID and secret (gear icon), authorise the two scopes while signed in as that mailbox, and exchange the code for tokens.
- [ ] Store each mailbox's token JSON as its own GitHub secret.
- [ ] Do this for every mailbox. A wrong paste (extra quotes or line breaks) is the most common failure.

### D. Repo and scheduler
- [ ] Create a repo. Add the tool, `config.yaml` and the template pool.
- [ ] Add secrets: one token per mailbox plus `WARMUP_STATE_KEY` (a long random string; keep a copy).
- [ ] Fill `config.yaml`: timezone, start date, working hours, the mailboxes (email, name, title), signature address, outside seeds, sheet ID.
- [ ] Share the Google Sheet with the mailbox that carries the Sheets scope.
- [ ] Run the connection check and a dry run. Look at the plan it prints.
- [ ] Set `github_actions_live: true` only when the dry run looks right.
- [ ] **cron-job.org**: create a fine-grained GitHub token (Actions: read and write on that repo only), then a job that POSTs to the workflow-dispatch URL every hour.

### E. First 48 hours
- [ ] Watch the first live run's log: all mailboxes connect, emails go out.
- [ ] Check the sheet fills in.
- [ ] Reply by hand to the outside seeds so they look like real conversations.

---

## 6. Monitoring: what "healthy" looks like

Check at least once a day (we have Claude do it every hour):

- Every GitHub Actions run is green.
- The sheet has a row per mailbox for today, and "sent" and "replied" climb through the day.
- `problems` is empty and `rescued_from_spam` is near 0.
- No `ALERT` file or failed run.

If a run fails, read its log first. The usual causes are a broken token, a dropped connection, or a bounce.

---

## 7. Is it ready? (the health checks)

Run these before the first cold campaign, and again after changes.

| Check | Tool | Pass |
|---|---|---|
| SPF, DKIM, DMARC | Google Admin Toolbox → Check MX; or send to `check-auth@verifier.port25.com` | All pass |
| Blacklists | MXToolbox blacklist check | Zero listings |
| Spam score | mail-tester.com | 9/10 or better |
| Inbox placement | EasyDMARC inbox-placement test (free) | Gmail, Google Workspace and Microsoft 365 land in the inbox |
| Reputation | Google Postmaster Tools | Domain reputation Medium or better, spam rate low |
| Warm-up history | The sheet | 2+ weeks, zero bounces, zero rescues |

**Our placement test (before the full ramp-up):** Google Workspace 100% inbox, Microsoft 365 100%, Gmail 86% inbox with 0% spam, consumer Outlook 75%, Zoho 30%, Yahoo and AOL not delivered. Takeaway: business inboxes were fine; the strict consumer providers need weeks more reputation, so we hold off emailing them at first.

---

## 8. After warm-up: starting cold outreach

- **Wait** until the readiness table above passes.
- **Start small**: 10–20 cold emails per mailbox per day, and **keep the warm-up running alongside it**.
- **Verify every list** before sending (a verifier such as Hunter or ZeroBounce).
- **Business domains first** (Google Workspace and Microsoft 365). Hold off on Yahoo, AOL, Zoho and consumer Outlook until a later placement test is clean.
- **Stop and clean the list** if the bounce rate goes above 2%.
- Plain-text, short, one clear ask, an easy opt-out.

---

## 9. Mistakes we made (so you don't)

| What happened | Fix |
|---|---|
| **We skipped two days of sending** because the monitoring chain lapsed and GitHub's cron only fires sporadically. | Add an external hourly timer (cron-job.org) so runs never depend on a person or on GitHub's scheduler. |
| **A false alert stopped everything.** A deliverability test sent from one mailbox generated dozens of bounce notices, and the tool counted them as warm-up bounces. | Only count a bounce if it names one of our own warm-up addresses. A one-off reset cleared the pause. |
| **Connection drops** (`SSLEOF`) during sends after a long idle wait. | Retry on a fresh connection. |
| **Two DKIM records** at the same name, and later the wrong key published. | Exactly one `google._domainkey` record, and it must match the key shown in Admin. |
| **Daylight saving** moved the UTC working window by an hour. | Define hours in the company timezone and re-check the check-in times after the change. |
| **Wrong token pasted** (extra characters) stopped one mailbox. | Paste the JSON exactly; the connection check shows `ok` or the error type per mailbox. |

---

## 10. FAQ

**Why not just use a warm-up tool (Instantly, Lemwarm, etc.)?**
They work, but they cost money per mailbox and send through shared pools you don't control. This is free and uses only your own mailboxes and addresses. The cost is the setup time.

**Why only a few outside addresses?**
They give real conversations outside the closed group. A big group would add little and cost more to run.

**How many mailboxes do I need?**
At least two (they email each other). Three or more looks more natural.

**Can the volume go higher?**
The hard cap is 35 per mailbox per day on purpose. Higher volume on a young domain is the fastest way to get flagged.

**What if a run is missed?**
Nothing breaks. The next run picks up and the day just ends lower. Never compensate with extra sends.

**Is this allowed?**
It uses the official Gmail API with the account owner's OAuth consent, on mailboxes you own. Keep the content genuinely business-like, and follow Google's and your local anti-spam rules for the real campaigns that come afterwards.

---

*Keep secrets out of the repo, keep the daily cap, and let the schedule run.*
