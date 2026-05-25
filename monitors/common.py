#!/usr/bin/env python3
"""Shared helpers for the weekly monitors (GitLab ADA, StudIP).

Stdlib only — no third-party dependencies, so the scripts run anywhere a
plain Python 3.10+ interpreter is available.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# JLU / PwC live in Central European Time. CEST (+2) in summer, CET (+1) in winter.
# Timestamps are only used for human-readable report headers and "since" windows,
# so a fixed +2 offset is close enough and avoids a tzdata dependency.
TZ = timezone(timedelta(hours=2))

MONITORS_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(MONITORS_DIR, "reports")
STATE_PATH = os.path.join(MONITORS_DIR, "state.json")


def now() -> datetime:
    return datetime.now(TZ)


def iso_date() -> str:
    return now().strftime("%Y-%m-%d")


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"Missing required environment variable: {name}")
    return val


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string into an aware datetime (assumes local TZ if naive)."""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


# ── Run-state (committed alongside reports so weekly deltas survive fresh clones) ──

def load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(monitor: str, last_run: datetime) -> None:
    state = load_state()
    state[monitor] = {"last_run": last_run.isoformat()}
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def resolve_since(monitor: str, cli_since: str | None, lookback_days: int) -> datetime:
    """Window start: explicit --since > last committed run > now minus lookback."""
    if cli_since:
        return parse_iso(cli_since)
    last = load_state().get(monitor, {}).get("last_run")
    if last:
        return parse_iso(last)
    return now() - timedelta(days=lookback_days)


# ── HTTP ──────────────────────────────────────────────────────────────────────

class HttpError(Exception):
    pass


def basic_auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _request(url: str, headers: dict | None, timeout: int):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            resp_headers = dict(resp.headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise HttpError(f"HTTP {exc.code} for {url}: {detail}")
    except urllib.error.URLError as exc:
        raise HttpError(f"Network error for {url}: {exc.reason}")
    return (json.loads(raw) if raw else None), resp_headers


def http_get(url: str, headers: dict | None = None, timeout: int = 30):
    """GET a URL, returning (parsed_json, response_headers). Exits on HTTP error."""
    try:
        return _request(url, headers, timeout)
    except HttpError as exc:
        sys.exit(str(exc))


def http_try_get(url: str, headers: dict | None = None, timeout: int = 30):
    """Non-fatal GET: returns (parsed_json, response_headers, error_or_None)."""
    try:
        data, resp_headers = _request(url, headers, timeout)
        return data, resp_headers, None
    except HttpError as exc:
        return None, {}, str(exc)


# ── Report output ───────────────────────────────────────────────────────────────

def write_report(monitor: str, markdown: str) -> str:
    out_dir = os.path.join(REPORTS_DIR, monitor)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{iso_date()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path
