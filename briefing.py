#!/usr/bin/env python3
"""
Daily Briefing Generator
Generates a structured daily briefing via Gemini 2.0 Flash,
delivers via GitHub Pages (docs/index.html), Gmail, and Telegram.
"""

import os
import re
import smtplib
import sys
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import google.generativeai as genai

# ─── Config ───────────────────────────────────────────────────────────────────

GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
GMAIL_ADDRESS       = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD  = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL     = os.environ["RECIPIENT_EMAIL"]
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")

CET = timezone(timedelta(hours=2))  # CEST in summer; adjust to +1 in winter
TODAY = datetime.now(CET)
DATE_LABEL = TODAY.strftime("%A, %d %B %Y")
ISO_DATE   = TODAY.strftime("%Y-%m-%d")

# ─── Gemini Prompt ────────────────────────────────────────────────────────────

# Day-of-week index (0=Mon) drives which skill categories appear today
DOW = TODAY.weekday()
SKILL_CATEGORIES = ["PowerPoint & Storytelling", "Excel & Data Modeling", "Python & Coding", "AI Prompting", "Consulting Craft"]
SKILL_A = SKILL_CATEGORIES[DOW % len(SKILL_CATEGORIES)]
SKILL_B = SKILL_CATEGORIES[(DOW + 1) % len(SKILL_CATEGORIES)]

SKILL_FORMAT_HINTS = {
    "PowerPoint & Storytelling": "💡 PPT Snack:",
    "Excel & Data Modeling":     "📊 Excel Snack:",
    "Python & Coding":           "🐍 Python Snack:",
    "AI Prompting":              "🤖 Prompting Snack:",
    "Consulting Craft":          "🎯 Consulting Snack:",
}

