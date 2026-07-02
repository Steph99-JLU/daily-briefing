# Daily Briefing

Automated intelligence briefing synthesized from Stephan's actual inbox newsletters,
delivered Mon–Fri via:
- **GitHub Pages** — mobile-first dark web dashboard
- **Gmail** — full HTML email
- **Telegram** — condensed text message (optional)

Powered by GPT-4o, with live web search used narrowly for verification and enrichment.

---

## How it works (v7 pipeline)

1. **Acquire** — logs into Gmail via IMAP and pulls every email received today from
   the primary newsletters (all TLDR verticals: AI, Founders, IT, Crypto, Dev,
   DevOps, Information Security, and the standard edition). If nothing arrived
   today (weekend/holiday), it walks backward up to 7 days to the most recent day
   that has them, and says so in the briefing.
2. **Read & filter** — extracts every article link from those newsletters, resolves
   redirects, dedups by final URL, and crawls each article for its main text
   (falls back to `[blurb only]` — headline/anchor text — if a fetch fails).
3. **Verify & enrich** — GPT-4o is given a live web-search tool, used *only* for:
   - verifying claims that are both high-impact and surprising (funding, M&A,
     benchmark/SOTA claims, breaches, regulatory action) against an independent
     Tier-1/Tier-2 source — capped at 5 lookups/run
   - adding one extra source of context to the top 1–3 headlines — capped at
     3 lookups/run
   If the account/model doesn't support the search tool, it falls back to a plain
   completion (verification/enrichment tags are simply omitted, and the delivered
   briefing/email footer notes that live search was unavailable that run).
4. **Write** — organizes by theme (Headlines, AI & Research, Business/Founders/
   Strategy, Dev/DevOps/Infra, Other), closing with an Analyst Take, Watch/Action,
   a Verification Log, and a full Source List.
5. Any other bulk/newsletter-style sender seen today that isn't yet whitelisted is
   surfaced as a **NEW SENDER DETECTED** banner at the top of the briefing — it's
   never auto-ingested.

---

## Setup (15 minutes)

### 1. Create a GitHub repository

```bash
cd daily-briefing
git init
git add .
git commit -m "init"
gh repo create daily-briefing --public --source=. --push
```

> Must be **public** for free GitHub Pages. Or use a private repo with GitHub Pages on Pro.

---

### 2. Enable GitHub Pages

1. Go to **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / folder: `/docs`
4. Save — your dashboard URL will be `https://<you>.github.io/daily-briefing/`

---

### 3. Get an OpenAI API key

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create a key with access to `gpt-4o`

---

### 4. Get a Gmail App Password

> Required because Gmail blocks plain passwords for SMTP/IMAP.
> This same password is used both to **read** today's newsletters (IMAP) and to
> **send** the briefing email (SMTP) — no separate credential needed.

1. Enable **2-Factor Authentication** on your Google account (if not already)
2. Make sure **IMAP is enabled**: Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. App name: `Daily Briefing` → **Create**
5. Copy the 16-character password (shown once)

---

### 5. Set GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name          | Value                                      |
|----------------------|--------------------------------------------|
| `OPENAI_API_KEY`     | Your OpenAI API key                        |
| `GMAIL_ADDRESS`      | Your Gmail address (e.g. you@gmail.com)    |
| `GMAIL_APP_PASSWORD` | 16-char App Password from step 4           |
| `RECIPIENT_EMAIL`    | Where to send the briefing (can be same)   |
| `TELEGRAM_BOT_TOKEN` | *(optional)* Telegram bot token            |
| `TELEGRAM_CHAT_ID`   | *(optional)* Your Telegram chat/user ID    |

---

### 6. (Optional) Set up Telegram

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → follow prompts → copy token
2. Start a chat with your bot, then get your chat ID:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Look for `"chat": {"id": 123456789}` in the response

---

### 7. Test it

1. Go to **Actions → Daily Briefing**
2. Click **Run workflow → Run workflow**
3. Watch the logs — acquisition + crawl + generation takes a couple of minutes
4. Check your email and open `https://<you>.github.io/daily-briefing/`

---

## Schedule

The workflow runs at **06:30 UTC** on weekdays:
- = 07:30 CET (winter, UTC+1)
- = 08:30 CEST (summer, UTC+2)

To get exactly 07:30 in summer, change the cron in `.github/workflows/daily_briefing.yml`:
```yaml
# Summer (CEST, UTC+2):
- cron: "30 5 * * 1-5"

# Winter (CET, UTC+1):
- cron: "30 6 * * 1-5"
```

---

## Local testing

```bash
pip install -r requirements.txt

export OPENAI_API_KEY="..."
export GMAIL_ADDRESS="..."
export GMAIL_APP_PASSWORD="..."
export RECIPIENT_EMAIL="..."
export TELEGRAM_BOT_TOKEN="..."   # optional
export TELEGRAM_CHAT_ID="..."     # optional

python briefing.py
```

The generated `docs/index.html` opens directly in any browser — no server needed.
Set `ARCHIVE_DIR=archive` to also save the raw crawled context and the raw
GPT-4o markdown output for each day.

---

## Briefing sections

| Section | Content |
|---------|---------|
| 📰 Headlines | 1–3 most consequential stories today |
| 🤖 AI & Research | Models, capabilities, papers, lab moves |
| 💼 Business, Founders & Strategy | Funding, business models, market moves |
| 🛠️ Dev, DevOps & Infra | Tooling, platforms, security (incl. InfoSec) |
| 🌐 Other | Crypto and general items worth keeping |
| 🧠 Analyst Take | 3–5 bullets connecting the dots |
| 📌 Watch / Action | Releases to try, deadlines, risks |
| ✅ Verification Log | What was checked this run, and any disputes |
| 🔗 Source List | Every article used, grouped by section, with links |

Any section with no qualifying stories is omitted — the briefing never pads to
hit a word count.

---

## Configuration

Tunable constants live at the top of `briefing.py`:

- `PRIMARY_SENDER_KEYWORD` — how newsletters are matched (defaults to `"tldr"`,
  which covers all TLDR verticals)
- `MAX_FALLBACK_DAYS` — how far back to search if no primary mail arrived today
- `MAX_VERIFICATION_LOOKUPS` / `MAX_ENRICHMENT_LOOKUPS` — web-search budget per run
- `MAX_ARTICLES_TO_CRAWL` / `ARTICLE_CHAR_LIMIT` — crawl scope and per-article
  text budget fed to the model

---

## File structure

```
daily-briefing/
├── briefing.py                          # main script
├── docs/
│   └── index.html                       # overwritten daily (GitHub Pages source)
├── archive/
│   └── YYYY-MM-DD.md                    # raw GPT-4o output, auto-committed
│   └── YYYY-MM-DD.context.md            # raw crawled source material
├── .github/
│   └── workflows/
│       └── daily_briefing.yml           # GitHub Actions schedule
└── README.md
```

---

## Limitations

- **No headless browser fallback**: if an article fetch is blocked (paywall,
  JS-rendered content, bot detection), the item is tagged `[blurb only]` and the
  briefing uses just the newsletter's headline/anchor text — it never invents
  details.
- **Web search depends on OpenAI account/model access**: verification and
  enrichment require the `web_search_preview` tool on the Responses API. If
  that's unavailable, the script automatically falls back to a plain completion
  and the footer notes that live search was skipped that run.
- **IMAP must be enabled** on the Gmail account (see setup step 4) — SMTP alone
  is not enough to read today's newsletters.
- **GitHub Actions free tier**: 2,000 minutes/month on free accounts. Crawling
  adds a couple of minutes per run versus the old single-API-call version.
