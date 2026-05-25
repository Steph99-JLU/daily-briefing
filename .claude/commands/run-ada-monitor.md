---
description: Run the weekly GitLab ADA monitor and commit the report
argument-hint: "[--since YYYY-MM-DD]"
allowed-tools: Bash(python monitors/gitlab_ada_monitor.py:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(git status:*), Read
---

Run the weekly GitLab ADA monitor.

1. Execute: `python monitors/gitlab_ada_monitor.py $ARGUMENTS`
2. If it exits complaining about a missing environment variable, stop and tell
   me which of these to set, then wait — do not invent values:
   `GITLAB_URL`, `GITLAB_TOKEN`, `GITLAB_ADA_PROJECT`.
3. On success, read the report it wrote under `monitors/reports/ada/` (the file
   named with today's date) and give me a tight summary in the session:
   highlight failed pipelines, milestones due in the next 14 days, and anything
   that looks like it needs my attention. Keep it short.
4. Commit the new report and the updated `monitors/state.json` with message
   `ada monitor: <today's date>`, then push to the current branch.
