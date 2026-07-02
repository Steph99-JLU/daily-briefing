#!/usr/bin/env python3
"""
Daily Briefing Generator (v7)
Acquires today's TLDR newsletters from Gmail, crawls the linked articles,
synthesizes a sourced briefing via GPT-4o (with live web search for
verification/enrichment), and delivers via GitHub Pages, Gmail, and Telegram.
"""

import email
import hashlib
import imaplib
import json
import os
import re
import smtplib
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# ─── Config ───────────────────────────────────────────────────────────────────

OPENAI_API_KEY      = os.environ["OPENAI_API_KEY"]
GMAIL_ADDRESS       = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD  = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL     = os.environ["RECIPIENT_EMAIL"]
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")

CET = timezone(timedelta(hours=2))  # CEST in summer; adjust to +1 in winter
TODAY = datetime.now(CET)

# newsletters that are the backbone of the briefing (all TLDR verticals)
PRIMARY_SENDER_KEYWORD = "tldr"

# how far back to look for the most recent day that has primary newsletters
MAX_FALLBACK_DAYS = 7

# verification/enrichment caps (see SYSTEM_PROMPT) — enforced via instruction,
# not by the API, since web_search is a single model-directed tool
MAX_VERIFICATION_LOOKUPS = 5
MAX_ENRICHMENT_LOOKUPS   = 3
WORD_TARGET_MIN = 1500
WORD_TARGET_MAX = 2500

# crawl limits
MAX_ARTICLES_TO_CRAWL = 80
ARTICLE_CHAR_LIMIT     = 1500
CRAWL_TIMEOUT_SECONDS  = 10
CRAWL_MAX_WORKERS      = 8

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "ref_src", "fbclid", "gclid", "mc_cid", "mc_eid",
}

EXCLUDE_LINK_SUBSTRINGS = [
    "unsubscribe", "list-manage", "view-in-browser", "view_in_browser",
    "manage-preferences", "manage_subscription", "manage-subscriptions",
    "privacy-policy", "privacypolicy", "advertise", "sponsor-with-us",
    "sponsorship", "twitter.com/intent", "twitter.com/share",
    "facebook.com/sharer", "linkedin.com/share", "t.me/share", "mailto:",
    "tldrnewsletter.com/subscribe", "tldrnewsletter.com/manage",
]

EXCLUDE_ANCHOR_TEXTS = {
    "unsubscribe", "advertise", "view in browser", "manage preferences",
    "privacy policy", "sponsor", "click here", "read more", "learn more",
    "sign up", "subscribe",
}

# ─── Gmail acquisition ──────────────────────────────────────────────────────

def decode_mime_words(raw: str) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    return "".join(
        chunk.decode(enc or "utf-8", errors="ignore") if isinstance(chunk, bytes) else chunk
        for chunk, enc in parts
    )

def get_body_html(msg: email.message.Message) -> str:
    """Return the best HTML (or plain-text) body found in the message."""
    if msg.is_multipart():
        plain_fallback = ""
        for part in msg.walk():
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(charset, errors="ignore")
            elif part.get_content_type() == "text/plain" and not plain_fallback:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    plain_fallback = payload.decode(charset, errors="ignore")
        return plain_fallback
    charset = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    return payload.decode(charset, errors="ignore") if payload else ""

def extract_links(html: str) -> list:
    if "<" not in html:
        return []
    soup = BeautifulSoup(html, "lxml")
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        anchor = a.get_text(" ", strip=True)
        if not href.lower().startswith("http"):
            continue
        low = href.lower()
        if any(p in low for p in EXCLUDE_LINK_SUBSTRINGS):
            continue
        if anchor.lower() in EXCLUDE_ANCHOR_TEXTS or len(anchor) < 8:
            continue
        if href in seen:
            continue
        seen.add(href)
        links.append({"url": href, "anchor": anchor})
    return links

def is_primary_sender(from_header: str) -> bool:
    return PRIMARY_SENDER_KEYWORD in from_header.lower()

def looks_like_bulk_sender(msg: email.message.Message, body: str) -> bool:
    if msg.get("List-Unsubscribe"):
        return True
    return "unsubscribe" in body.lower()[:5000]

