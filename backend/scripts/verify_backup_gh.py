"""Verify a fresh backup file landed in the `backups/` folder of
the current GitHub repo.

Reads GITHUB_TOKEN and the GITHUB_REPOSITORY env var (set
automatically by GitHub Actions), hits the GitHub Contents API,
and prints a short summary. Exits non-zero if the newest file
in `backups/` is more than 60 minutes old, so a quiet failure
(expired token, neon outage, script crash) surfaces as a red
workflow run.

This is the workflow-side counterpart of verify_backup.py,
which talks to a *separate* backup repo. The single-repo design
(in-use since audit-9b) only needs this one.
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("BACKUP_REPO") or os.environ.get(
        "GITHUB_REPOSITORY", ""
    )
    if not token:
        print("::error::GITHUB_TOKEN is not set (workflow misconfig)")
        return 1
    if not repo:
        print("::error::BACKUP_REPO / GITHUB_REPOSITORY is not set")
        return 1
    # List the backups/ folder and sort by name. Filenames are
    # `backup-YYYYMMDD-HHMMSS.json` so lexicographic order matches
    # chronological order.
    url = f"https://api.github.com/repos/{repo}/contents/backups"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            entries = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"::error::GitHub API returned {e.code}: {e.reason}")
        return 1
    except urllib.error.URLError as e:
        print(f"::error::Could not reach GitHub: {e.reason}")
        return 1
    # entries can be a single dict (a file) or a list (a folder).
    if isinstance(entries, dict):
        entries = [entries]
    json_files = [e for e in entries if e.get("name", "").endswith(".json")]
    if not json_files:
        print("::error::No backup JSON files found in backups/ folder")
        return 1
    newest = sorted(json_files, key=lambda e: e["name"], reverse=True)[0]
    name = newest["name"]
    # Contents API doesn't return a committed date; use the path's
    # `git_url` to fetch the actual commit timestamp.
    git_url = newest.get("git_url", "")
    age_min = None
    if git_url:
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    git_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                ),
                timeout=15,
            ) as r:
                blob = json.loads(r.read().decode("utf-8"))
            ts = datetime.datetime.fromisoformat(
                blob["committer"]["date"].replace("Z", "+00:00")
            )
            age_min = (
                datetime.datetime.now(datetime.timezone.utc) - ts
            ).total_seconds() / 60
        except (urllib.error.URLError, KeyError, ValueError):
            pass
    if age_min is not None:
        print(f"Latest backup: {name} ({age_min:.1f} min ago)")
        if age_min > 60:
            print(
                f"::warning::Latest backup is {age_min:.0f} min old — "
                f"workflow may have failed silently."
            )
            return 1
    else:
        print(f"Latest backup: {name} (age unknown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
