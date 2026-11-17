# Public GitHub analytics

`assets/github-analytics.svg` and `assets/github-analytics-mobile.svg` are desktop and mobile views of the same real public data. The charts show weekly contributions, language shares, contributions by weekday, public profile totals and contribution types. They are dated snapshots, not a proficiency score or a claim about years of experience.

## What the charts measure

- Contributions, active days, weekday totals and weekly bars cover **January 1 through the snapshot timestamp**, in UTC. They use GitHub's contribution calendar; zero activity remains zero. Weekday bars include all contribution types, not just commits, and do not claim to show working hours.
- Contribution types show GitHub's counts for commits, issues, pull requests, reviews and repository creation. An account-joined contribution is included only when GitHub returns it within the period. These categories must reconcile exactly with the calendar total before publishing.
- Language percentages are the share of **code bytes in owned public non-fork repositories**, as detected by GitHub. They are not skill ratings, a count of all languages known, or a view of private projects. Documentation and media may have no detected code language. More than five languages are grouped into the four largest plus Other in the graphic; source data retains every language.
- Public repositories, stars received on owned public repositories and followers are current snapshot totals. Active days count dates with at least one public contribution in the stated period.

The source of every number is recorded in `assets/github-public-data.json`, including the fetch timestamp and exact period. No repository contents, private repository names, commit messages, customer information, credentials or tokens are stored in that file. The illustrations elsewhere in this profile are decorative artwork.

Sources: [GitHub contribution schema](https://docs.github.com/en/graphql/reference/users#contributionscollection), [public user API](https://docs.github.com/en/rest/users/users#get-a-user), [public repository list](https://docs.github.com/en/rest/repos/repos#list-repositories-for-a-user), [language byte counts](https://docs.github.com/en/rest/repos/repos#list-repository-languages).

## Refresh locally

Use the existing GitHub CLI sign-in, then run:

```sh
python3 tools/update_profile_activity.py
```

The updater uses `gh api`; it does not create credentials or request extra account permissions. Rendering lives in `tools/profile_analytics_svg.py`. No outside statistics, visitor-counter or trophy service is required to render these local SVG images.

All requests and validation must succeed before any existing asset is replaced. The updater checks public repository ownership and visibility before requesting language counts. It refuses restricted contributions and any non-public repository in the contribution groups, even if a future local token could read that repository. Per-type grouped counts must match the summary totals. Repository creations must be fully returned, public and unrestricted. The full daily calendar must be ordered, complete and match the weekly and category totals.

Contribution groups currently support up to 100 repositories per type and 100 created repositories per period. Incomplete coverage, an unsupported contribution category, a changed repository count during collection, API failures or invalid data stop the update and preserve previous assets. This is intentional: no partial or guessed statistics are published. Each prepared output file is replaced atomically after all data and SVG validation succeeds.

Run the focused validation checks with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

## Scheduled refresh

The existing workflow runs daily at **03:17 UTC**, or manually from Actions → **Refresh public profile activity** → **Run workflow**. It runs only on the profile repository's default branch. Scheduled runs can be delayed; the image always shows the actual snapshot date. [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

The workflow uses GitHub's repository-bounded `GITHUB_TOKEN`, without a personal access token or additional account scopes. The refresh job has contents write permission only to commit the three generated assets. It stages those exact files, commits as the GitHub Actions bot only when they change, and has no push trigger. The README and renderer are not rewritten by the scheduled job. [Automatic token authentication](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication)

If Actions cannot write due to repository policy or branch protection, the job fails without changing those protections. The existing snapshot and its visible date remain available. GitHub's own outer page, native contribution calendar and achievements remain controlled by GitHub.
