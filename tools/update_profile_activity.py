#!/usr/bin/env python3
"""Build a dated profile image from GitHub's real public activity data only."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

LOGIN = "samiullahdarwish89-cmd"
ROOT = Path(__file__).resolve().parent.parent
QUERY = """
query PublicProfileActivity($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    contributionsCollection(from: $from, to: $to) {
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def github_api(path: str, fields: dict[str, str] | None = None) -> dict:
    """Use gh's existing authentication; never obtain or print credentials."""
    command = ["gh", "api", path, "--method", "POST" if fields else "GET"]
    if fields:
        for name, value in fields.items():
            command.extend(["-f", f"{name}={value}"])
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"GitHub API request failed for {path}; previous assets were preserved.") from exc
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("GitHub returned invalid JSON; previous assets were preserved.") from exc
    if not isinstance(response, dict) or response.get("errors"):
        raise ValueError("GitHub returned an API error; previous assets were preserved.")
    return response


def count(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid count for {field}; previous assets were preserved.")
    return value


def prepare_snapshot(profile: dict, graphql: dict, now: datetime) -> dict:
    started_at = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    if profile.get("login", "").lower() != LOGIN.lower():
        raise ValueError("Unexpected profile identity; previous assets were preserved.")
    public_repos = count(profile.get("public_repos"), "public repositories")
    user = graphql["data"]["user"]
    if not user or user.get("login", "").lower() != LOGIN.lower():
        raise ValueError("Unexpected contribution identity; previous assets were preserved.")
    collection = user["contributionsCollection"]
    restricted = count(collection["restrictedContributionsCount"], "restricted contributions")
    if restricted:
        raise ValueError("Restricted contributions were present; no activity assets were changed.")
    calendar = collection["contributionCalendar"]
    total = count(calendar["totalContributions"], "public contributions")
    weeks = []
    seen = set()
    first_date, last_date = started_at.date(), now.date()
    for week in calendar["weeks"]:
        week_start = date.fromisoformat(week["firstDay"])
        week_total = 0
        included = False
        for day in week["contributionDays"]:
            day_date = date.fromisoformat(day["date"])
            day_total = count(day["contributionCount"], "daily contributions")
            if day_date in seen:
                raise ValueError("Duplicate calendar day; previous assets were preserved.")
            seen.add(day_date)
            if first_date <= day_date <= last_date:
                included = True
                week_total += day_total
            elif day_total:
                raise ValueError("Contributions outside the requested period; previous assets were preserved.")
        if included:
            weeks.append({"week_start": week_start.isoformat(), "contributions": week_total})
    if not weeks or sum(week["contributions"] for week in weeks) != total:
        raise ValueError("Weekly contributions do not match the calendar total; previous assets were preserved.")
    if weeks != sorted(weeks, key=lambda week: week["week_start"]):
        raise ValueError("Unexpected calendar ordering; previous assets were preserved.")
    timestamp = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "login": LOGIN,
        "public_only": True,
        "fetched_at": timestamp,
        "period": {
            "year": now.year,
            "from": started_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "to": timestamp,
            "timezone": "UTC",
        },
        "sources": [
            {"path": f"/users/{LOGIN}", "fields": ["public_repos"]},
            {"path": "/graphql", "fields": ["user.contributionsCollection.restrictedContributionsCount", "user.contributionsCollection.contributionCalendar.totalContributions", "user.contributionsCollection.contributionCalendar.weeks"]},
        ],
        "metrics": {"public_repositories": public_repos, "public_contributions": total},
        "restricted_contributions": restricted,
        "weeks": weeks,
    }


def activity_svg(snapshot: dict) -> str:
    year = snapshot["period"]["year"]
    updated = snapshot["fetched_at"][:10]
    total = snapshot["metrics"]["public_contributions"]
    repositories = snapshot["metrics"]["public_repositories"]
    weeks = snapshot["weeks"]
    maximum = max(1, max(week["contributions"] for week in weeks))
    cell = 920 / len(weeks)
    bar_width = max(1, cell - min(5, cell * .24))
    chart_bottom, chart_height = 284, 83
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="350" viewBox="0 0 1000 350" role="img" aria-labelledby="activity-title activity-desc">',
        '<title id="activity-title">Public GitHub activity</title>',
        f'<desc id="activity-desc">{escape(LOGIN)}: {repositories} public repositories and {total} public contributions from January 1, {year} through {updated} UTC. Bars show real weekly contribution totals. Snapshot updated {updated}.</desc>',
        '<defs><linearGradient id="card" x2="1" y2="1"><stop stop-color="#10182d"/><stop offset="1" stop-color="#15132e"/></linearGradient><linearGradient id="bar" x2="0" y2="1"><stop stop-color="#79e5e9"/><stop offset="1" stop-color="#967cf4"/></linearGradient></defs>',
        '<rect x="1" y="1" width="998" height="348" rx="22" fill="url(#card)" stroke="#8d9ecd" stroke-opacity=".25"/>',
        '<g font-family="Arial,Helvetica,sans-serif">',
        '<text x="40" y="38" font-size="11" letter-spacing="2" fill="#a8b9da">GITHUB / PUBLIC ACTIVITY</text>',
        f'<text x="960" y="38" text-anchor="end" font-size="11" fill="#98a8c8">Updated {escape(updated)} · UTC</text>',
        f'<text x="40" y="97" font-size="39" font-weight="600" fill="#f0f4ff">{repositories:,}</text>',
        '<text x="40" y="123" font-size="12" fill="#b7c5e1">Public repositories</text>',
        f'<text x="350" y="97" font-size="39" font-weight="600" fill="#bbaaff">{total:,}</text>',
        f'<text x="350" y="123" font-size="12" fill="#b7c5e1">Public contributions · {year}</text>',
        '<path d="M40 148H960" stroke="#8d9ecd" stroke-opacity=".18"/>',
        '<text x="40" y="177" font-size="12" fill="#d7e1f5">Weekly contributions</text>',
        f'<text x="960" y="177" text-anchor="end" font-size="10" fill="#91a2c4">Weekly maximum: {maximum if total else 0}</text>',
        f'<path d="M40 {chart_bottom}H960" stroke="#7d8cb4" stroke-opacity=".3"/>',
    ]
    for index, week in enumerate(weeks):
        value = week["contributions"]
        height = value / maximum * chart_height
        x = 40 + index * cell + (cell - bar_width) / 2
        y = chart_bottom - height
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{height:.2f}" rx="2" fill="url(#bar)"><title>Week of {escape(week["week_start"])}: {value} contributions</title></rect>')
    parts.extend([
        f'<text x="40" y="307" font-size="10" fill="#91a2c4">January 1, {year}</text>',
        f'<text x="960" y="307" text-anchor="end" font-size="10" fill="#91a2c4">{escape(updated)} UTC</text>',
        '<text x="40" y="331" font-size="10" fill="#7f91b6">Source: GitHub API · Public data only · A dated snapshot, not a proficiency score</text>',
        '</g></svg>\n',
    ])
    return "\n".join(parts)


def activity_svg_mobile(snapshot: dict) -> str:
    """Use the same real data with type large enough for a narrow profile."""
    year = snapshot["period"]["year"]
    updated = snapshot["fetched_at"][:10]
    total = snapshot["metrics"]["public_contributions"]
    repositories = snapshot["metrics"]["public_repositories"]
    weeks = snapshot["weeks"]
    maximum = max(1, max(week["contributions"] for week in weeks))
    cell = 528 / len(weeks)
    bar_width = max(1, cell - min(3, cell * .24))
    chart_bottom, chart_height = 405, 122
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="530" viewBox="0 0 600 530" role="img" aria-labelledby="activity-title activity-desc">',
        '<title id="activity-title">Public GitHub activity</title>',
        f'<desc id="activity-desc">{escape(LOGIN)}: {repositories} public repositories and {total} public contributions from January 1, {year} through {updated} UTC. Bars show actual weekly contribution totals. Snapshot updated {updated}.</desc>',
        '<defs><linearGradient id="card" x2="1" y2="1"><stop stop-color="#10182d"/><stop offset="1" stop-color="#15132e"/></linearGradient><linearGradient id="bar" x2="0" y2="1"><stop stop-color="#79e5e9"/><stop offset="1" stop-color="#967cf4"/></linearGradient></defs>',
        '<rect x="1" y="1" width="598" height="528" rx="22" fill="url(#card)" stroke="#8d9ecd" stroke-opacity=".25"/>',
        '<g font-family="Arial,Helvetica,sans-serif">',
        '<text x="36" y="46" font-size="27" font-weight="600" fill="#e5edff">Public GitHub activity</text>',
        f'<text x="36" y="78" font-size="19" fill="#98a8c8">Updated {escape(updated)} · UTC</text>',
        f'<text x="36" y="151" font-size="60" font-weight="600" fill="#f0f4ff">{repositories:,}</text>',
        '<text x="36" y="181" font-size="20" fill="#b7c5e1">Public repositories</text>',
        f'<text x="319" y="151" font-size="60" font-weight="600" fill="#bbaaff">{total:,}</text>',
        '<text x="319" y="181" font-size="20" fill="#b7c5e1">Public contributions</text>',
        f'<text x="319" y="207" font-size="18" fill="#91a2c4">Year to date · {year}</text>',
        '<path d="M36 232H564" stroke="#8d9ecd" stroke-opacity=".2"/>',
        '<text x="36" y="266" font-size="21" fill="#d7e1f5">Weekly contributions</text>',
        f'<path d="M36 {chart_bottom}H564" stroke="#7d8cb4" stroke-opacity=".3"/>',
    ]
    for index, week in enumerate(weeks):
        value = week["contributions"]
        height = value / maximum * chart_height
        x = 36 + index * cell + (cell - bar_width) / 2
        y = chart_bottom - height
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{height:.2f}" rx="2" fill="url(#bar)"><title>Week of {escape(week["week_start"])}: {value} contributions</title></rect>')
    parts.extend([
        f'<text x="36" y="436" font-size="18" fill="#91a2c4">Jan 1, {year}</text>',
        f'<text x="564" y="436" text-anchor="end" font-size="18" fill="#91a2c4">{escape(updated)} UTC</text>',
        '<text x="36" y="479" font-size="18" fill="#94a5c7">Source: GitHub API · Public data only</text>',
        '<text x="36" y="507" font-size="18" fill="#94a5c7">A dated snapshot, not a proficiency score</text>',
        '</g></svg>\n',
    ])
    return "\n".join(parts)


def write_assets(snapshot: dict) -> None:
    """Prepare all files first, then atomically replace each complete output."""
    assets = ROOT / "assets"
    svg = activity_svg(snapshot)
    mobile_svg = activity_svg_mobile(snapshot)
    # Validate the native SVG before touching any existing output.
    from xml.etree import ElementTree
    ElementTree.fromstring(svg)
    ElementTree.fromstring(mobile_svg)
    data = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    assets.mkdir(exist_ok=True)
    pending = []
    try:
        for name, text in [("github-activity.svg", svg), ("github-activity-mobile.svg", mobile_svg), ("github-public-data.json", data)]:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=assets, prefix=f".{name}.", delete=False) as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
                pending.append((Path(stream.name), assets / name))
        for temporary, destination in pending:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in pending:
            temporary.unlink(missing_ok=True)


def main() -> int:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    try:
        profile = github_api(f"users/{LOGIN}")
        graphql = github_api("graphql", {
            "query": QUERY,
            "login": LOGIN,
            "from": start.isoformat(timespec="seconds"),
            "to": now.isoformat(timespec="seconds"),
        })
        snapshot = prepare_snapshot(profile, graphql, now)
        write_assets(snapshot)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Profile activity update stopped: {exc}", file=sys.stderr)
        return 1
    print("Updated the three public GitHub activity snapshot assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
