# Daily Briefing

Automated structured daily briefing delivered Mon–Fri at 07:30 CET via:
- **GitHub Pages** — mobile-first dark web dashboard
- **Gmail** — full HTML email
- **Telegram** — condensed text message (optional)

Powered by Gemini 2.0 Flash (free tier). Zero paid dependencies.

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

### 3. Get a Gemini API key (free)

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API key → Create API key**
3. Copy the key

---

### 4. Get a Gmail App Password

> Required because Gmail blocks plain passwords for SMTP.

1. Enable **2-Factor Authentication** on your Google account (if not already)
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. App name: `Daily Briefing` → **Create**
4. Copy the 16-character password (shown once)

---

### 5. Set GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name          | Value                                      |
|----------------------|--------------------------------------------|
| `GEMINI_API_KEY`     | Your Gemini API key                        |
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
3. Watch the logs — should complete in ~30 seconds
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
pip install google-generativeai

export GEMINI_API_KEY="..."
export GMAIL_ADDRESS="..."
export GMAIL_APP_PASSWORD="..."
export RECIPIENT_EMAIL="..."
export TELEGRAM_BOT_TOKEN="..."   # optional
export TELEGRAM_CHAT_ID="..."     # optional

python briefing.py
```

The generated `docs/index.html` opens directly in any browser — no server needed.

---

## Briefing sections

| # | Section | Content |
|---|---------|---------|
| 1 | ⚡ Skill Snacks | 2 practical tips, rotating across PPT / Excel / Python / AI Prompting / Consulting Craft |
| 2 | 📈 Macro & Markets | Top 3 market moves with ECB/Fed context |
| 3 | 🤖 AI & Tech | Top 5 signal-over-noise items |
| 4 | 🌍 Geopolitics & Defense | Top 3 developments, European angle |
| 5 | 💼 PwC Conversation Starter | 1 topic for CIO advisory client calls |
| 6 | ⚽ Eintracht Frankfurt | Match result or squad news |

---

## File structure

```
daily-briefing/
├── briefing.py                          # main script
├── docs/
│   └── index.html                       # overwritten daily (GitHub Pages source)
├── archive/
│   └── YYYY-MM-DD.md                    # raw Gemini output, auto-committed
├── .github/
│   └── workflows/
│       └── daily_briefing.yml           # GitHub Actions schedule
└── README.md
```

---

## Limitations

- **Gemini knowledge cutoff**: Gemini 2.0 Flash has a training cutoff and may not know events from the last few weeks. For truly current news, consider enabling Google Search grounding (requires Gemini API Pro tier).
- **Gmail rate limits**: Free Gmail SMTP allows ~500 emails/day — irrelevant for a single daily send.
- **GitHub Actions free tier**: 2,000 minutes/month on free accounts. This workflow uses ~1 minute per run × 20 weekdays = ~20 minutes/month.
