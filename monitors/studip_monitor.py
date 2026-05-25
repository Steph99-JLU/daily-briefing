#!/usr/bin/env python3
"""StudIP monitor — weekly digest of activity across your JLU Gießen courses.

Reports, for the window since the last run (or the last 7 days):
  - new files / materials uploaded to your courses
  - announcements / news postings
  - new inbox messages and forum activity
  - upcoming dates / schedule entries (deadlines)

Talks to the classic Stud.IP REST API ("/api.php/...") with HTTP Basic Auth.
Endpoint route names vary slightly between Stud.IP versions, so each probe is
non-fatal: if one route is missing on your instance, the report flags it and
the rest still run. Adjust the *_PATH constants below if your instance differs.

Output: a dated markdown report under monitors/reports/studip/ plus a short
stdout summary. No external delivery.

Config (environment variables):
  STUDIP_URL        instance base URL   (default https://studip.uni-giessen.de)
  STUDIP_API_PATH   REST API path       (default /api.php)
  STUDIP_USERNAME   account username    (required unless STUDIP_TOKEN is set)
  STUDIP_PASSWORD   account password    (required unless STUDIP_TOKEN is set)
  STUDIP_TOKEN      OAuth/bearer token  (alternative to username/password)
  MONITOR_LOOKBACK_DAYS  fallback window when no prior run is recorded (default 7)

Usage:
  python monitors/studip_monitor.py [--since 2026-05-18] [--no-state]
"""

import argparse
from datetime import datetime

import common

MONITOR = "studip"


