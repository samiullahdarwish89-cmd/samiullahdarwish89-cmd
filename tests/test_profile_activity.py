"""Offline regression checks for public-only analytics and truthful chart output."""

from copy import deepcopy
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import update_profile_activity as activity

SVG = "{http://www.w3.org/2000/svg}"
NOW = datetime(2026, 1, 3, 12, tzinfo=timezone.utc)


def repository(name="profile", **changes):
    value = {
        "name": name, "private": False, "visibility": "public",
        "owner": {"login": activity.LOGIN}, "fork": False, "stargazers_count": 2,
    }
    value.update(changes)
    return value


def fixture():
    """Five real contributions across three days, including a zero day."""
    collection = {
        "restrictedContributionsCount": 0,
        "totalCommitContributions": 3,
        "totalIssueContributions": 0,
        "totalPullRequestContributions": 0,
        "totalPullRequestReviewContributions": 0,
        "totalRepositoryContributions": 1,
        "joinedGitHubContribution": {"isRestricted": False},
        "commitContributionsByRepository": [
            {"repository": {"visibility": "PUBLIC"}, "contributions": {"totalCount": 3}},
        ],
        "issueContributionsByRepository": [],
        "pullRequestContributionsByRepository": [],
        "pullRequestReviewContributionsByRepository": [],
        "repositoryContributions": {
            "totalCount": 1, "pageInfo": {"hasNextPage": False},
            "nodes": [{"isRestricted": False, "repository": {"visibility": "PUBLIC"}}],
        },
        "contributionCalendar": {
            "totalContributions": 5,
            "weeks": [{"firstDay": "2026-01-01", "contributionDays": [
                {"date": "2026-01-01", "contributionCount": 1},
                {"date": "2026-01-02", "contributionCount": 0},
                {"date": "2026-01-03", "contributionCount": 4},
            ]}],
        },
    }
    profile = {"login": activity.LOGIN, "public_repos": 1, "followers": 2}
    graphql = {"data": {"user": {"login": activity.LOGIN, "contributionsCollection": collection}}}
    repos = {
        "public_repositories": 1, "public_stars": 2, "language_repository_count": 1,
        "languages": [{"name": "Python", "bytes": 300, "repository_count": 1}],
    }
    return profile, graphql, repos


class PublicRepositoryTests(unittest.TestCase):
    def test_private_repository_is_refused_before_any_language_request(self):
        for change in ({"private": True}, {"visibility": "private"}, {"visibility": "internal"}):
            with self.subTest(change=change), patch.object(
                activity, "github_api", return_value=[repository(**change)]
            ) as api:
                with self.assertRaises(ValueError):
                    activity.public_repository_stats()
                self.assertEqual(api.call_count, 1)

    def test_foreign_owner_is_refused_before_any_language_request(self):
        with patch.object(activity, "github_api", return_value=[
            repository(owner={"login": "somebody-else"})
        ]) as api:
            with self.assertRaises(ValueError):
                activity.public_repository_stats()
            self.assertEqual(api.call_count, 1)

    def test_forks_count_as_public_repositories_but_never_supply_language_bytes(self):
        with patch.object(activity, "github_api", side_effect=[
            [repository(), repository("forked", fork=True, stargazers_count=0)],
            {"Python": 300, "CSS": 100},
        ]) as api:
            stats = activity.public_repository_stats()
        self.assertEqual(stats["public_repositories"], 2)
        self.assertEqual(stats["public_stars"], 2)
        self.assertEqual(stats["language_repository_count"], 1)
        self.assertEqual(stats["languages"], [
            {"name": "Python", "bytes": 300, "repository_count": 1},
            {"name": "CSS", "bytes": 100, "repository_count": 1},
        ])
        self.assertEqual(api.call_count, 2)
        self.assertTrue(api.call_args_list[1].args[0].endswith("/profile/languages"))

    def test_repository_pagination_does_not_silently_stop_at_100(self):
        pages = [[repository(f"repo-{n}", stargazers_count=0) for n in range(100)],
                 [repository("repo-100", stargazers_count=0)]]

        def respond(path):
            if "/repos?" in path:
                return pages[1 if path.endswith("page=2") else 0]
            return {"Python": 10}

        with patch.object(activity, "github_api", side_effect=respond) as api:
            stats = activity.public_repository_stats()
        self.assertEqual(stats["public_repositories"], 101)
        self.assertEqual(stats["languages"], [
            {"name": "Python", "bytes": 1010, "repository_count": 101},
        ])
        self.assertEqual(api.call_count, 103)


class PublicContributionTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.graphql, self.repos = fixture()
        self.collection = self.graphql["data"]["user"]["contributionsCollection"]

    def snapshot(self):
        return activity.prepare_snapshot(self.profile, self.graphql, NOW, self.repos)

    def test_real_counts_categories_and_zero_days_survive_without_inflation(self):
        snapshot = self.snapshot()
        self.assertEqual(snapshot["metrics"], {
            "public_repositories": 1, "public_contributions": 5, "public_stars": 2,
            "followers": 2, "active_days": 2,
        })
        self.assertEqual(snapshot["contribution_types"], {
            "commits": 3, "issues": 0, "pull_requests": 0,
            "reviews": 0, "repositories": 1, "joined": 1,
        })
        self.assertEqual(sum(day["contributions"] for day in snapshot["daily"]), 5)
        self.assertEqual(snapshot["daily"][1]["contributions"], 0)
        self.assertEqual(snapshot["weeks"], [{"week_start": "2026-01-01", "contributions": 5}])
        self.assertTrue(snapshot["public_only"])

    def test_accessible_private_or_internal_contribution_groups_are_refused(self):
        for visibility in ("PRIVATE", "INTERNAL"):
            for field in ("commitContributionsByRepository", "issueContributionsByRepository",
                          "pullRequestContributionsByRepository", "pullRequestReviewContributionsByRepository"):
                collection = deepcopy(self.collection)
                collection[field] = [{"repository": {"visibility": visibility},
                                      "contributions": {"totalCount": 1}}]
                with self.subTest(visibility=visibility, field=field), self.assertRaises(ValueError):
                    activity.public_contribution_types(collection, 5)

    def test_restricted_counts_and_created_private_repositories_are_refused(self):
        self.collection["restrictedContributionsCount"] = 1
        with self.assertRaises(ValueError):
            self.snapshot()
        self.collection["restrictedContributionsCount"] = 0
        self.collection["repositoryContributions"]["nodes"][0]["repository"]["visibility"] = "PRIVATE"
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_incomplete_repository_coverage_is_refused(self):
        self.collection["commitContributionsByRepository"][0]["contributions"]["totalCount"] = 2
        with self.assertRaises(ValueError):
            self.snapshot()
        self.collection["commitContributionsByRepository"][0]["contributions"]["totalCount"] = 3
        self.collection["repositoryContributions"]["pageInfo"]["hasNextPage"] = True
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_category_and_calendar_mismatch_is_refused(self):
        self.collection["contributionCalendar"]["totalContributions"] = 6
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_missing_and_duplicate_calendar_days_are_refused_even_if_totals_match(self):
        days = self.collection["contributionCalendar"]["weeks"][0]["contributionDays"]
        zero_day = days.pop(1)
        with self.assertRaises(ValueError):
            self.snapshot()
        days.insert(1, zero_day)
        days.insert(2, deepcopy(zero_day))
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_negative_and_boolean_counts_are_not_valid_statistics(self):
        for value in (-1, True):
            self.profile["followers"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.snapshot()


class RenderingAndFailureTests(unittest.TestCase):
    def test_zero_one_and_multiple_languages_produce_valid_script_free_svg(self):
        profile, graphql, repos = fixture()
        snapshot = activity.prepare_snapshot(profile, graphql, NOW, repos)
        for languages in ([], [{"name": "Python", "bytes": 300, "repository_count": 1}], [
            {"name": "Python", "bytes": 300, "repository_count": 1},
            {"name": "C++", "bytes": 100, "repository_count": 1},
        ]):
            snapshot["languages"] = languages
            for render in (activity.activity_svg, activity.activity_svg_mobile):
                with self.subTest(languages=len(languages), renderer=render.__name__):
                    document = ElementTree.fromstring(render(snapshot))
                    self.assertEqual(document.tag, SVG + "svg")
                    self.assertFalse(document.findall(".//" + SVG + "script"))
                    self.assertTrue(document.find(SVG + "desc").text)
                    self.assertNotIn("NaN", ElementTree.tostring(document, encoding="unicode"))
                    circles = [node.find(SVG + "title").text
                               for node in document.findall(".//" + SVG + "circle")
                               if node.find(SVG + "title") is not None]
                    if languages:
                        self.assertIn("Python: 300", circles)
                    self.assertIn("Account joined: 1", circles)

    def test_zero_activity_does_not_acquire_decorative_positive_bars(self):
        profile, graphql, repos = fixture()
        snapshot = activity.prepare_snapshot(profile, graphql, NOW, repos)
        snapshot["metrics"].update(public_contributions=0, active_days=0)
        snapshot["contribution_types"] = dict.fromkeys(snapshot["contribution_types"], 0)
        for day in snapshot["daily"]:
            day["contributions"] = 0
        for week in snapshot["weeks"]:
            week["contributions"] = 0
        for render in (activity.activity_svg, activity.activity_svg_mobile):
            document = ElementTree.fromstring(render(snapshot))
            bars = [node for node in document.findall(".//" + SVG + "rect")
                    if node.attrib.get("fill") == "url(#bar)"]
            self.assertTrue(bars)
            self.assertTrue(all(float(node.attrib["height"]) == 0 for node in bars))

    def test_failed_api_request_preserves_all_published_snapshot_files(self):
        names = ("github-analytics.svg", "github-analytics-mobile.svg", "github-public-data.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            for name in names:
                (assets / name).write_bytes(b"existing verified snapshot")
            with patch.object(activity, "ROOT", root), patch.object(
                activity, "github_api", side_effect=ValueError("Unavailable")
            ), patch.object(activity, "write_assets") as write, patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(activity.main(), 1)
            write.assert_not_called()
            for name in names:
                self.assertEqual((assets / name).read_bytes(), b"existing verified snapshot")


if __name__ == "__main__":
    unittest.main()
