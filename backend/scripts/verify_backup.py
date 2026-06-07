"""Verify the most recent backup commit in the backup repo.

Run by .github/workflows/backup.yml after the backup step. Reads
BACKUP_GITHUB_REPO and BACKUP_GITHUB_TOKEN from the environment, hits
the GitHub commits API, and prints a short summary. Exits with code 1
if the latest commit is more than 60 minutes old, so the workflow
surfaces a quiet failure (e.g. expired token, neon outage, script
crash) instead of just going green.
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    repo = os.environ.get("BACKUP_GITHUB_REPO", "")
    token = os.environ.get("BACKUP_GITHUB_TOKEN", "")
    if not repo or not token:
        print("::error::BACKUP_GITHUB_REPO / BACKUP_GITHUB_TOKEN unset")
        return 1
    url = f"https://api.github.com/repos/{repo}/commits?per_page=3"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            commits = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"::error::GitHub API returned {e.code}: {e.reason}")
        return 1
    except urllib.error.URLError as e:
        print(f"::error::Could not reach GitHub: {e.reason}")
        return 1
    if not commits:
        print("::error::No commits found in backup repo")
        return 1
    latest = commits[0]
    ts = datetime.datetime.fromisoformat(
        latest["commit"]["author"]["date"].replace("Z", "+00:00")
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    age_min = (now - ts).total_seconds() / 60
    short_sha = latest["sha"][:8]
    msg = latest["commit"]["message"].splitlines()[0]
    print(f"Latest backup commit: {short_sha} ({age_min:.1f} min ago)")
    print(f"Message: {msg}")
    if age_min > 60:
        print(
            f"::warning::Latest backup is {age_min:.0f} min old — "
            f"workflow may have failed silently."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