SYSTEM_PROMPT = f"""You are Stephan's personal intelligence analyst. Today is {DATE_LABEL}.
Write his structured daily briefing — concise, sourced, opinionated.

WHO IS STEPHAN:
25-year-old IT Consulting & CIO Advisory professional at PwC Germany (Gießen).
Master's student in Data Analytics at JLU Gießen (thesis completed).
Interests: AI, macro economics, personal finance, European regulation (DORA, NIS2, CSRD),
geopolitics, and European tech. Eintracht Frankfurt fan and football player.
Write like a trusted senior colleague who respects his intelligence. Real signal, not noise.

EDITORIAL RULES:
- Calm, direct language. Avoid: "must", "never", "critical", "important"
- No exclamation marks, no LinkedIn filler phrases
- Bold the most important number or fact per story
- Every story ends with → 💡 Why it matters for Stephan: [specific to PwC, DA, or personal finance]
- After source line, add confidence flag: 🟢 Confirmed by 2+ sources | 🟡 Single source | 🔴 Developing story
- If same event spans multiple topics, cover fully in most relevant topic only; elsewhere write one line:
  "→ Cross-topic: [event] also impacts this area because [1 specific reason]."
- If story follows up on a major event from the prior 1–2 days, open with:
  "📅 Follow-up: [1-sentence prior context]" then continue with today's development.
- Flag contradictions: ⚠️ [Source A] vs [Source B]: [one sentence on discrepancy]

STORY FORMAT (follow strictly for every story):
Line 1 — What happened (facts, numbers, actors)
Line 2 — Why it happened / broader context
Line 3 — What changes because of this
→ 💡 Why it matters for Stephan: [1 specific sentence]
Source: [name] | [approximate date] | [🟢/🟡/🔴]

OUTPUT FORMAT — use exactly these section headers:

## ⚡ Daily Skill Snacks
Generate exactly 2 skill snacks today: one on {SKILL_A}, one on {SKILL_B}.
Format snack A as: "{SKILL_FORMAT_HINTS[SKILL_A]} [tip in 2–3 sentences with concrete example or code snippet]"
Format snack B as: "{SKILL_FORMAT_HINTS[SKILL_B]} [tip in 2–3 sentences with concrete example or code snippet]"
Be specific and immediately applicable. No theory.

## 🤖 AI & Technology
Exactly 2 stories. Follow STORY FORMAT. Signal over noise — structural shifts, funding >€100M, capability breakthroughs, EU AI Act developments.

## 🔐 Cybersecurity & IT Risk
Exactly 2 stories. Prioritise CVEs being actively exploited, ransomware, supply chain attacks. DORA/NIS2 compliance angles where relevant.

## 🇩🇪 European & German Politics
Exactly 2 stories. EU regulation (DORA, NIS2, CSRD, AI Act), German government, Bundestag, major EU institutional decisions.

## 🌍 Macro & Global Economy
Exactly 2 stories. ECB, Fed, inflation, GDP revisions, trade policy. Include specific numbers.

## 📈 Markets & Personal Finance
Exactly 2 stories. DAX, EUR/USD, bond yields, ETF-relevant macro. Personal finance angle for a German saver/investor in their mid-20s.

## 🚀 Startups, VC & European Tech
Exactly 2 stories. European focus. Funding rounds, IPOs, strategic pivots, founder moves.

## 🔬 Science & Research
Exactly 2 stories. Nature, ScienceDaily level — actual research with potential near-term application, not press releases.

## ⚡ Energy & Climate / ESG
Exactly 2 stories. German Energiewende, EU climate policy, corporate ESG regulation, energy prices.

## 💼 Future of Work & Consulting Industry
Exactly 2 stories. AI impact on consulting, Big Four strategy, workforce trends, McKinsey/BCG/PwC-level moves.

## 🧠 Stephan's Takeaway
3–4 sentences. The single biggest signal from today's briefing and what it means for Stephan's work this week.

## 📌 One Action
One concrete thing Stephan can do today (read something, research a topic, prepare a talking point) based on today's briefing.

## 💬 PwC Conversation Starter
One topic that will come up in CIO client conversations this week. 3–5 sentences. Specific enough for a steering committee. Include a suggested opening line.

## 📈 Relevance Score
X/10 — one sentence explanation of why today's news is more or less relevant than average for Stephan's work.

## 🌡️ News Stress Level
Calm / Elevated / Critical — one sentence justification.

## 🗓️ Tomorrow's Watch
2–3 things to watch for tomorrow: scheduled events, expected announcements, or developing stories.

TARGET LENGTH: 1,800–2,200 words total. Format as clean markdown.
Write the briefing now.
"""

# ─── Generate Briefing ────────────────────────────────────────────────────────

def generate_briefing() -> str:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            max_output_tokens=4096,
        ),
    )
    print("⏳ Calling Gemini 2.0 Flash…")
    response = model.generate_content(SYSTEM_PROMPT)
    text = response.text
    print(f"✅ Received {len(text)} chars from Gemini")
    return text

# ─── Markdown → HTML Renderer ─────────────────────────────────────────────────

SECTION_META = {
    # Main sections
    "DAILY SKILL SNACKS":               ("⚡", "skill",     "Daily Skill Snacks",          False),
    "AI & TECHNOLOGY":                  ("🤖", "ai",        "AI & Technology",             False),
    "CYBERSECURITY & IT RISK":          ("🔐", "cyber",     "Cybersecurity & IT Risk",     False),
    "EUROPEAN & GERMAN POLITICS":       ("🇩🇪", "politics", "European & German Politics",  False),
    "MACRO & GLOBAL ECONOMY":           ("🌍", "macro",     "Macro & Global Economy",      False),
    "MARKETS & PERSONAL FINANCE":       ("📈", "markets",   "Markets & Personal Finance",  False),
    "STARTUPS, VC & EUROPEAN TECH":     ("🚀", "startups",  "Startups, VC & European Tech",False),
    "SCIENCE & RESEARCH":               ("🔬", "science",   "Science & Research",          False),
    "ENERGY & CLIMATE / ESG":           ("⚡", "energy",    "Energy & Climate / ESG",      False),
    "FUTURE OF WORK & CONSULTING":      ("💼", "work",      "Future of Work & Consulting", False),
    # End-section cards (compact=True → rendered in summary grid)
    "STEPHAN'S TAKEAWAY":               ("🧠", "takeaway",  "Stephan's Takeaway",          True),
    "ONE ACTION":                       ("📌", "action",    "One Action",                  True),
    "PWC CONVERSATION STARTER":         ("💬", "pwc",       "PwC Conversation Starter",    True),
    "RELEVANCE SCORE":                  ("📈", "score",     "Relevance Score",             True),
    "NEWS STRESS LEVEL":                ("🌡️", "stress",   "News Stress Level",           True),
    "TOMORROW'S WATCH":                 ("🗓️", "tomorrow", "Tomorrow's Watch",            True),
}

