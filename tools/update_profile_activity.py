#!/usr/bin/env python3
"""Build a dated profile image from GitHub's real public activity data only."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from profile_analytics_svg import activity_svg, activity_svg_mobile

LOGIN = "samiullahdarwish89-cmd"
ROOT = Path(__file__).resolve().parent.parent
QUERY = """
query PublicProfileActivity($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    contributionsCollection(from: $from, to: $to) {
      restrictedContributionsCount
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalRepositoryContributions
      joinedGitHubContribution { isRestricted }
      commitContributionsByRepository(maxRepositories: 100) {
        repository { visibility }
        contributions { totalCount }
      }
      issueContributionsByRepository(maxRepositories: 100) {
        repository { visibility }
        contributions { totalCount }
      }
      pullRequestContributionsByRepository(maxRepositories: 100) {
        repository { visibility }
        contributions { totalCount }
      }
      pullRequestReviewContributionsByRepository(maxRepositories: 100) {
        repository { visibility }
        contributions { totalCount }
      }
      repositoryContributions(first: 100) {
        totalCount
        pageInfo { hasNextPage }
        nodes { isRestricted repository { visibility } }
      }
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


def github_api(path: str, fields: dict[str, str] | None = None) -> dict | list:
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
    if not isinstance(response, (dict, list)) or (isinstance(response, dict) and response.get("errors")):
        raise ValueError("GitHub returned an API error; previous assets were preserved.")
    return response


def count(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid count for {field}; previous assets were preserved.")
    return value


def public_repository_stats() -> dict:
    """Read only public owned repositories; never serialize repository identities."""
    repositories, seen = [], set()
    for page in range(1, 101):
        batch = github_api(f"users/{LOGIN}/repos?type=owner&sort=full_name&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Invalid public repository response.")
        for repo in batch:
            name = repo.get("name", "")
            if (repo.get("private") is not False or repo.get("visibility") != "public"
                    or repo.get("owner", {}).get("login", "").lower() != LOGIN.lower()
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in seen
                    or type(repo.get("fork")) is not bool):
                raise ValueError("Public repository validation failed; no assets were changed.")
            seen.add(name)
            repositories.append(repo)
        if len(batch) < 100:
            break
    else:
        raise ValueError("Public repository pagination exceeded the safe limit.")
    languages, language_repository_count = {}, 0
    for repo in repositories:
        if repo["fork"]:
            continue
        detected = github_api(f"repos/{LOGIN}/{repo['name']}/languages")
        if not isinstance(detected, dict):
            raise ValueError("Invalid public repository language response.")
        detected_any = False
        for name, byte_value in detected.items():
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise ValueError("Invalid language name.")
            byte_count = count(byte_value, "language bytes")
            if byte_count:
                detected_any = True
                totals = languages.setdefault(name, {"name": name, "bytes": 0, "repository_count": 0})
                totals["bytes"] += byte_count
                totals["repository_count"] += 1
        language_repository_count += detected_any
    return {
        "public_repositories": len(repositories),
        "public_stars": sum(count(repo.get("stargazers_count"), "public stars") for repo in repositories),
        "languages": sorted(languages.values(), key=lambda item: (-item["bytes"], item["name"])),
        "language_repository_count": language_repository_count,
    }


def public_contribution_types(collection: dict, calendar_total: int) -> dict:
    """Refuse accessible private contributions as well as restricted counts."""
    types = {}
    for key, total_field, group_field in [
        ("commits", "totalCommitContributions", "commitContributionsByRepository"),
        ("issues", "totalIssueContributions", "issueContributionsByRepository"),
        ("pull_requests", "totalPullRequestContributions", "pullRequestContributionsByRepository"),
        ("reviews", "totalPullRequestReviewContributions", "pullRequestReviewContributionsByRepository"),
    ]:
        total = count(collection[total_field], key)
        groups = collection[group_field]
        if not isinstance(groups, list) or any(group["repository"]["visibility"] != "PUBLIC" for group in groups):
            raise ValueError("Non-public contribution data was refused.")
        if sum(count(group["contributions"]["totalCount"], key) for group in groups) != total:
            raise ValueError("Contribution repository coverage is incomplete; previous assets were preserved.")
        types[key] = total
    repositories = collection["repositoryContributions"]
    repo_total = count(collection["totalRepositoryContributions"], "created repositories")
    if (repositories["pageInfo"]["hasNextPage"] is not False
            or count(repositories["totalCount"], "repository contributions") != repo_total
            or len(repositories["nodes"]) != repo_total
            or any(node["isRestricted"] is not False or node["repository"]["visibility"] != "PUBLIC"
                   for node in repositories["nodes"])):
        raise ValueError("Non-public or incomplete repository contributions were refused.")
    types["repositories"] = repo_total
    joined = collection["joinedGitHubContribution"]
    if joined is not None and joined["isRestricted"] is not False:
        raise ValueError("Restricted account contribution was refused.")
    types["joined"] = int(joined is not None)
    if sum(types.values()) != calendar_total:
        raise ValueError("Contribution categories do not match the calendar; previous assets were preserved.")
    return types


def prepare_snapshot(profile: dict, graphql: dict, now: datetime, repository_stats: dict) -> dict:
    started_at = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    if profile.get("login", "").lower() != LOGIN.lower():
        raise ValueError("Unexpected profile identity; previous assets were preserved.")
    public_repos = count(profile.get("public_repos"), "public repositories")
    if public_repos != repository_stats["public_repositories"]:
        raise ValueError("Public repository counts changed during the fetch; retry the update.")
    user = graphql["data"]["user"]
    if not user or user.get("login", "").lower() != LOGIN.lower():
        raise ValueError("Unexpected contribution identity; previous assets were preserved.")
    collection = user["contributionsCollection"]
    restricted = count(collection["restrictedContributionsCount"], "restricted contributions")
    if restricted:
        raise ValueError("Restricted contributions were present; no activity assets were changed.")
    calendar = collection["contributionCalendar"]
    total = count(calendar["totalContributions"], "public contributions")
    contribution_types = public_contribution_types(collection, total)
    weeks = []
    daily = []
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
                daily.append({"date": day_date.isoformat(), "contributions": day_total})
            elif day_total:
                raise ValueError("Contributions outside the requested period; previous assets were preserved.")
        if included:
            weeks.append({"week_start": week_start.isoformat(), "contributions": week_total})
    if not weeks or sum(week["contributions"] for week in weeks) != total:
        raise ValueError("Weekly contributions do not match the calendar total; previous assets were preserved.")
    if weeks != sorted(weeks, key=lambda week: week["week_start"]):
        raise ValueError("Unexpected calendar ordering; previous assets were preserved.")
    expected_days = [(first_date + timedelta(days=offset)).isoformat()
                     for offset in range((last_date - first_date).days + 1)]
    if [day["date"] for day in daily] != expected_days:
        raise ValueError("Contribution calendar has missing or unordered dates.")
    timestamp = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "schema_version": 2,
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
            {"path": f"/users/{LOGIN}", "fields": ["public_repos", "followers"]},
            {"path": f"/users/{LOGIN}/repos", "fields": ["private", "visibility", "owner.login", "fork", "stargazers_count"]},
            {"path": "/repos/{verified_public_owner}/{verified_public_repo}/languages", "fields": ["language code byte counts"]},
            {"path": "/graphql", "fields": ["user.contributionsCollection.contributionCalendar", "user.contributionsCollection public-validated contribution categories"]},
        ],
        "metrics": {
            "public_repositories": public_repos,
            "public_contributions": total,
            "public_stars": count(repository_stats["public_stars"], "public stars"),
            "followers": count(profile.get("followers"), "followers"),
            "active_days": sum(day["contributions"] > 0 for day in daily),
        },
        "restricted_contributions": restricted,
        "languages": repository_stats["languages"],
        "language_repository_count": repository_stats["language_repository_count"],
        "contribution_types": contribution_types,
        "daily": daily,
        "weeks": weeks,
    }


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
        for name, text in [("github-analytics.svg", svg), ("github-analytics-mobile.svg", mobile_svg), ("github-public-data.json", data)]:
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
        repository_stats = public_repository_stats()
        snapshot = prepare_snapshot(profile, graphql, now, repository_stats)
        write_assets(snapshot)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"Profile activity update stopped: {exc}", file=sys.stderr)
        return 1
    print("Updated the three public GitHub activity snapshot assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