def fetch_messages_for_date(imap: imaplib.IMAP4_SSL, day: datetime):
    since = day.strftime("%d-%b-%Y")
    before = (day + timedelta(days=1)).strftime("%d-%b-%Y")
    status, data = imap.search(None, f'(SINCE "{since}" BEFORE "{before}")')
    if status != "OK" or not data or not data[0]:
        return [], []

    newsletters = []
    other_bulk_senders = set()
    for msg_id in data[0].split():
        status, msg_data = imap.fetch(msg_id, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        from_header = decode_mime_words(msg.get("From", ""))
        subject = decode_mime_words(msg.get("Subject", ""))
        body = get_body_html(msg)

        if is_primary_sender(from_header):
            newsletters.append({
                "sender": from_header,
                "subject": subject,
                "links": extract_links(body),
            })
        elif looks_like_bulk_sender(msg, body):
            other_bulk_senders.add(from_header)

    return newsletters, sorted(other_bulk_senders)

def acquire_newsletters():
    """Search backward from today for the most recent day with primary mail."""
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    imap.select("INBOX")
    try:
        for offset in range(MAX_FALLBACK_DAYS):
            day = TODAY - timedelta(days=offset)
            newsletters, other_bulk = fetch_messages_for_date(imap, day)
            if newsletters:
                return newsletters, other_bulk, day
        return [], [], TODAY
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()

# ─── Crawl & dedup ────────────────────────────────────────────────────────────

def crawl_article(url: str):
    """Follow redirects, fetch, and extract the main article text. Returns
    (final_url, text_or_None)."""
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=CRAWL_TIMEOUT_SECONDS, allow_redirects=True)
        final_url = resp.url
        if resp.status_code >= 400 or not resp.text:
            return final_url, None
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        containers = soup.find_all("article") or [soup.body or soup]
        paragraphs = []
        for c in containers:
            paragraphs.extend(p.get_text(" ", strip=True) for p in c.find_all("p"))
        text = " ".join(p for p in paragraphs if len(p) > 40)
        text = text[:ARTICLE_CHAR_LIMIT].strip()
        return final_url, (text or None)
    except Exception:
        return url, None

def normalize_key(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))

def build_article_index(newsletters: list) -> list:
    """Crawl all candidate links, dedup by resolved URL, merge newsletter sources."""
    ordered_refs = []  # (original_url, sender, anchor)
    for nl in newsletters:
        for link in nl["links"]:
            ordered_refs.append((link["url"], nl["sender"], link["anchor"]))

    unique_originals = list(dict.fromkeys(u for u, _, _ in ordered_refs))[:MAX_ARTICLES_TO_CRAWL]
    crawled = {}
    with ThreadPoolExecutor(max_workers=CRAWL_MAX_WORKERS) as pool:
        futures = {pool.submit(crawl_article, u): u for u in unique_originals}
        for fut in as_completed(futures):
            orig = futures[fut]
            crawled[orig] = fut.result()

    articles = {}
    order = []
    for orig_url, sender, anchor in ordered_refs:
        final_url, text = crawled.get(orig_url, (orig_url, None))
        key = normalize_key(final_url)
        if key not in articles:
            articles[key] = {"url": final_url, "anchor": anchor, "sources": set(), "content": text}
            order.append(key)
        articles[key]["sources"].add(sender)
        if not articles[key]["content"] and text:
            articles[key]["content"] = text

    return [articles[k] for k in order]

# ─── Context document + prompt ─────────────────────────────────────────────────

DATE_LABEL = TODAY.strftime("%A, %d %B %Y")
ISO_DATE   = TODAY.strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""ROLE: You are Stephan's personal intelligence analyst.
TONE: The Economist — direct, analytical, zero filler. No exclamation marks, no hype, no "in today's fast-moving world" framing.
GOAL: A scannable daily AI/tech briefing synthesized from today's newsletters. Optimize for signal, not length — a sharp 8-minute read beats a padded 25-minute one.

PRIME DIRECTIVE: brevity wins. Verification and enrichment exist to catch errors and add context on the few stories that matter — never to lengthen the briefing. If an addition does not change what a reader should believe or do, cut it.

The SOURCE MATERIAL below was already acquired from today's TLDR newsletters and crawled for full article text where possible. Items marked "[fetch failed]" have no crawled body — treat those as [blurb only] in your output and do not invent details beyond the headline/anchor text given.

