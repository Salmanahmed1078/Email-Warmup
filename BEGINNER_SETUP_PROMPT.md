# Prompt: set up an automated Gmail inbox warm-up with Claude Code

Copy everything below the line into Claude Code. First fill in the `<...>` parts in "My details".
You don't need to know how to code. Claude Code will guide you one step at a time.

---

I'm a beginner. Please teach me, one step at a time, how to set up an automated email warm-up
for my Google Workspace inboxes. Do the technical work yourself (code, config, commits). Tell me
exactly what to click in Google Cloud, Google Sheets and GitHub. Give me one step, then wait for me
to say "done" before the next. If a step fails, help me fix it before moving on.

## My details
- Domain: `<mydomain.com>` (Google Workspace)
- Warm-up inboxes (at least 2, ideally 3). For each: email, the name and title to use in the signature:
  - `<name1@mydomain.com>`: `<Full Name>`, `<Title>`
  - `<name2@mydomain.com>`: `<Full Name>`, `<Title>`
  - `<name3@mydomain.com>`: `<Full Name>`, `<Title>`
- Company name and postal address for the signature: `<Company>`, `<street, city, state ZIP>`
- Timezone and working hours: `<America/New_York, 09:00-17:00>`
- Warm-up start date (Week 1, day 1): `<YYYY-MM-DD>`
- Emails per inbox per day: Week 1: 5-10 | Week 2: 10-15 | Week 3: 15-25 | Week 4+: 25-35
- Google Sheet for daily numbers (optional): `<sheet link>`
- My GitHub username: `<username>`

## What to build
Use this public repo as the template, since it already does all of this:
https://github.com/Salmanahmed1078/Email-Warmup (folder `warmup/` plus `.github/workflows/warmup.yml`).
Help me make my own copy and change `warmup/config.yaml` to my details. Then replace the example
names, company and address everywhere (including `warmup/warmup/pool.yaml`), and reset
`github_actions_live` to `false` until we've tested. What it does:
- It sends plain-text work emails between my inboxes, one recipient per email. There are no links,
  images or attachments, and every email ends with the sender's signature. Emails come from a fixed
  pool of 40+ templates, so it uses no AI tokens when it runs.
- It sends in short bursts with random 5-15 minute gaps, spread across working hours. It never
  repeats a subject from the same inbox within 14 days.
- It replies in the same thread 20 minutes to 4 hours after an email arrives. It only replies to
  warm-up emails it sent itself and never touches my real mail.
- Every run, it moves warm-up emails out of Spam/Promotions ("Not spam", back to Inbox).
- Daily target comes from the calendar above, with a hard cap per inbox per day.
- Any bounce or spam report stops all sending and alerts me. A bounce rate above 2% pauses that
  inbox for 7 days.
- It logs to a CSV and to my Google Sheet.
- It runs on GitHub Actions, which is free for public repos, so no server is needed. State and logs
  are saved encrypted, so nothing private shows in a public repo.
- Dry-run is the default. It only sends for real after I approve.

## Safety rules (follow these strictly)
- Never ask me to paste a client secret, refresh token or password into this chat. Secrets go only
  into GitHub's encrypted secrets, which I add myself in the GitHub website.
- Google Cloud does not need billing for this. If Google shows a "set up organization/billing" page,
  tell me to close it.
- Test in dry-run first, against my real inboxes. Only switch to live when I say "go live".
- Before we start, check that SPF, DKIM and DMARC are set up for my domain. Tell me how to check if
  you can't.

## The steps to walk me through
1. **GitHub:** create my repo from the template. It must be on the `main` branch, because GitHub only
   runs scheduled jobs from the default branch.
2. **Google Cloud project:** sign in at console.cloud.google.com with one of my Workspace inboxes and
   create a project.
3. **APIs:** enable **Gmail API** and **Google Sheets API** (APIs & Services > Library).
4. **OAuth consent screen:** user type **Internal**. That's for Workspace only: no Google review, and
   tokens don't expire. Add the scopes `https://www.googleapis.com/auth/gmail.modify` and
   `https://www.googleapis.com/auth/spreadsheets`.
5. **OAuth client:** Credentials > Create credentials > OAuth client ID > **Web application**. Add
   this authorized redirect URI: `https://developers.google.com/oauthplayground`.
   (A Desktop app client also works, but then the login has to run on my own computer with Python.)
6. **Refresh tokens:** get one per inbox with Google's OAuth Playground
   (developers.google.com/oauthplayground), using a private/incognito window for each inbox:
   1. Click the gear icon, tick "Use your own OAuth credentials", and paste the client ID and secret.
   2. Paste both scopes into the left box and click "Authorize APIs".
   3. Sign in as that inbox and click Allow.
   4. Click "Exchange authorization code for tokens" and copy the refresh token.
7. **GitHub secrets:** in repo Settings > Secrets and variables > Actions, add one secret per inbox,
   named `WARMUP_TOKEN_<INBOXKEY>_JSON`. The value is this JSON:
   `{"client_id":"...","client_secret":"...","refresh_token":"...","token_uri":"https://oauth2.googleapis.com/token","scopes":["https://www.googleapis.com/auth/gmail.modify","https://www.googleapis.com/auth/spreadsheets"]}`.
   Also add `WARMUP_STATE_KEY`: any long random password, which encrypts the saved state.
   Tell me to type plain straight quotes. Notes apps change them to curly quotes and break the JSON.
   Update the secret names in `.github/workflows/warmup.yml` to match my inbox keys.
8. **Google Sheet:** create a tab called `warm-up`. Share the sheet **by name as Editor** with the
   inbox whose token writes to it (`sheets.token_inbox` in the config). "Anyone with the link" is
   not enough for the API.
9. **Dry run:** start the workflow from the Actions tab (Run workflow). In the log, the connection
   check must show `ok` for every inbox and for the sheet. If one shows `FAILED`, fix it first:
   JSONDecodeError means a bad secret paste, and HttpError on the sheet means the API isn't enabled
   or the sheet isn't shared.
10. **Go live:** only when I say so. Set `github_actions_live: true` in `warmup/config.yaml` and merge
    it to `main`.
11. **Make sure it keeps running:** GitHub's scheduled runs can start hours late and then fire only
    now and then. If scheduled runs are missing or sparse, help me set up a free external scheduler,
    for example cron-job.org. It should call the GitHub API every 10 minutes during working hours to
    start the workflow with input `window` = `10`. That needs a fine-grained GitHub token limited to
    this one repo with "Actions: read and write", which I paste into cron-job.org myself, not here.

## Known problems already solved in the template
- `SSLEOFError` after long runs: the template retries Gmail calls on a fresh connection.
- Replies that come due after working hours roll to the next working morning. That's expected.
- Nothing is sent on weekends or before the start date.

Explain each step in plain words and keep it short. Start with step 1 now.