# Partial-match lookup: handles Gemini adding extra words to headers
def find_section_meta(raw_title: str):
    upper = raw_title.upper()
    for key, meta in SECTION_META.items():
        # Check all significant words of the key appear in the title
        key_words = set(key.replace("/", " ").replace("&", " ").split())
        if key_words and key_words.issubset(upper.replace("/", " ").replace("&", " ").split()):
            return key, meta
        # Fallback: direct substring
        if key in upper:
            return key, meta
    return None, None

def md_to_html_inline(text: str) -> str:
    """Convert inline markdown (bold, italic, links) to HTML."""
    # Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    # Italic *text* or _text_
    text = re.sub(r'\*([^*\n]+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_([^_\n]+?)_', r'<em>\1</em>', text)
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text

def render_section_body(raw: str) -> str:
    """Convert a section's markdown body to HTML."""
    html_parts = []
    lines = raw.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # H3 ### heading → item title
        if line.startswith('### '):
            title = md_to_html_inline(line[4:])
            html_parts.append(f'<h3 class="item-title">{title}</h3>')
        # H4 #### heading
        elif line.startswith('#### '):
            title = md_to_html_inline(line[5:])
            html_parts.append(f'<h4 class="item-sub">{title}</h4>')
        # Bold label line (e.g. **PPT Snack:**)
        elif re.match(r'^\*\*[^*]+:\*\*', line):
            html_parts.append(f'<p class="snack-label">{md_to_html_inline(line)}</p>')
        # Insight line
        elif line.startswith('→'):
            insight = md_to_html_inline(line)
            html_parts.append(f'<p class="insight">{insight}</p>')
        # Source line
        elif line.lower().startswith('source:'):
            src = md_to_html_inline(line)
            html_parts.append(f'<p class="source">{src}</p>')
        # Unordered list item
        elif line.startswith('- ') or line.startswith('* '):
            items = []
            while i < len(lines) and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('* ')):
                items.append(f'<li>{md_to_html_inline(lines[i].strip()[2:])}</li>')
                i += 1
            html_parts.append(f'<ul>{"".join(items)}</ul>')
            continue
        # Numbered list item
        elif re.match(r'^\d+\.', line):
            items = []
            while i < len(lines) and re.match(r'^\d+\.', lines[i].strip()):
                content = re.sub(r'^\d+\.\s*', '', lines[i].strip())
                items.append(f'<li>{md_to_html_inline(content)}</li>')
                i += 1
            html_parts.append(f'<ol>{"".join(items)}</ol>')
            continue
        # Horizontal rule
        elif line.startswith('---'):
            html_parts.append('<hr class="item-divider">')
        # Regular paragraph
        else:
            html_parts.append(f'<p>{md_to_html_inline(line)}</p>')
        i += 1

    return '\n'.join(html_parts)

def parse_sections(briefing_text: str) -> list[dict]:
    """Split the briefing into named sections."""
    # Match ## headers (with or without leading emoji)
    pattern = re.compile(r'^##\s+(.+?)$', re.MULTILINE)
    matches = list(pattern.finditer(briefing_text))
    sections = []
    for idx, match in enumerate(matches):
        raw_title = match.group(1).strip()
        meta_key, meta = find_section_meta(raw_title)
        if not meta_key:
            continue
        emoji, css_class, display_title, compact = meta
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(briefing_text)
        body_raw = briefing_text[start:end].strip()
        sections.append({
            "key":       meta_key,
            "emoji":     emoji,
            "class":     css_class,
            "title":     display_title,
            "compact":   compact,
            "body_raw":  body_raw,
            "body_html": render_section_body(body_raw),
        })
    return sections

