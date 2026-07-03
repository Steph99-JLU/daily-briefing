---
name: daily-briefing
description: Generate Stephan's Daily Intelligence Briefing from today's Gmail newsletters (TLDR AI/Founders/IT/Crypto/Dev/DevOps/InfoSec/standard) — real Gmail read + article crawl + narrow claim verification, written to archive/YYYY-MM-DD.md. Use when asked to run, generate, or update the daily briefing.
---

Run the full process described in `PROMPT.md` at the repository root:

1. Pull today's (or the most recent weekday's) emails from the PRIMARY_SENDERS list via Gmail.
2. Flag any newsletter-style sender not on the whitelist under "NEW SENDER DETECTED".
3. Crawl every extracted article link (native fetch first, Chrome fallback, else `[blurb only]`).
4. Dedupe stories across newsletters, filter for relevance, verify the few high-impact/surprising claims (cap 5) against independent Tier-1/2 sources, enrich the top 1-3 headlines (cap 3).
5. Write the themed briefing (HEADLINES / AI & RESEARCH / BUSINESS, FOUNDERS & STRATEGY / DEV, DEVOPS & INFRA / OTHER) plus the ANALYST TAKE / WATCH-ACTION / VERIFICATION LOG / SOURCE LIST close, per the exact format and word-count target in `PROMPT.md`.
6. Save the result to `archive/YYYY-MM-DD.md`.

Read `PROMPT.md` in full before starting — it is the source of truth for tone, section structure, caps, and the brevity-first prime directive. Do not shorten or paraphrase the spec; follow it exactly.
