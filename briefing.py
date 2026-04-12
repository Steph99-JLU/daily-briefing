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

# Rotate skill snack topics: week number drives deterministic rotation
WEEK = TODAY.isocalendar()[1]
SKILL_ROTATION = ["PowerPoint", "Excel", "Python", "AI Prompting", "Consulting Craft"]
SKILL_A = SKILL_ROTATION[WEEK % len(SKILL_ROTATION)]
SKILL_B = SKILL_ROTATION[(WEEK + 1) % len(SKILL_ROTATION)]

# ─── Gemini Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are Stephan's personal intelligence analyst. Your job is to write his daily briefing — concise, sourced, opinionated.

ABOUT STEPHAN:
- Stephan Alber, 25, IT Consulting & CIO Advisory at PwC Germany
- Master's in Data Analytics, JLU Gießen (completed thesis)
- Interests: AI/tech, macro economics, personal finance, European regulation (DORA, NIS2, CSRD), geopolitics
- Eintracht Frankfurt fan and football player

EDITORIAL VOICE:
- The Economist tone: precise, dry, data-driven — never LinkedIn inspirational
- No filler phrases, no exclamation marks, no "fascinating" or "exciting"
- Every item must include a "→ 💡 Why it matters for Stephan:" line with a specific, actionable insight for his PwC CIO advisory work or personal finance
- Include source name and approximate date where possible
- Bold the most important number or fact in each item

OUTPUT FORMAT — use exactly these section headers, nothing else:

## ⚡ SKILL SNACKS
[Two skill snacks: one on {SKILL_A}, one on {SKILL_B}. Each 3–4 sentences. Practical, immediately applicable. Label them **{SKILL_A} Snack:** and **{SKILL_B} Snack:**]

## 📈 MACRO & MARKETS
[Top 3 macro/market moves. Each: headline in bold, 4–6 sentences with context, → 💡 line. Include specific numbers: rates, index levels, % moves.]

## 🤖 AI & TECH
[Top 5 AI/tech news items. Format same as macro. Signal over noise — no product launches unless strategically significant. Focus on structural shifts, funding rounds >$100M, capability breakthroughs, regulatory moves.]

## 🌍 GEOPOLITICS & DEFENSE
[Top 3 geopolitical developments. Same format. European perspective where relevant. DORA/NIS2/CSRD regulatory developments count here.]

## 💼 PWC CONVERSATION STARTER
[1 topic that will come up in CIO client conversations this week. 5–8 sentences. Specific enough to use in a steering committee or partner call. Include a suggested framing or talking point.]

## ⚽ EINTRACHT FRANKFURT
[Match result, upcoming fixture, or squad news if relevant. If nothing significant happened in the last 48h, write "No major update." — never fabricate scores or transfers.]

Today is {DATE_LABEL}. Write the briefing now.
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
    "SKILL SNACKS":            ("⚡", "skill",       "Daily Skill Snacks"),
    "MACRO & MARKETS":         ("📈", "macro",       "Macro & Markets"),
    "AI & TECH":               ("🤖", "ai",          "AI & Tech"),
    "GEOPOLITICS & DEFENSE":   ("🌍", "geo",         "Geopolitics & Defense"),
    "PWC CONVERSATION STARTER":("💼", "pwc",         "PwC Conversation Starter"),
    "EINTRACHT FRANKFURT":     ("⚽", "eintracht",   "Eintracht Frankfurt"),
}

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
    # Match section headers like: ## ⚡ SKILL SNACKS
    pattern = re.compile(r'^##\s+[^\s]*\s+(.+?)$', re.MULTILINE)
    matches = list(pattern.finditer(briefing_text))
    sections = []
    for idx, match in enumerate(matches):
        raw_title = match.group(1).strip().upper()
        # Find the matching meta entry
        meta_key = next((k for k in SECTION_META if k in raw_title), None)
        if not meta_key:
            continue
        emoji, css_class, display_title = SECTION_META[meta_key]
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(briefing_text)
        body_raw = briefing_text[start:end].strip()
        sections.append({
            "key":       meta_key,
            "emoji":     emoji,
            "class":     css_class,
            "title":     display_title,
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

  /* Footer */
  .footer {{ text-align: center; padding: 20px 0 28px; font-family: var(--mono); font-size: 11px; color: var(--muted); border-top: 1px solid var(--border); margin-top: 8px; }}

  /* Dark mode already — no toggle needed */
  @media (prefers-color-scheme: light) {{
    /* Keep dark regardless of system setting — this is a dashboard */
  }}
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
    cards_html = []
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
        cards_html.append(card)
    return HTML_TEMPLATE.format(
        date=date_label,
        time=time_label,
        cards="\n".join(cards_html),
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
