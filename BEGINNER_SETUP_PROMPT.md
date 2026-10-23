# Prompt: set up an automated Gmail inbox warm-up with Claude Code

How to use it: fill in the `<...>` parts in "MY DETAILS", then copy everything below the line into
Claude Code (claude.ai/code, with your GitHub connected). You don't need to know how to code.

---

I'm a beginner. Walk me through setting up an automated email warm-up for my Google Workspace
inboxes, exactly as described below. This setup has already been done successfully once. Follow the
steps in order and use the exact click paths and values given. You (Claude Code) do all the code,
config and git work. I do the clicking in Google Cloud, Google's OAuth Playground, Google Sheets and
GitHub, because only I can sign in to my accounts.

How to teach me:
- Give me ONE step at a time in plain words, then wait for me to reply "done" (or paste an error)
  before the next step.
- Tell me exactly where to click: page, menu, button, and what to type in each field.
- If a screen looks different from what you describe (Google renames menus often), ask me what I
  see and adapt.

## MY DETAILS
- Domain: `<mydomain.com>` (Google Workspace)
- Warm-up inboxes (2 or 3). Short key, email, and the name and title for the signature:
  - key `<name1>`: `<name1@mydomain.com>`, `<Full Name>`, `<Title>`
  - key `<name2>`: `<name2@mydomain.com>`, `<Full Name>`, `<Title>`
  - key `<name3>`: `<name3@mydomain.com>`, `<Full Name>`, `<Title>`
- Company name for the signature: `<Company>`
- Postal address for the signature: `<street, suite>` / `<city, state ZIP>`
- Timezone: `<America/New_York>`. Working hours: `<09:00>`-`<17:00>`. Weekdays only.
- Warm-up start date (Week 1, day 1): `<YYYY-MM-DD>`
- Emails per inbox per day: Week 1: 5-10, Week 2: 10-15, Week 3: 15-25, Week 4 and later: 25-35
- Hard daily cap per inbox: 35
- My GitHub username: `<username>`

## SAFETY RULES (always)
1. Never ask me to paste a client secret, refresh token, password or GitHub token into this chat.
   I put those only into GitHub secrets (or cron-job.org) myself. If I paste one by mistake, tell
   me to regenerate it.
2. Google Cloud does NOT need billing for this. If Google shows "Set up your organization",
   "Start free trial" or a billing page, tell me to close it and continue.
3. Everything starts in dry-run, which reads only and sends nothing. We switch to live only when I
   type "go live".
4. Never print secrets in logs. The repo is public, so only encrypted state goes into it.

## WHAT GETS BUILT
A copy of this working public template: https://github.com/Salmanahmed1078/Email-Warmup
(code in `warmup/`, scheduler in `.github/workflows/warmup.yml`). Read its `warmup/README.md`
first. What it does:
- **Content:** a pool of 44 plain-text work emails (`warmup/warmup/pool.yaml`), each with 3-4
  replies. No links, images or attachments. Every email ends with the sender's signature: name,
  title + company, address. It uses no AI at run time, so it costs zero tokens.
- **Sending:** one recipient per email, short bursts with random 5-15 minute gaps spread across
  working hours. The same inbox never repeats a subject within 14 days.
- **Replies:** in-thread, 20 minutes to 4 hours after an email arrives, only to warm-up emails it
  sent itself. Replies due after working hours wait until the next working morning.
- **Spam rescue:** every run, warm-up mail in Spam/Promotions is marked "Not spam" and moved to Inbox.
- **Schedule:** the daily target comes from the calendar, shifted by the start date. Nothing is sent
  on weekends.
- **Safety:** a hard daily cap. Any bounce or spam report stops all sending and fails that run once,
  so GitHub emails me. A bounce rate above 2% over 7 days pauses that inbox for 7 days.
- **Logging:** a CSV plus a Google Sheet tab with one row per inbox per day: date, inbox, sent,
  replied, rescued_from_spam, problems.
- **Runs on GitHub Actions**, which is free for public repos. State and logs are saved encrypted
  (AES) on a `warmup-state` branch. The public log shows only counts and "ok"/"FAILED" checks.

---