You have a live web_search tool. Use it ONLY for these two purposes, and respect the hard caps:
1. VERIFICATION (max {MAX_VERIFICATION_LOOKUPS} lookups total this run): trigger only when a claim is BOTH high-impact AND surprising — funding rounds/valuations/financials, M&A, shutdowns, major leadership moves, benchmark or capability claims ("beats GPT-x", "SOTA"), safety incidents, breaches, regulatory/legal actions, anything a reader would repeat as fact in a professional or investment context. Cross-check against >= 1 INDEPENDENT Tier-1 (company blog, SEC/regulatory filing, arXiv, official product docs, first-party press release) or Tier-2 (Reuters, Bloomberg, FT, The Information, WSJ, Stratechery, official gov/EU source) source — never the original newsletter blurb alone, and never the same article twice. Tag inline: [verified] / [disputed: <what conflicts>] / [unconfirmed]. If more claims qualify than the cap allows, verify the highest-impact first and note the rest as [unverified — over cap].
2. ENRICHMENT (max {MAX_ENRICHMENT_LOOKUPS} lookups total this run, HEADLINES section only): pull one extra independent Tier-1/Tier-2 source per headline to add a number, a counterpoint, or "what's actually new here" that the newsletter omitted. If it adds no signal, drop it — enrichment must earn its words.
Do not use web_search for anything else. Do not exceed the caps.

READ & FILTER: the same story may appear in more than one newsletter below — merge into one item and list all newsletter sources. Rank by significance to someone tracking AI, tech strategy, and infra. Drop sponsor/advertorial content and low-signal trivia. Quality over completeness.

WRITE — organize by THEME, not by newsletter. Use these section headers exactly, as "##" markdown headers, in this order. Skip a section header entirely if nothing qualifies for it (except HEADLINES, ANALYST TAKE, WATCH / ACTION, VERIFICATION LOG, and SOURCE LIST, which are always included):

## HEADLINES
The 1-3 most consequential stories today. 3-4 sentences each.

## AI & RESEARCH
Models, capabilities, papers, lab moves.

## BUSINESS, FOUNDERS & STRATEGY
Funding, business models, market moves.

## DEV, DEVOPS & INFRA
Tooling, platforms, security (incl. InfoSec).

## OTHER
Crypto and general items worth keeping.

Per item (sections after HEADLINES):
<sharp headline> — what happened (2-3 sentences).
Why it matters: one line of analysis/implication.
(sources: <newsletters>) [verification tag if applicable] [blurb only if applicable]

CLOSE — always include, in this exact order:

## ANALYST TAKE
3-5 bullets connecting the dots across today's stories — the trend or tension to walk away with. This is the value-add, not a recap.

## WATCH / ACTION
2-4 bullets: releases to try, deadlines, risks.

## VERIFICATION LOG
One line: how many claims were checked this run, and any that came back [disputed] or [unconfirmed]. If nothing was verified, say "no high-impact claims triggered verification."

## SOURCE LIST
Every underlying article you used, grouped by the section it appeared in, formatted as "Title — full URL". Mark [blurb only] items. Use ONLY URLs given in the SOURCE MATERIAL below — never invent a URL.

LENGTH: total {WORD_TARGET_MIN}-{WORD_TARGET_MAX} words across the whole briefing; cut below if today is thin. Never pad to hit a number. Each item 2-4 sentences.
"""

def build_context_document(articles: list, newsletters: list, other_bulk: list, date_used: datetime) -> str:
    lines = [f"Date used for this briefing: {date_used.strftime('%A, %d %B %Y')}"]
    if date_used.date() != TODAY.date():
        lines.append(
            f"NOTE: no primary newsletters were received on {DATE_LABEL}; "
            f"falling back to the most recent day that has them."
        )
    senders = sorted(set(nl["sender"] for nl in newsletters))
    lines.append(f"Newsletters received: {len(newsletters)} ({', '.join(senders)})")
    lines.append(f"Unique articles extracted after URL dedup: {len(articles)}")
    lines.append("")

    for i, art in enumerate(articles, 1):
        srcs = ", ".join(sorted(art["sources"]))
        lines.append(f"[{i}] {art['anchor']}")
        lines.append(f"URL: {art['url']}")
        lines.append(f"Newsletter source(s): {srcs}")
        if art["content"]:
            lines.append(f"Extracted article text: {art['content']}")
        else:
            lines.append("Extracted article text: [fetch failed — use headline/blurb only, tag as [blurb only]]")
        lines.append("")

    if other_bulk:
        lines.append("OTHER NEWSLETTER-STYLE SENDERS DETECTED TODAY (not yet whitelisted as PRIMARY_SENDERS):")
        for s in other_bulk:
            lines.append(f"- {s}")

    return "\n".join(lines)

# ─── LLM call ──────────────────────────────────────────────────────────────────

def call_llm(context_doc: str):
    """Returns (briefing_markdown, used_web_search: bool)."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    full_input = SYSTEM_PROMPT + "\n\n=== SOURCE MATERIAL ===\n\n" + context_doc

    try:
        print("⏳ Calling GPT-4o with live web search…")
        response = client.responses.create(
            model="gpt-4o",
            input=full_input,
            tools=[{"type": "web_search_preview"}],
            max_output_tokens=6000,
        )
        text = getattr(response, "output_text", "") or ""
        if text.strip():
            print(f"✅ Received {len(text)} chars (web search enabled)")
            return text, True
        print("⚠️ Empty response from web-search call, falling back")
    except Exception as e:
        print(f"⚠️ web_search-enabled call failed ({e}); falling back to plain completion")

    print("⏳ Calling GPT-4o (no live search)…")
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=6000,
        messages=[{"role": "user", "content": full_input}],
    )
    text = response.choices[0].message.content
    print(f"✅ Received {len(text)} chars (no web search)")
    return text, False

