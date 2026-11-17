# Public profile activity snapshot

`assets/github-activity.svg` and the responsive `assets/github-activity-mobile.svg` are generated from real GitHub public data. They show the account’s public repository count, current UTC year-to-date public contribution count, and actual weekly contribution totals. They are dated snapshots, not a proficiency score or a claim about programming experience.

`assets/github-public-data.json` records the UTC fetch timestamp, exact period, source API paths, public metrics, and weekly totals used to draw the image. The public snapshot never includes repository contents, private repository names, customer information, credentials, or tokens. The other illustrations in this profile are decorative artwork; they are not evidence of a customer, employer, or project.

## Refresh locally

Use an existing GitHub CLI sign-in that can read public profile data, then run:

```sh
python3 tools/update_profile_activity.py
```

The script uses `gh api`; it does not create credentials or request extra account permissions. The intended token has repository access without the optional `read:user`/`user` access that enables private contribution data. Do not run this public-data generator with added private-user access. GitHub’s GraphQL documentation states that private and internal contributions require the optional `read:user` scope. [GitHub contribution schema](https://docs.github.com/en/graphql/reference/users#contributionscollection)

Both API requests and all validation must succeed before any snapshot asset is replaced. The script refuses restricted contributions, invalid counts, duplicate calendar dates, and weekly totals that do not match GitHub’s calendar total. Each completed output is replaced atomically. A failed API request or validation preserves the existing snapshot. Zero activity remains zero; no sample bars or fabricated statistics are inserted.

## Scheduled refresh

`.github/workflows/profile-activity.yml` runs daily at **03:17 UTC**, or manually from Actions → **Refresh public profile activity** → **Run workflow**. It runs only on the default branch of `samiullahdarwish89-cmd/samiullahdarwish89-cmd`. Scheduled runs can be delayed by GitHub; the image always shows the actual snapshot date. [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

The workflow uses GitHub’s automatically provided repository-bounded `GITHUB_TOKEN` via `GH_TOKEN`. It does not need a personal access token or additional account scopes. Default permissions are read-only; only the refresh job receives repository contents write permission to commit the three generated assets. Its commit step stages only `assets/github-activity.svg`, `assets/github-activity-mobile.svg`, and `assets/github-public-data.json`, uses the GitHub Actions bot identity, and commits/pushes only if those files changed. There is no push trigger, so its own refresh commits cannot trigger a loop. [Automatic token authentication](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication)

If Actions cannot write because of repository policy or branch protection, the job fails without changing that policy. Review the failed run before retrying. If the image is stale, its timestamp remains visible.

## Presentation and data boundaries

The repository count comes from the public `GET /users/samiullahdarwish89-cmd` response’s `public_repos` field. Contributions come from that user’s GraphQL `contributionsCollection` for January 1 through the current UTC time. GitHub’s own contribution rules apply; this count is not a count of every programming action or every commit on disk. [Public user API](https://docs.github.com/en/rest/users/users#get-a-user)

Keep real language names in the README or descriptive alternative text. No external statistics service, visitor counter, or trophy service is required to render the local assets. The profile’s outer page, native contribution calendar, and achievements remain controlled by GitHub.