## STEP 0: Check the domain (5 min)
Ask me to check my domain's email authentication with a free checker (for example, MXToolbox:
SPF, DKIM and DMARC lookups), or check it yourself if you can. SPF and DMARC must pass. DKIM must
be turned on in Google Admin (admin.google.com > Apps > Google Workspace > Gmail > Authenticate
email > Start authentication); it can take up to 48 hours to work. The warm-up can start while DKIM
is still propagating.

## STEP 1: Make my own copy of the repo (GitHub)
1. Open https://github.com/Salmanahmed1078/Email-Warmup and click **Fork** (top right).
2. Owner: me. Repo name: for example `email-warmup`. Leave **"Copy the main branch only" ticked**.
   This matters: the template's `warmup-state` branch is encrypted with someone else's key and
   would break my runs.
3. Click **Create fork**.
4. In my fork, open the **Actions** tab. If it says "Workflows aren't being run on this forked
   repository", click **"I understand my workflows, go ahead and enable them"**.
5. Connect the new repo to this Claude Code session so you can commit to it.

## STEP 2: You adapt the code to my details (Claude Code does this)
Edit and commit to `main`:
- `warmup/config.yaml`:
  - `timezone`, `start_date`, `working_hours`, `company`, `address` (use `\n` between the
    address lines), and the calendar.
  - `hard_daily_cap: 35`.
  - `inboxes:` with my keys, emails, `full_name` and `title`.
  - `github_actions_live: false`.
  - `sheets.enabled: false` for now. We turn it on in step 8.
- `.github/workflows/warmup.yml`: in the "Tick" step's `env:`, replace the three
  `WARMUP_TOKEN_AWAIS_JSON` / `..._SALMAN_JSON` / `..._KINZA_JSON` lines with one line per inbox,
  in the form `WARMUP_TOKEN_<KEY IN CAPITALS>_JSON: ${{ secrets.WARMUP_TOKEN_<KEY IN CAPITALS>_JSON }}`.
  The code reads each inbox's token from the env var `WARMUP_TOKEN_<KEY>_JSON`.
- Check that `pool.yaml` doesn't mention anything that doesn't fit my company, and adjust the topics
  if I ask.
- Run `python -m pytest -q warmup/tests` and `python -m warmup check` locally, and fix anything
  that fails.
- Then tell me the exact secret names I'll need: one `WARMUP_TOKEN_<KEY>_JSON` per inbox, plus
  `WARMUP_STATE_KEY`.

## STEP 3: Google Cloud project (no billing)
1. Open **https://console.cloud.google.com**, signed in as one of my warm-up inboxes (for example
   `<name1@mydomain.com>`), not a personal Gmail.
2. If a welcome or terms popup appears, accept the terms. If it offers billing, a free trial or
   "set up organization", close it.
3. Click the **project picker** at the top left (next to the Google Cloud logo) > **New project**.
4. Name it `email-warmup`. Organization/Location should show my domain (that's automatic for
   Workspace). Click **Create**, then make sure the new project is selected in the picker.
5. If project creation is blocked: my Workspace super admin needs to give me the "Project Creator"
   role (IAM & Admin > IAM, on the organization). That's free.

## STEP 4: Turn on the two APIs
1. Left menu (☰) > **APIs & Services** > **Library**.
2. Search **Gmail API**, open it, click **Enable**.
3. Back to Library, search **Google Sheets API**, open it, click **Enable**.

## STEP 5: OAuth consent screen (set to "Internal")
Google moved this. It may be under ☰ > **APIs & Services** > **OAuth consent screen**, or under
**Google Auth Platform** (Branding / Audience / Data Access / Clients).
1. If you see **Get started**, click it. App name `Email Warmup`, user support email = my inbox.
2. **Audience / User type: Internal**. This is important: Internal means only my domain can use
   it, Google doesn't need to review it, and the login never expires. External + Testing tokens
   expire after 7 days.
3. Contact email = my inbox. Agree to the policy and click **Create** / **Save**.
4. **Data Access** (or "Scopes") > **Add or remove scopes**. Paste these into "Manually add scopes",
   then click **Add to table**, **Update**, **Save**:
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/spreadsheets`

## STEP 6: OAuth client (Web application)
1. ☰ > **APIs & Services** > **Credentials** (or Google Auth Platform > **Clients**) >
   **+ Create credentials** > **OAuth client ID**.
2. Application type: **Web application**. Name: `warmup-playground`.
3. **Authorized JavaScript origins:** leave empty.
4. **Authorized redirect URIs** > **+ Add URI**, then paste exactly:
   `https://developers.google.com/oauthplayground`