# ─── Markdown → HTML Renderer ─────────────────────────────────────────────────

SECTION_META = {
    "HEADLINES":                        ("📰", "headlines", "Headlines",                   False),
    "AI RESEARCH":                       ("🤖", "ai",        "AI & Research",               False),
    "BUSINESS FOUNDERS STRATEGY":       ("💼", "business",  "Business, Founders & Strategy",False),
    "DEV DEVOPS INFRA":                 ("🛠️", "devops",   "Dev, DevOps & Infra",         False),
    "OTHER":                             ("🌐", "other",     "Other (Crypto & General)",    False),
    "ANALYST TAKE":                      ("🧠", "takeaway",  "Analyst Take",                True),
    "WATCH ACTION":                      ("📌", "watch",     "Watch / Action",              True),
    "VERIFICATION LOG":                  ("✅", "verify",    "Verification Log",            True),
    "SOURCE LIST":                       ("🔗", "sources",   "Source List",                 True),
}

def find_section_meta(raw_title: str):
    upper = raw_title.upper()
    upper_words = set(upper.replace("/", " ").replace("&", " ").replace(",", " ").split())
    for key, meta in SECTION_META.items():
        key_words = set(key.replace("/", " ").split())
        if key_words and key_words.issubset(upper_words):
            return key, meta
    return None, None

def md_to_html_inline(text: str) -> str:
    """Convert inline markdown (links, bold, italic, code) to HTML."""
    # Markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    # Bare URLs not already inside an href/quote
    text = re.sub(r'(?<!["\'>])(https?://[^\s<]+)', r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)
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

        if line.startswith('### '):
            html_parts.append(f'<h3 class="item-title">{md_to_html_inline(line[4:])}</h3>')
        elif line.startswith('#### '):
            html_parts.append(f'<h4 class="item-sub">{md_to_html_inline(line[5:])}</h4>')
        elif line.lower().startswith('why it matters'):
            html_parts.append(f'<p class="insight">{md_to_html_inline(line)}</p>')
        elif line.lower().startswith('(sources:') or line.lower().startswith('source:'):
            html_parts.append(f'<p class="source">{md_to_html_inline(line)}</p>')
        elif line.startswith('- ') or line.startswith('* '):
            items = []
            while i < len(lines) and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('* ')):
                items.append(f'<li>{md_to_html_inline(lines[i].strip()[2:])}</li>')
                i += 1
            html_parts.append(f'<ul>{"".join(items)}</ul>')
            continue
        elif re.match(r'^\d+\.', line):
            items = []
            while i < len(lines) and re.match(r'^\d+\.', lines[i].strip()):
                content = re.sub(r'^\d+\.\s*', '', lines[i].strip())
                items.append(f'<li>{md_to_html_inline(content)}</li>')
                i += 1
            html_parts.append(f'<ol>{"".join(items)}</ol>')
            continue
        elif line.startswith('---'):
            html_parts.append('<hr class="item-divider">')
        else:
            html_parts.append(f'<p>{md_to_html_inline(line)}</p>')
        i += 1

    return '\n'.join(html_parts)