def auth_headers() -> dict:
    token = common.env("STUDIP_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    user = common.env("STUDIP_USERNAME", required=True)
    pwd = common.env("STUDIP_PASSWORD", required=True)
    return common.basic_auth_header(user, pwd)


def collection_items(payload) -> list:
    """Classic Stud.IP wraps lists as {"collection": {id: {...}}}; normalise to a list."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        coll = payload.get("collection", payload)
        if isinstance(coll, dict):
            out = []
            for key, val in coll.items():
                if isinstance(val, dict):
                    val.setdefault("_id", key)
                    out.append(val)
            return out
        if isinstance(coll, list):
            return coll
    return []


def item_timestamp(item: dict) -> int | None:
    """Best-effort extraction of a unix timestamp from common Stud.IP date fields."""
    for field in ("chdate", "mkdate", "date", "start_time", "timestamp"):
        val = item.get(field)
        if val is None:
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            try:
                return int(common.parse_iso(str(val)).timestamp())
            except ValueError:
                continue
    return None


def newer_than(items: list, since_ts: int) -> list:
    """Keep items whose timestamp is >= since; undated items are kept (flagged later)."""
    kept = []
    for it in items:
        ts = item_timestamp(it)
        if ts is None or ts >= since_ts:
            kept.append(it)
    return kept


class StudIP:
    def __init__(self, base: str, api_path: str, headers: dict):
        self.api = f"{base}{api_path}".rstrip("/")
        self.headers = headers
        self.errors: list[str] = []

    def get(self, route: str):
        url = f"{self.api}/{route.lstrip('/')}?limit=100"
        data, _, err = common.http_try_get(url, headers=self.headers)
        if err:
            self.errors.append(f"{route}: {err}")
            return None
        return data

    def current_user_id(self) -> str | None:
        data = self.get("user")
        if isinstance(data, dict):
            return data.get("user_id") or data.get("_id") or data.get("id")
        return None

    def courses(self, uid: str) -> list:
        return collection_items(self.get(f"user/{uid}/courses"))


def gather(client: StudIP, since_ts: int) -> dict:
    uid = client.current_user_id()
    result = {"files": [], "news": [], "messages": [], "forum": [], "dates": [], "courses": []}

    if not uid:
        return result  # client.errors already records why

    inbox = newer_than(collection_items(client.get(f"user/{uid}/inbox")), since_ts)
    result["messages"] = inbox

    for course in client.courses(uid):
        cid = course.get("course_id") or course.get("_id") or course.get("id")
        ctitle = (course.get("title") or course.get("name") or cid or "?").strip()
        if not cid:
            continue
        result["courses"].append(ctitle)

        for it in newer_than(collection_items(client.get(f"course/{cid}/documents")), since_ts):
            it["_course"] = ctitle
            result["files"].append(it)
        for it in newer_than(collection_items(client.get(f"course/{cid}/news")), since_ts):
            it["_course"] = ctitle
            result["news"].append(it)
        for it in newer_than(collection_items(client.get(f"course/{cid}/forum_categories")), since_ts):
            it["_course"] = ctitle
            result["forum"].append(it)
        for it in newer_than(collection_items(client.get(f"course/{cid}/dates")), since_ts):
            it["_course"] = ctitle
            result["dates"].append(it)

    return result


def _name(item: dict, *fields: str) -> str:
    for f in fields:
        if item.get(f):
            return str(item[f]).strip()
    return "(untitled)"


def render(data: dict, errors: list[str], since: datetime) -> str:
    L: list[str] = []
    L.append(f"# StudIP monitor — {common.iso_date()}")
    L.append("")
    L.append(f"Courses scanned: {len(data['courses'])} · Window since: {since.strftime('%Y-%m-%d %H:%M')} CET")
    L.append("")

    files = data["files"]
    L.append(f"## New files / materials ({len(files)})")
    if not files:
        L.append("_No new files._")
    for it in files[:60]:
        L.append(f"- [{it.get('_course','?')}] {_name(it, 'name', 'filename')}")
    L.append("")

    news = data["news"]
    L.append(f"## Announcements / news ({len(news)})")
    if not news:
        L.append("_No new announcements._")
    for it in news[:40]:
        L.append(f"- [{it.get('_course','?')}] {_name(it, 'topic', 'title', 'subject')}")
    L.append("")

    messages = data["messages"]
    L.append(f"## Inbox messages ({len(messages)})")
    if not messages:
        L.append("_No new messages._")
    for it in messages[:40]:
        L.append(f"- {_name(it, 'subject')} — from {_name(it, 'sender', 'autor')}")
    L.append("")

    forum = data["forum"]
    L.append(f"## Forum activity ({len(forum)})")
    if not forum:
        L.append("_No forum activity (or forum route unavailable)._")
    for it in forum[:40]:
        L.append(f"- [{it.get('_course','?')}] {_name(it, 'entry_name', 'name', 'topic')}")
    L.append("")

    dates = data["dates"]
    L.append(f"## Dates / deadlines ({len(dates)})")
    if not dates:
        L.append("_No upcoming dates._")
    for it in dates[:40]:
        when = it.get("start_time") or it.get("date") or "?"
        L.append(f"- [{it.get('_course','?')}] {_name(it, 'title', 'topic')} — {when}")
    L.append("")

    if errors:
        L.append("## ⚠️ Endpoints that could not be read")
        L.append("_Adjust the route paths in studip_monitor.py for your Stud.IP version._")
        for e in errors[:20]:
            L.append(f"- {e}")
        L.append("")

    return "\n".join(L)


def summarize(data: dict, errors: list[str]) -> str:
    base = (
        f"StudIP: {len(data['files'])} files, {len(data['news'])} announcements, "
        f"{len(data['messages'])} messages, {len(data['forum'])} forum items, "
        f"{len(data['dates'])} dates across {len(data['courses'])} courses."
    )
    if errors:
        base += f" ({len(errors)} endpoint(s) unavailable — see report.)"
    return base


def main() -> None:
    ap = argparse.ArgumentParser(description="Weekly StudIP monitor")
    ap.add_argument("--since", help="ISO date/time window start (overrides stored state)")
    ap.add_argument("--no-state", action="store_true", help="do not update state.json after the run")
    args = ap.parse_args()

    base = common.env("STUDIP_URL", "https://studip.uni-giessen.de").rstrip("/")
    api_path = common.env("STUDIP_API_PATH", "/api.php")
    lookback = int(common.env("MONITOR_LOOKBACK_DAYS", "7"))

    headers = auth_headers()  # validates credentials before any work
    started = common.now()
    since = common.resolve_since(MONITOR, args.since, lookback)
    since_ts = int(since.timestamp())
    print(f"Fetching StudIP activity since {since.isoformat()} …")

    client = StudIP(base, api_path, headers)
    data = gather(client, since_ts)
    report = render(data, client.errors, since)
    path = common.write_report(MONITOR, report)

    if not args.no_state:
        common.save_state(MONITOR, started)

    print(f"Report written → {path}")
    print(summarize(data, client.errors))


if __name__ == "__main__":
    main()