5. Click **Create**. A popup shows the **Client ID** and **Client secret**. Click **Download JSON**
   or copy both into a private note on my own computer. Don't paste them in chat.
6. Wait about 5 minutes before step 7. A new redirect URI can take a few minutes to start working.

(For reference: a "Desktop app" client has no redirect field and would need Python on my computer
with `python -m warmup auth --inbox <key>`. We use the Web client + Playground instead because it
works entirely in the browser.)

## STEP 7: Get a refresh token for each inbox (OAuth Playground)
Repeat for EACH inbox, using a NEW private/incognito window each time, so the right account is
signed in:
1. Open **https://developers.google.com/oauthplayground**.
2. Click the **gear icon ⚙** (top right). Tick **"Use your own OAuth credentials"**, then paste
   **OAuth Client ID** and **OAuth Client secret**. Close the gear panel.
3. On the left, in **"Input your own scopes"** at the bottom of the list, paste exactly (one line,
   with a space between them):
   `https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/spreadsheets`
4. Click **Authorize APIs**. Sign in as THIS inbox (for example `<name2@mydomain.com>`) and click
   **Allow**.
5. Back in the Playground, Step 2 opens. Click **Exchange authorization code for tokens**.
6. Copy the **Refresh token** value (it often starts with `1//`). Keep it in my private note,
   labelled with the inbox.
Errors: "redirect_uri_mismatch" means the URI in step 6.4 is wrong or not active yet. Wait 5
minutes and check it. "access_denied / org_internal" means I signed in with an account outside my
domain.

## STEP 8: Google Sheet for the daily numbers
1. Create a Google Sheet (or use mine) and rename the first tab to `warm-up`.
2. Click **Share**. Add the inbox whose token will write to the sheet (for example
   `<name1@mydomain.com>`) **by name as Editor**. "Anyone with the link can edit" is NOT enough for
   the API, especially when a personal Gmail owns the sheet.
3. Send me the sheet link. You then set in `warmup/config.yaml`:
   - `sheets.enabled: true`
   - `spreadsheet_id` (the long ID between `/d/` and `/edit` in the link)
   - `tab: "warm-up"`
   - `mode: upsert`
   - `token_inbox: <that inbox key>`
   Then commit to `main`. The code writes the header row itself.

## STEP 9: GitHub secrets
In my repo: **Settings** (top tab) > left menu **Secrets and variables** > **Actions** >
**New repository secret**. Create these. The Name must match exactly, and the Secret field gets
the value:
1. `WARMUP_TOKEN_<KEY>_JSON`, one per inbox (for example `WARMUP_TOKEN_NAME1_JSON`). The value is
   this JSON on one line, with my client ID and secret and THAT inbox's refresh token:
   ```
   {"client_id": "PASTE_CLIENT_ID", "client_secret": "PASTE_CLIENT_SECRET", "refresh_token": "PASTE_THIS_INBOXES_REFRESH_TOKEN", "token_uri": "https://oauth2.googleapis.com/token", "scopes": ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/spreadsheets"]}
   ```
   Type it in a plain-text editor (Notepad / TextEdit in plain-text mode) with straight quotes `"`.
   Notes apps and Word turn them into curly quotes `“ ”`, which breaks it (error: JSONDecodeError).
   Easiest: make the first one, then copy it and change only the `refresh_token` for the others.
2. `WARMUP_STATE_KEY`: any long random password, 30+ characters, made by me (a password manager
   works). It encrypts the saved state and logs. Don't lose it: if it changes, the saved state can't
   be decrypted and runs fail until the `warmup-state` branch is deleted.

## STEP 10: Dry run against the real inboxes
1. **Actions** tab > left: **warm-up** > **Run workflow** (right) > branch `main`, window `0` >
   **Run workflow**.
2. After about 1 minute, open the run > job **tick** > expand the **Tick** step. It must show:
   ```
   mode: dry-run
   gmail <key>: ok      (one line per inbox)
   sheets: ok
   ```
