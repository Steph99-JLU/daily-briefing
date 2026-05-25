#!/usr/bin/env python3
"""GitLab ADA monitor — weekly digest of activity on the ADA GitLab project.

Reports, for the window since the last run (or the last 7 days):
  - new commits
  - merge requests created/updated
  - issues created/updated
  - pipelines run (with status)
  - open milestones and their due dates

Output: a dated markdown report under monitors/reports/ada/ plus a short
stdout summary. No external delivery.

Config (environment variables):
  GITLAB_URL          base instance URL          (default https://gitlab.com)
  GITLAB_TOKEN        personal/project access token with read_api scope  (required)
  GITLAB_ADA_PROJECT  project id or full path, e.g. "mygroup/ada"         (required)
  MONITOR_LOOKBACK_DAYS  fallback window when no prior run is recorded    (default 7)

Usage:
  python monitors/gitlab_ada_monitor.py [--since 2026-05-18] [--no-state]
"""

import argparse
import urllib.parse
from datetime import datetime

import common

MONITOR = "ada"


def gl_get(base: str, token: str, path: str, params: dict) -> list:
    """GET a GitLab REST endpoint, following Link-header pagination."""
    params = {**params, "per_page": 100}
    url = f"{base}/api/v4{path}?{urllib.parse.urlencode(params)}"
    headers = {"PRIVATE-TOKEN": token}
    results: list = []
    while url:
        page, resp_headers = common.http_get(url, headers=headers)
        if isinstance(page, list):
            results.extend(page)
        else:
            return page  # single-object endpoint
        url = _next_link(resp_headers.get("Link", ""))
    return results


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) >= 2 and 'rel="next"' in segments[1]:
            return segments[0].strip().strip("<>")
    return None


def fetch(base: str, token: str, project: str, since: datetime) -> dict:
    pid = urllib.parse.quote(project, safe="")
    since_iso = since.isoformat()
    p = f"/projects/{pid}"
    return {
        "commits": gl_get(base, token, f"{p}/repository/commits", {"since": since_iso, "all": "true"}),
        "mrs": gl_get(base, token, f"{p}/merge_requests", {"updated_after": since_iso, "order_by": "updated_at", "sort": "desc", "scope": "all"}),
        "issues": gl_get(base, token, f"{p}/issues", {"updated_after": since_iso, "order_by": "updated_at", "sort": "desc", "scope": "all"}),
        "pipelines": gl_get(base, token, f"{p}/pipelines", {"updated_after": since_iso, "order_by": "updated_at", "sort": "desc"}),
        "milestones": gl_get(base, token, f"{p}/milestones", {"state": "active"}),
    }


def render(data: dict, project: str, since: datetime) -> str:
    L: list[str] = []
    L.append(f"# GitLab ADA monitor — {common.iso_date()}")
    L.append("")
    L.append(f"Project: `{project}` · Window since: {since.strftime('%Y-%m-%d %H:%M')} CET")
    L.append("")

    commits = data["commits"]
    L.append(f"## Commits ({len(commits)})")
    if not commits:
        L.append("_No new commits._")
    for c in commits[:50]:
        title = c.get("title", "").strip()
        author = c.get("author_name", "?")
        short = c.get("short_id", "")
        date = (c.get("committed_date") or "")[:10]
        L.append(f"- `{short}` {title} — {author}, {date}")
    L.append("")

    mrs = data["mrs"]
    L.append(f"## Merge requests ({len(mrs)})")
    if not mrs:
        L.append("_No merge request activity._")
    for m in mrs[:50]:
        L.append(f"- !{m.get('iid')} [{m.get('state')}] {m.get('title','').strip()} — {m.get('author',{}).get('username','?')}")
    L.append("")

    issues = data["issues"]
    L.append(f"## Issues ({len(issues)})")
    if not issues:
        L.append("_No issue activity._")
    for i in issues[:50]:
        labels = ", ".join(i.get("labels", []))
        suffix = f" · {labels}" if labels else ""
        L.append(f"- #{i.get('iid')} [{i.get('state')}] {i.get('title','').strip()}{suffix}")
    L.append("")

    pipelines = data["pipelines"]
    failed = [p for p in pipelines if p.get("status") == "failed"]
    L.append(f"## Pipelines ({len(pipelines)}, {len(failed)} failed)")
    if not pipelines:
        L.append("_No pipeline runs._")
    for p in pipelines[:30]:
        flag = " ⚠️" if p.get("status") == "failed" else ""
        L.append(f"- #{p.get('id')} [{p.get('status')}]{flag} ref `{p.get('ref')}`")
    L.append("")

    milestones = data["milestones"]
    L.append(f"## Open milestones ({len(milestones)})")
    if not milestones:
        L.append("_No open milestones._")
    for ms in milestones:
        due = ms.get("due_date") or "no due date"
        L.append(f"- {ms.get('title','').strip()} — due {due}")
    L.append("")

    return "\n".join(L)


def summarize(data: dict) -> str:
    failed = sum(1 for p in data["pipelines"] if p.get("status") == "failed")
    return (
        f"ADA: {len(data['commits'])} commits, {len(data['mrs'])} MRs, "
        f"{len(data['issues'])} issues, {len(data['pipelines'])} pipelines "
        f"({failed} failed), {len(data['milestones'])} open milestones."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Weekly GitLab ADA monitor")
    ap.add_argument("--since", help="ISO date/time window start (overrides stored state)")
    ap.add_argument("--no-state", action="store_true", help="do not update state.json after the run")
    args = ap.parse_args()

    base = common.env("GITLAB_URL", "https://gitlab.com").rstrip("/")
    token = common.env("GITLAB_TOKEN", required=True)
    project = common.env("GITLAB_ADA_PROJECT", required=True)
    lookback = int(common.env("MONITOR_LOOKBACK_DAYS", "7"))

    started = common.now()
    since = common.resolve_since(MONITOR, args.since, lookback)
    print(f"Fetching ADA activity since {since.isoformat()} …")

    data = fetch(base, token, project, since)
    report = render(data, project, since)
    path = common.write_report(MONITOR, report)

    if not args.no_state:
        common.save_state(MONITOR, started)

    print(f"Report written → {path}")
    print(summarize(data))


if __name__ == "__main__":
    main()