# ─── HTML Builder ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0a0a0a">
<title>Daily Briefing — {date}</title>
<style>
  :root {{
    --bg:       #0a0a0a;
    --surface:  #141414;
    --border:   #232323;
    --text:     #e8e8e8;
    --muted:    #888;
    --accent:   #f0a500;
    --insight:  #1a3a2a;
    --insight-t:#4ade80;
    --source:   #2a2a2a;
    --radius:   10px;
    --font:     -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --mono:     'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ background: var(--bg); color: var(--text); font-family: var(--font); }}
  body {{ max-width: 680px; margin: 0 auto; padding: 16px 16px env(safe-area-inset-bottom); }}

  /* Header */
  .header {{ padding: 28px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }}
  .header-eyebrow {{ font-family: var(--mono); font-size: 11px; color: var(--accent); letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 6px; }}
  .header-title {{ font-size: 22px; font-weight: 700; color: var(--text); line-height: 1.2; }}
  .header-sub {{ font-family: var(--mono); font-size: 12px; color: var(--muted); margin-top: 6px; }}

  /* Cards */
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 16px; overflow: hidden; }}
  .card-header {{ display: flex; align-items: center; gap: 10px; padding: 14px 16px 12px; border-bottom: 1px solid var(--border); }}
  .card-emoji {{ font-size: 18px; line-height: 1; }}
  .card-title {{ font-size: 13px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }}
  .card-body {{ padding: 14px 16px 16px; }}

  /* Typography */
  .card-body p {{ font-size: 14px; line-height: 1.65; color: var(--text); margin-bottom: 10px; }}
  .card-body p:last-child {{ margin-bottom: 0; }}
  .card-body h3.item-title {{ font-size: 15px; font-weight: 700; color: var(--text); margin: 18px 0 6px; line-height: 1.35; }}
  .card-body h3.item-title:first-child {{ margin-top: 0; }}
  .card-body h4.item-sub {{ font-size: 13px; font-weight: 600; color: var(--muted); margin: 12px 0 4px; }}
  .card-body ul, .card-body ol {{ padding-left: 20px; margin-bottom: 10px; }}
  .card-body li {{ font-size: 14px; line-height: 1.6; margin-bottom: 4px; }}
  .card-body hr.item-divider {{ border: none; border-top: 1px solid var(--border); margin: 16px 0; }}
  .card-body code {{ font-family: var(--mono); font-size: 12px; background: #1e1e1e; padding: 1px 5px; border-radius: 3px; }}
  .card-body strong {{ color: #fff; font-weight: 600; }}
  .card-body em {{ color: #ccc; font-style: italic; }}

  /* Special paragraph types */
  p.insight {{ background: var(--insight); border-left: 3px solid var(--insight-t); border-radius: 0 6px 6px 0; padding: 8px 12px; color: var(--insight-t); font-size: 13px; margin: 8px 0 10px; }}
  p.snack-label {{ font-size: 14px; font-weight: 600; color: var(--accent); margin-top: 14px; margin-bottom: 4px; }}
  p.snack-label:first-child {{ margin-top: 0; }}
  p.source {{ font-family: var(--mono); font-size: 11px; color: var(--muted); background: var(--source); border-radius: 4px; padding: 4px 8px; margin-top: 4px; }}

  /* Summary grid (end-section compact cards) */
  .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }}
  .summary-grid .card {{ margin-bottom: 0; }}
  .summary-grid .card-body p {{ font-size: 13px; }}
  @media (max-width: 480px) {{
    .summary-grid {{ grid-template-columns: 1fr; }}
  }}

  /* Footer */
  .footer {{ text-align: center; padding: 20px 0 28px; font-family: var(--mono); font-size: 11px; color: var(--muted); border-top: 1px solid var(--border); margin-top: 8px; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-eyebrow">Intelligence Briefing</div>
  <div class="header-title">Good morning, Stephan.</div>
  <div class="header-sub">{date} &nbsp;·&nbsp; Generated {time} CET</div>
</div>

{cards}

<div class="footer">
  Generated by Gemini 2.0 Flash &nbsp;·&nbsp; {date}
</div>

</body>
</html>"""

def build_html(sections: list[dict], date_label: str, time_label: str) -> str:
    main_cards = []
    compact_cards = []

    for s in sections:
        card = f"""<div class="card section-{s['class']}">
  <div class="card-header">
    <span class="card-emoji">{s['emoji']}</span>
    <span class="card-title">{s['title']}</span>
  </div>
  <div class="card-body">
{s['body_html']}
  </div>
</div>"""
        if s["compact"]:
            compact_cards.append(card)
        else:
            main_cards.append(card)

    summary_block = ""
    if compact_cards:
        summary_block = (
            '<div class="summary-grid">\n'
            + "\n".join(compact_cards)
            + "\n</div>"
        )

    return HTML_TEMPLATE.format(
        date=date_label,
        time=time_label,
        cards="\n".join(main_cards) + "\n" + summary_block,
    )

# ─── Delivery: GitHub Pages ────────────────────────────────────────────────────

def save_html(html: str, path: str = "docs/index.html") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Saved HTML → {path}")

# ─── Delivery: Gmail ──────────────────────────────────────────────────────────

def send_email(html: str, date_label: str) -> None:
    subject = f"Daily Briefing — {date_label}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECIPIENT_EMAIL

    # Plain-text fallback (minimal)
    plain = f"Daily Briefing — {date_label}\n\nOpen the HTML version for the full briefing."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    print("📧 Sending email…")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
    print("✅ Email sent")

# ─── Delivery: Telegram ───────────────────────────────────────────────────────

MAX_TG = 4000  # conservative limit below Telegram's 4096

def sections_to_telegram(sections: list[dict], date_label: str) -> str:
    """Build a condensed plain-text Telegram message."""
    lines = [f"📋 *Daily Briefing — {date_label}*\n"]
    for s in sections:
        lines.append(f"\n{s['emoji']} *{s['title']}*")
        # Strip HTML tags for plain text
        clean = re.sub(r'<[^>]+>', '', s['body_html'])
        # Collapse blank lines
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        lines.append(clean.strip())
    full = "\n".join(lines)
    if len(full) > MAX_TG:
        full = full[:MAX_TG] + "\n\n_[truncated — see web version]_"
    return full

def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⏭️  Telegram not configured — skipping")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print("📱 Sending Telegram message…")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    if result.get("ok"):
        print("✅ Telegram sent")
    else:
        print(f"❌ Telegram error: {result}", file=sys.stderr)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    time_label = TODAY.strftime("%H:%M")

    print(f"🗓️  Generating briefing for {DATE_LABEL}")
    raw_briefing = generate_briefing()

    # Optionally save raw markdown for archiving
    archive_dir = os.environ.get("ARCHIVE_DIR", "")
    if archive_dir:
        os.makedirs(archive_dir, exist_ok=True)
        with open(f"{archive_dir}/{ISO_DATE}.md", "w") as f:
            f.write(raw_briefing)
        print(f"✅ Archived raw markdown → {archive_dir}/{ISO_DATE}.md")

    sections = parse_sections(raw_briefing)
    if not sections:
        print("❌ No sections parsed — dumping raw output:")
        print(raw_briefing[:500])
        sys.exit(1)
    print(f"✅ Parsed {len(sections)} sections")

    html = build_html(sections, DATE_LABEL, time_label)
    save_html(html)

    send_email(html, DATE_LABEL)

    tg_text = sections_to_telegram(sections, DATE_LABEL)
    send_telegram(tg_text)

    print(f"\n✅ Briefing complete — {DATE_LABEL}")

if __name__ == "__main__":
    main()