3. If anything shows FAILED, fix it before going on:
   - `JSONDecodeError`: that inbox's secret isn't valid JSON (curly quotes, a missing brace or
     comma). Re-paste it.
   - `RefreshError` / `invalid_grant`: wrong client secret or refresh token. Redo step 7 for that
     inbox.
   - `WRONG ACCOUNT`: the refresh token was made while signed in as a different inbox.
   - `sheets: FAILED (HttpError ...)`: the Sheets API isn't enabled (step 4), the sheet isn't shared
     by name (step 8), or `token_inbox`'s token is missing the spreadsheets scope.
   - "WARMUP_STATE_KEY secret is not set": add it (step 9).
   - Restore step fails with a "bad decrypt" error: the state key changed, or the template's
     `warmup-state` branch was copied. Delete the `warmup-state` branch (Code tab > branches) and
     re-run.

## STEP 11: Go live (only when I type "go live")
1. Set `github_actions_live: true` in `warmup/config.yaml` and commit to `main`.
2. Start one run (Actions > warm-up > Run workflow, window `50`). It makes today's plan and sends
   the emails that come due during the next 50 minutes.
3. Show me the results: the `data/live` counts in the run log, the rows in my sheet, and a sent
   email in one inbox's Sent folder with the signature at the bottom.

## STEP 12: Make sure it keeps running every day (important)
The workflow has a GitHub schedule (`*/5 12-23 * * 1-5`, UTC). But GitHub's scheduled runs for a new
repo can start hours late and then fire only now and then. On our first day they fired about twice
in 10 hours. The tool only sends what is due when it runs, so sparse runs mean missed emails. Fix it
with a free external timer:
1. **Fine-grained GitHub token:** GitHub > my profile picture > **Settings** > **Developer
   settings** > **Personal access tokens** > **Fine-grained tokens** > **Generate new token**.
   - Name: `warmup-cron`. Expiration: 1 year.
   - Repository access: **Only select repositories** > my warm-up repo.
   - Permissions > Repository permissions > **Actions: Read and write**. Leave everything else as is.
   - Click **Generate token** and copy it (shown once). Don't paste it in chat.
2. **cron-job.org:** sign up free > **Create cronjob**:
   - Title: `warmup tick`.
   - URL: `https://api.github.com/repos/<username>/<repo>/actions/workflows/warmup.yml/dispatches`
   - Schedule: custom. Every 10 minutes, Monday-Friday, hours 9-17, in MY timezone (cron-job.org
     lets you pick it).
   - **Advanced** tab:
     - Request method: **POST**.
     - Headers:
       - `Accept: application/vnd.github+json`
       - `Authorization: Bearer <the token from step 12.1>`
       - `X-GitHub-Api-Version: 2022-11-28`
       - `Content-Type: application/json`
     - Request body: `{"ref":"main","inputs":{"window":"10"}}`
   - Save, then click **Test run**. A response of **204** means it worked, and a new run appears in
     my Actions tab.
3. With cron-job.org in place, the GitHub schedule just acts as a backup. Runs can't overlap
   (concurrency group), so the two together are safe.

## HOW I RUN IT DAY TO DAY (explain this at the end)
- I can watch everything in the sheet's `warm-up` tab and in the Actions tab.
- To pause: set `github_actions_live: false` in `warmup/config.yaml` (edit on GitHub, then commit),
  or disable the cron-job.org job.
- If a bounce or spam report happens, that run fails once and GitHub emails me, and sending stops
  until the alert is cleared. Help me look into it, then clear it. The CLI command is
  `python -m warmup clear-alert --live`. On Actions, add a small workflow input or step to run it,
  and commit that when needed.
- The calendar moves up by itself each week. In Week 3 I can start cold email from these inboxes,
  while the warm-up keeps running in the background.

## PROBLEMS WE ALREADY HIT (so you don't repeat them)
- We picked "Web application" instead of "Desktop app". That's fine: use the Playground redirect
  URI from step 6.
- Curly quotes in a secret caused `JSONDecodeError`.
- "Anyone with the link can edit" wasn't enough for the sheet. Share it by name with the token's
  inbox.
- `SSLEOFError` happened during long runs. The template already retries on a fresh connection; keep
  that code.
- GitHub's scheduler was late and sparse, which is why step 12 exists.
- Don't run any command that writes GitHub secrets or prints secrets. I add secrets myself in the
  website.

Start with STEP 0 now.
