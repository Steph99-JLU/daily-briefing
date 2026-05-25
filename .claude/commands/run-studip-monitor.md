---
description: Run the weekly StudIP monitor and commit the report
argument-hint: "[--since YYYY-MM-DD]"
allowed-tools: Bash(python monitors/studip_monitor.py:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(git status:*), Read
---

Run the weekly StudIP monitor for my JLU Gießen courses.

1. Execute: `python monitors/studip_monitor.py $ARGUMENTS`
2. If it exits complaining about a missing environment variable, stop and tell
   me which of these to set, then wait — do not invent values:
   `STUDIP_USERNAME` + `STUDIP_PASSWORD` (or `STUDIP_TOKEN`), and optionally
   `STUDIP_URL` if it is not the JLU instance.
3. On success, read the report it wrote under `monitors/reports/studip/` (the
   file named with today's date) and give me a tight summary in the session:
   new materials, upcoming deadlines/dates, unread messages, and announcements.
   If the report's "Endpoints that could not be read" section is non-empty,
   tell me which routes failed so I can adjust them for the instance version.
4. Commit the new report and the updated `monitors/state.json` with message
   `studip monitor: <today's date>`, then push to the current branch.
