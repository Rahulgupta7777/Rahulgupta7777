#!/usr/bin/env python3
"""
Auto-updates dark_mode.svg / light_mode.svg with live GitHub stats.
Runs daily via .github/workflows/update.yml -- inspired by Andrew6rant/Andrew6rant.

Updates: Uptime, Repos (+ Original count), Stars, Commits, Followers,
and Lines of Code (additions++ / deletions--), keeping every dotted
line perfectly right-aligned.
"""

import datetime
import os
import re
import time

import requests
from dateutil import relativedelta

USER = os.environ.get("USER_NAME", "Rahulgupta7777")
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json"}

# The moment the clock started: first GitHub commit (Dec 7, 2024).
# Swap this for your birthday if you want Uptime to show your age instead.
START = datetime.datetime(2024, 12, 7)

# Layout constants -- must match how the SVGs were generated.
TOTAL_WIDTH = 64   # the right column is justified to this many characters
LEFT_COL = 41      # width of the left half of the two-column stat rows
SVG_FILES = ("dark_mode.svg", "light_mode.svg")


# ---------------------------------------------------------------- helpers --

def fmt(n):
    return f"{n:,}"


def uptime():
    diff = relativedelta.relativedelta(datetime.datetime.today(), START)
    p = lambda n, w: f"{n} {w}" + ("" if n == 1 else "s")
    return f"{p(diff.years, 'year')}, {p(diff.months, 'month')}, {p(diff.days, 'day')}"


def dots_single(key, value):
    """Dot padding for a normal 'Key: .... value' row."""
    return " " + "." * max(2, TOTAL_WIDTH - len(key) - 3 - len(value)) + " "


def dots_pair_left(key, value):
    """Dot padding for the left half of a two-column stat row."""
    return " " + "." * max(2, LEFT_COL - len(key) - 3 - len(value)) + " "


def dots_pair_right(key, value):
    """Dot padding for the right half of a two-column stat row."""
    right = TOTAL_WIDTH - LEFT_COL - 3
    return " " + "." * max(2, right - len(key) - 3 - len(value)) + " "


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def set_tspan(svg, tspan_id, new_text):
    pattern = rf'(<tspan[^>]*id="{tspan_id}"[^>]*>)[^<]*(</tspan>)'
    new_svg, n = re.subn(pattern, lambda m: m.group(1) + esc(new_text) + m.group(2), svg)
    if n == 0:
        raise RuntimeError(f'tspan id="{tspan_id}" not found in SVG')
    return new_svg


# --------------------------------------------------------------- fetchers --

def gql(query, variables):
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def user_stats():
    """Returns (total_repos, original_repos, stars, followers, own_repo_names)."""
    total = original = stars = followers = 0
    names, cursor = [], None
    while True:
        d = gql(
            """
            query($login: String!, $cursor: String) {
              user(login: $login) {
                followers { totalCount }
                repositories(ownerAffiliations: OWNER, first: 100, after: $cursor) {
                  totalCount
                  pageInfo { hasNextPage endCursor }
                  nodes { name isFork stargazerCount }
                }
              }
            }
            """,
            {"login": USER, "cursor": cursor},
        )["user"]
        followers = d["followers"]["totalCount"]
        repos = d["repositories"]
        total = repos["totalCount"]
        for node in repos["nodes"]:
            stars += node["stargazerCount"]
            if not node["isFork"]:
                original += 1
                names.append(node["name"])
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]
    return total, original, stars, followers, names


def commit_count():
    """All-time commits authored by USER, as counted by GitHub search."""
    r = requests.get(
        f"https://api.github.com/search/commits?q=author:{USER}",
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["total_count"]


def loc(repo_names):
    """Lines added/deleted by USER across their own repos (default branches)."""
    added = deleted = 0
    for name in repo_names:
        url = f"https://api.github.com/repos/{USER}/{name}/stats/contributors"
        r = None
        for _ in range(6):
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 202:  # 202 = GitHub is still computing stats
                break
            time.sleep(3)
        if r is None or r.status_code != 200 or not r.text.strip():
            continue
        for contributor in r.json() or []:
            author = contributor.get("author") or {}
            if author.get("login", "").lower() == USER.lower():
                for week in contributor["weeks"]:
                    added += week["a"]
                    deleted += week["d"]
    return added, deleted


# ------------------------------------------------------------------- main --

def main():
    up = uptime()
    total, original, stars, followers, names = user_stats()
    commits = commit_count()
    added, deleted = loc(names)

    repo_val = f"{fmt(total)} (Original: {fmt(original)})"
    star_val = fmt(stars)
    commit_val = fmt(commits)
    follower_val = fmt(followers)
    loc_val = fmt(added - deleted)
    add_val = f"{fmt(added)}++"
    del_val = f"{fmt(deleted)}--"

    for path in SVG_FILES:
        with open(path, encoding="utf-8") as f:
            svg = f.read()
        svg = set_tspan(svg, "uptime_data", up)
        svg = set_tspan(svg, "uptime_dots", dots_single("Uptime", up))
        svg = set_tspan(svg, "repo_data", repo_val)
        svg = set_tspan(svg, "repo_dots", dots_pair_left("Repos", repo_val))
        svg = set_tspan(svg, "star_data", star_val)
        svg = set_tspan(svg, "star_dots", dots_pair_right("Stars", star_val))
        svg = set_tspan(svg, "commit_data", commit_val)
        svg = set_tspan(svg, "commit_dots", dots_pair_left("Commits", commit_val))
        svg = set_tspan(svg, "follower_data", follower_val)
        svg = set_tspan(svg, "follower_dots", dots_pair_right("Followers", follower_val))
        svg = set_tspan(svg, "loc_data", loc_val)
        svg = set_tspan(svg, "loc_add", add_val)
        svg = set_tspan(svg, "loc_del", del_val)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)

    print(f"Uptime:    {up}")
    print(f"Repos:     {repo_val} | Stars: {star_val}")
    print(f"Commits:   {commit_val} | Followers: {follower_val}")
    print(f"LOC:       {loc_val} ( {add_val}, {del_val} )")


if __name__ == "__main__":
    main()
