#!/usr/bin/env python3
"""Self-hosted GitHub profile stat cards.

Fetches your public GitHub stats over GraphQL and renders two SVG cards
(stats + contribution sparkline, top languages) that a scheduled GitHub
Action commits back to this repo. Embed the raw SVG URLs in your profile
README and you never depend on a third-party card service again.

Zero dependencies — Python 3.9+ standard library only.

Env:
  GITHUB_TOKEN  required. In Actions the built-in token is enough.
  GH_LOGIN      optional. Defaults to the owner of GITHUB_REPOSITORY,
                so a fork automatically shows the fork owner's stats.
"""
import datetime
import json
import os
import urllib.request
from html import escape

API = "https://api.github.com/graphql"

# ---- theme (tokyonight, matching the profile) ------------------------------
BG = "#1a1b26"
BORDER = "#2f3549"
TEXT = "#c0caf5"
DIM = "#565f89"
ACCENT = "#7aa2f7"
GREEN = "#9ece6a"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC,
                 isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount } }
      }
    }
  }
}
"""


def fetch(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL errors: {data['errors']}")
    return data["data"]["user"]


def fmt(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


# ---- cards -----------------------------------------------------------------

def stats_card(user: dict) -> str:
    repos = user["repositories"]
    stars = sum(r["stargazerCount"] for r in repos["nodes"])
    contrib = user["contributionsCollection"]
    calendar = contrib["contributionCalendar"]

    weekly = [
        sum(d["contributionCount"] for d in w["contributionDays"])
        for w in calendar["weeks"]
    ][-52:]

    rows = [
        ("⭐", "Total stars", fmt(stars)),
        ("\U0001f5d3", "Contributions (year)", fmt(calendar["totalContributions"])),
        ("\U0001f4e6", "Public repos", fmt(repos["totalCount"])),
        ("\U0001f465", "Followers", fmt(user["followers"]["totalCount"])),
    ]

    # sparkline geometry
    x0, x1, y0, y1 = 268, 438, 60, 138
    peak = max(max(weekly), 1)
    pts = []
    for i, v in enumerate(weekly):
        x = x0 + (x1 - x0) * i / max(len(weekly) - 1, 1)
        y = y1 - (y1 - y0) * v / peak
        pts.append(f"{x:.1f},{y:.1f}")
    line = " ".join(pts)
    area = f"{x0},{y1} {line.replace(' ', ' ')} {x1},{y1}"

    row_svg = []
    for i, (icon, label, value) in enumerate(rows):
        y = 66 + i * 25
        row_svg.append(
            f'<text x="22" y="{y}" font-size="13" fill="{TEXT}">{icon} {label}</text>'
            f'<text x="248" y="{y}" font-size="13" font-weight="700" fill="{ACCENT}" text-anchor="end">{value}</text>'
        )

    today = datetime.date.today().isoformat()
    login = escape(user["login"])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="460" height="170" viewBox="0 0 460 170" role="img" aria-label="GitHub stats for {login}">
  <rect x="0.5" y="0.5" width="459" height="169" rx="10" fill="{BG}" stroke="{BORDER}"/>
  <text x="22" y="36" font-size="15" font-weight="700" fill="{ACCENT}" font-family="{FONT}">{login} &#183; GitHub stats</text>
  <g font-family="{FONT}">
    {''.join(row_svg)}
  </g>
  <polygon points="{area}" fill="{GREEN}" opacity="0.18"/>
  <polyline points="{line}" fill="none" stroke="{GREEN}" stroke-width="1.8" stroke-linejoin="round"/>
  <text x="353" y="154" font-size="9" fill="{DIM}" text-anchor="middle" font-family="{FONT}">contributions &#183; last 12 months</text>
  <text x="22" y="154" font-size="9" fill="{DIM}" font-family="{FONT}">updated {today}</text>
</svg>
"""


def langs_card(user: dict) -> str:
    totals: dict[str, int] = {}
    colors: dict[str, str] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or "#8b98b8"

    top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
    total = sum(totals.values()) or 1

    # stacked bar
    bar_x, bar_w = 22, 256
    x = bar_x
    segments = []
    for name, size in top:
        w = bar_w * size / total
        segments.append(f'<rect x="{x:.1f}" y="48" width="{max(w, 1):.1f}" height="10" fill="{colors[name]}"/>')
        x += w

    legend = []
    for i, (name, size) in enumerate(top):
        col, row = divmod(i, 3)
        lx, ly = 22 + col * 132, 84 + row * 24
        pct = 100 * size / total
        legend.append(
            f'<circle cx="{lx + 4}" cy="{ly - 4}" r="4" fill="{colors[name]}"/>'
            f'<text x="{lx + 14}" y="{ly}" font-size="11" fill="{TEXT}">{escape(name)} '
            f'<tspan fill="{DIM}">{pct:.1f}%</tspan></text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="170" viewBox="0 0 300 170" role="img" aria-label="Most used languages">
  <rect x="0.5" y="0.5" width="299" height="169" rx="10" fill="{BG}" stroke="{BORDER}"/>
  <text x="22" y="36" font-size="15" font-weight="700" fill="{ACCENT}" font-family="{FONT}">Top languages</text>
  <clipPath id="bar"><rect x="{bar_x}" y="48" width="{bar_w}" height="10" rx="5"/></clipPath>
  <g clip-path="url(#bar)">{''.join(segments)}</g>
  <g font-family="{FONT}">{''.join(legend)}</g>
</svg>
"""


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required (in Actions the built-in token works)")
    login = os.environ.get("GH_LOGIN") or os.environ.get("GITHUB_REPOSITORY", "/").split("/")[0]
    if not login:
        raise SystemExit("set GH_LOGIN (or run inside GitHub Actions)")

    user = fetch(login, token)
    out = os.path.dirname(os.path.abspath(__file__))
    for name, svg in (("stats.svg", stats_card(user)), ("langs.svg", langs_card(user))):
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