def parse_sections(briefing_text: str) -> list:
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
    --banner:   #3a2a0a;
    --banner-t: #f0a500;
    --radius:   10px;
    --font:     -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --mono:     'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ background: var(--bg); color: var(--text); font-family: var(--font); }}
  body {{ max-width: 680px; margin: 0 auto; padding: 16px 16px env(safe-area-inset-bottom); }}
  a {{ color: var(--accent); }}

  /* Header */
  .header {{ padding: 28px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }}
  .header-eyebrow {{ font-family: var(--mono); font-size: 11px; color: var(--accent); letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 6px; }}
  .header-title {{ font-size: 22px; font-weight: 700; color: var(--text); line-height: 1.2; }}
  .header-sub {{ font-family: var(--mono); font-size: 12px; color: var(--muted); margin-top: 6px; }}
  .stats-line {{ font-family: var(--mono); font-size: 11px; color: var(--muted); margin-top: 8px; }}

  /* New-sender banner */
  .banner {{ background: var(--banner); border: 1px solid var(--banner-t); border-radius: var(--radius); padding: 12px 14px; margin-bottom: 16px; font-size: 13px; color: var(--banner-t); line-height: 1.5; }}
  .banner strong {{ color: #fff; }}

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
  p.source {{ font-family: var(--mono); font-size: 11px; color: var(--muted); background: var(--source); border-radius: 4px; padding: 4px 8px; margin-top: 4px; word-break: break-word; }}

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
  <div class="stats-line">{stats_line}</div>
</div>

{banner}
{cards}

<div class="footer">
  Generated by GPT-4o{search_note} &nbsp;·&nbsp; {date}
</div>

</body>
</html>"""

def build_html(sections: list, date_label: str, time_label: str, stats_line: str,
                other_bulk: list, used_web_search: bool) -> str:
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
        summary_block = '<div class="summary-grid">\n' + "\n".join(compact_cards) + "\n</div>"

    banner = ""
    if other_bulk:
        senders_list = ", ".join(other_bulk)
        banner = (
            f'<div class="banner"><strong>NEW SENDER DETECTED</strong> — received today but not in '
            f'PRIMARY_SENDERS: {senders_list}. Promote in briefing.py if this should be ingested going forward.</div>'
        )

    search_note = " + live web search" if used_web_search else " (no live search — verification/enrichment skipped)"

    return HTML_TEMPLATE.format(
        date=date_label,
        time=time_label,
        stats_line=stats_line,
        banner=banner,
        cards="\n".join(main_cards) + "\n" + summary_block,
        search_note=search_note,
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

def sections_to_telegram(sections: list, date_label: str) -> str:
    lines = [f"📋 *Daily Briefing — {date_label}*\n"]
    for s in sections:
        lines.append(f"\n{s['emoji']} *{s['title']}*")
        clean = re.sub(r'<[^>]+>', '', s['body_html'])
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
    print("📥 Acquiring today's newsletters from Gmail…")
    newsletters, other_bulk, date_used = acquire_newsletters()
    if not newsletters:
        print("❌ No primary newsletters found in the last "
              f"{MAX_FALLBACK_DAYS} days — nothing to brief. Exiting.")
        sys.exit(1)
    print(f"✅ {len(newsletters)} newsletters found for {date_used.strftime('%Y-%m-%d')}")

    print("🔗 Crawling and deduplicating article links…")
    articles = build_article_index(newsletters)
    print(f"✅ {len(articles)} unique articles after dedup "
          f"({sum(1 for a in articles if a['content'])} crawled, "
          f"{sum(1 for a in articles if not a['content'])} blurb-only)")

    context_doc = build_context_document(articles, newsletters, other_bulk, date_used)

    archive_dir = os.environ.get("ARCHIVE_DIR", "")
    if archive_dir:
        os.makedirs(archive_dir, exist_ok=True)
        with open(f"{archive_dir}/{ISO_DATE}.context.md", "w") as f:
            f.write(context_doc)

    raw_briefing, used_web_search = call_llm(context_doc)

    if archive_dir:
        with open(f"{archive_dir}/{ISO_DATE}.md", "w") as f:
            f.write(raw_briefing)
        print(f"✅ Archived raw markdown → {archive_dir}/{ISO_DATE}.md")

    sections = parse_sections(raw_briefing)
    if not sections:
        print("❌ No sections parsed — dumping raw output:")
        print(raw_briefing[:500])
        sys.exit(1)
    print(f"✅ Parsed {len(sections)} sections")

    stats_line = (
        f"{len(newsletters)} newsletters &nbsp;·&nbsp; {len(articles)} unique articles"
    )
    html = build_html(sections, DATE_LABEL, time_label, stats_line, other_bulk, used_web_search)
    save_html(html)

    send_email(html, DATE_LABEL)

    tg_text = sections_to_telegram(sections, DATE_LABEL)
    send_telegram(tg_text)

    print(f"\n✅ Briefing complete — {DATE_LABEL}")

if __name__ == "__main__":
    main()
