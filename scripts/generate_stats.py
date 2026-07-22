import urllib.request
import re
import os
import sys
import json
from datetime import datetime, timedelta, timezone


def fetch_from_github_api(username, token=None):
    """Fetch all GitHub stats for a user using the GitHub REST API."""

    def make_headers(use_token=True):
        h = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/vnd.github.v3+json',
        }
        if use_token and token:
            prefix = "Bearer " if token.startswith("gh") else "token "
            h['Authorization'] = token if token.startswith(("Bearer ", "token ")) else f"token {token}"
        return h

    def get_json(url, use_token=True):
        """Fetch JSON from a URL; returns (data, response_headers)."""
        req = urllib.request.Request(url, headers=make_headers(use_token))
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data, resp.headers
        except urllib.error.HTTPError as e:
            if e.code == 401 and use_token and token:
                print(f"  401 with token, retrying without: {url}")
                return get_json(url, use_token=False)
            raise

    def parse_last_page_from_link(link_header):
        """
        Parse the last page number from a GitHub Link response header.
        Header example:
          <https://api.github.com/...?page=3&per_page=1>; rel="last"
        We need the page= value immediately before >; rel="last"
        """
        if not link_header:
            return None
        # Find all occurrences of page=N before >; rel="last"
        # The URL params can appear in any order, so we find the last-page URL
        # and then extract page= from that URL
        last_url_match = re.search(r'<([^>]+)>;\s*rel=["\']last["\']', link_header)
        if last_url_match:
            last_url = last_url_match.group(1)
            page_match = re.search(r'[?&]page=(\d+)', last_url)
            if page_match:
                return int(page_match.group(1))
        return None

    def count_commits_in_repo(owner, repo_name, author=None):
        """
        Count commits in a repo using the GitHub pagination Link header trick.
        Fetch only 1 commit per page; the 'last' page number = total commits.
        Optionally filter by author (email or login).
        """
        if author:
            url = f"https://api.github.com/repos/{owner}/{repo_name}/commits?author={author}&per_page=1"
        else:
            url = f"https://api.github.com/repos/{owner}/{repo_name}/commits?per_page=1"

        try:
            data, headers = get_json(url)
            link = headers.get('Link', '')
            last_page = parse_last_page_from_link(link)
            if last_page is not None:
                return last_page
            elif isinstance(data, list):
                return len(data)
            return 0
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Empty repository
                return 0
            if e.code == 403:
                print(f"  Rate-limited counting commits for {repo_name}, skipping.")
                return 0
            print(f"  Warning HTTP {e.code} for {owner}/{repo_name}: {e.reason}")
            return 0
        except Exception as e:
            print(f"  Warning: could not count commits for {owner}/{repo_name}: {e}")
            return 0

    # ── 1. User profile ───────────────────────────────────────────────────
    followers = 0
    try:
        print("Fetching user profile...")
        user_data, _ = get_json(f"https://api.github.com/users/{username}")
        followers = user_data.get("followers", 0)
    except Exception as e:
        print("Warning: Could not fetch user profile:", e)

    # ── 2. All repos (PUBLIC endpoint — always returns all public repos) ──
    # We intentionally use the public /users/{name}/repos endpoint so that
    # the response is NOT filtered by the token's repository scope.
    repos = []
    try:
        print("Fetching all public repositories...")
        page = 1
        while True:
            url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}&type=owner"
            page_data, _ = get_json(url)
            if not isinstance(page_data, list) or len(page_data) == 0:
                break
            repos.extend(page_data)
            if len(page_data) < 100:
                break
            page += 1
        print(f"Found {len(repos)} total repositories.")
    except Exception as e:
        print("Warning: Could not fetch repositories:", e)

    # ── 3. Stars — count from ALL repos (including forks) ───────────────────
    # GitHub profile shows stars on ALL your repos, including forks.
    total_stars = 0
    lang_bytes = {}
    own_repos = [r for r in repos if not r.get("fork")]
    print(f"Processing {len(repos)} total repositories ({len(own_repos)} own, {len(repos)-len(own_repos)} forks)...")

    for r in repos:
        # Stars: count from every repo (own + forks)
        total_stars += r.get("stargazers_count", 0)

        # Languages: only from own repos (more meaningful)
        if not r.get("fork"):
            lang_url = r.get("languages_url")
            if lang_url:
                try:
                    langs, _ = get_json(lang_url)
                    if isinstance(langs, dict):
                        for lang, val in langs.items():
                            lang_bytes[lang] = lang_bytes.get(lang, 0) + val
                except Exception as e:
                    print(f"  Warning: could not fetch languages for {r.get('name')}: {e}")

    print(f"Total stars (own + forks): {total_stars}")

    # ── 4. Commit counts — count from ALL repos (including forks) ────────────
    # User may have commits in forked repos (e.g. contributions to open-source).
    # We filter by author=username so we only count the user's own commits.
    print("Counting commits per repository (using pagination Link header)...")
    total_commits = 0
    for r in repos:
        repo_name = r.get("name", "")
        if not repo_name:
            continue
        count = count_commits_in_repo(username, repo_name, author=username)
        print(f"  {'[fork] ' if r.get('fork') else ''}{repo_name}: {count} commits")
        total_commits += count
    print(f"Total commits across all repos (own + forks): {total_commits}")

    # ── 5. PRs ────────────────────────────────────────────────────────────
    total_prs = 0
    try:
        print("Fetching PR count...")
        pr_data, _ = get_json(f"https://api.github.com/search/issues?q=author:{username}+type:pr")
        total_prs = pr_data.get("total_count", 0)
    except Exception as e:
        print("Warning: Could not fetch PRs:", e)

    # ── 6. Issues ─────────────────────────────────────────────────────────
    total_issues = 0
    try:
        print("Fetching issue count...")
        issue_data, _ = get_json(f"https://api.github.com/search/issues?q=author:{username}+type:issue")
        total_issues = issue_data.get("total_count", 0)
    except Exception as e:
        print("Warning: Could not fetch issues:", e)

    # ── 7. Contributed-to repos ───────────────────────────────────────────
    contributed_to = 0
    try:
        print("Fetching contributed-to count...")
        contrib_data, _ = get_json(
            f"https://api.github.com/search/issues?q=author:{username}+type:pr+-user:{username}"
        )
        contributed_repos = set()
        if contrib_data and "items" in contrib_data:
            for item in contrib_data["items"]:
                repo_url = item.get("repository_url")
                if repo_url:
                    contributed_repos.add(repo_url.split("/repos/")[-1])
        contributed_to = len(contributed_repos)
    except Exception as e:
        print("Warning: Could not fetch contributions:", e)

    # ── 8. Build language list ────────────────────────────────────────────
    color_map = {
        "JavaScript": "#f1e05a",
        "Python": "#3572A5",
        "HTML": "#e34c26",
        "TypeScript": "#3178c6",
        "CSS": "#663399",
        "Jupyter Notebook": "#DA5B0B",
        "Rust": "#dea584",
        "EJS": "#a91e50",
        "Java": "#b07219",
        "Dockerfile": "#384d54",
        "Batchfile": "#C1F12E",
        "C++": "#f34b7d",
        "C": "#555555",
        "C#": "#178600",
        "Go": "#00ADD8",
        "Ruby": "#701516",
        "PHP": "#4F5D95",
        "Shell": "#89e051",
        "Kotlin": "#A97BFF",
        "Swift": "#F05138",
        "SQL": "#e38c00",
    }
    total_bytes = sum(lang_bytes.values())
    langs_list = []
    if total_bytes > 0:
        sorted_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)
        for name, val in sorted_langs:
            pct = round((val / total_bytes) * 100, 2)
            langs_list.append({
                "name": name,
                "percentage": pct,
                "color": color_map.get(name, "#858585"),
            })
    langs_list = langs_list[:10]

    return {
        "stars": str(total_stars),
        "commits": str(total_commits),
        "prs": str(total_prs),
        "issues": str(total_issues),
        "contributions": str(contributed_to),
        "followers": followers,
        "languages": langs_list,
    }


def get_manual_commits():
    """Read an optional manual commits value from README.md (used only as fallback)."""
    try:
        readme_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md"
        )
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(
                r'<!--\s*(?:manual_commits|commits_override|commits):\s*([+-]?\d+)\s*-->',
                content
            )
            if match:
                return match.group(1)
    except Exception as e:
        print("Error reading manual commits:", e)
    return None


def get_manual_stars():
    """Read an optional manual_stars floor value from README.md."""
    try:
        readme_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md"
        )
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(
                r'<!--\s*(?:manual_stars|stars_floor|stars):\s*(\d+)\s*-->',
                content
            )
            if match:
                return match.group(1)
    except Exception as e:
        print("Error reading manual stars:", e)
    return None


def get_streaks(username):
    """Scrape GitHub contribution graph to calculate current/longest streaks."""
    contributions = {}
    current_year = datetime.now().year
    years = list(range(2023, current_year + 1))

    for year in years:
        url = f"https://github.com/users/{username}/contributions?from={year}-01-01&to={year}-12-31"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode("utf-8")

            day_tags = re.findall(
                r'<td\s+[^>]*class="[^"]*ContributionCalendar-day[^"]*"[^>]*>', html
            )
            id_to_date = {}
            for tag in day_tags:
                date_m = re.search(r'data-date="([^"]+)"', tag)
                id_m = re.search(r'id="([^"]+)"', tag)
                if date_m and id_m:
                    id_to_date[id_m.group(1)] = date_m.group(1)

            tooltips = re.findall(
                r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]+)</tool-tip>', html
            )
            for tid, text in tooltips:
                text = text.strip()
                if tid not in id_to_date:
                    continue
                date_str = id_to_date[tid]
                count = 0
                if "No contributions" not in text:
                    m = re.match(r"(\d+)\s+contribution", text)
                    if m:
                        count = int(m.group(1))
                contributions[date_str] = count
        except Exception as e:
            print(f"Error fetching contributions for {year}:", e)

    if not contributions:
        return {
            "current_streak": 0,
            "current_range": "No active streak",
            "longest_streak": 0,
            "longest_range": "No streak recorded",
        }

    sorted_dates = sorted(contributions.keys())

    # Longest streak
    longest_streak = 0
    longest_start = None
    longest_end = None
    temp_streak = 0
    temp_start = None
    for d in sorted_dates:
        if contributions[d] > 0:
            if temp_streak == 0:
                temp_start = d
            temp_streak += 1
            if temp_streak > longest_streak:
                longest_streak = temp_streak
                longest_start = temp_start
                longest_end = d
        else:
            temp_streak = 0

    # Current streak (Kolkata timezone UTC+5:30)
    kolkata_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    today_str = kolkata_now.strftime("%Y-%m-%d")
    current_streak = 0
    current_start = None
    current_end = None

    active = [d for d in sorted_dates if contributions.get(d, 0) > 0]
    if active:
        last_active = active[-1]
        last_dt = datetime.strptime(last_active, "%Y-%m-%d").date()
        today_dt = datetime.strptime(today_str, "%Y-%m-%d").date()
        if today_dt - last_dt <= timedelta(days=1):
            idx = sorted_dates.index(last_active)
            current_end = last_active
            for i in range(idx, -1, -1):
                d = sorted_dates[i]
                if contributions.get(d, 0) > 0:
                    current_streak += 1
                    current_start = d
                else:
                    break

    def fmt(d):
        if not d:
            return "-"
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%b %d")
        except Exception:
            return d

    return {
        "current_streak": current_streak,
        "current_range": (
            f"{fmt(current_start)} - {fmt(current_end)}" if current_streak > 0 else "No active streak"
        ),
        "longest_streak": longest_streak,
        "longest_range": (
            f"{fmt(longest_start)} - {fmt(longest_end)}" if longest_streak > 0 else "No streak recorded"
        ),
    }


def compute_grade(stars, commits, prs, contributions):
    score = min(stars * 4, 100) + min(commits * 1.65, 250) + min(prs * 0.5, 20) + min(contributions * 2, 10)
    if score >= 300:
        return "A+"
    elif score >= 250:
        return "A"
    elif score >= 200:
        return "A-"
    elif score >= 150:
        return "B+"
    elif score >= 100:
        return "B"
    elif score >= 50:
        return "B-"
    elif score >= 30:
        return "C+"
    return "C"


def generate_svg(stats, streak, langs, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    width = 560
    rows = (len(langs) + 1) // 2
    height = max(560, 400 + 90 + rows * 26 + 20)

    grade = stats.get("grade", "A+")
    if grade == "A+":
        grade_color = "#BF91F3"
    elif grade.startswith("A"):
        grade_color = "#38BDAE"
    elif grade.startswith("B"):
        grade_color = "#FF9E64"
    else:
        grade_color = "#70A5FD"

    # Progress bar
    bar_x, bar_y, bar_width, bar_height = 30, 50, 500, 10
    total_pct = sum(l["percentage"] for l in langs) or 1
    bar_svg_parts = []
    cur_x = bar_x
    for lang in langs:
        seg_w = (lang["percentage"] / total_pct) * bar_width
        bar_svg_parts.append(
            f'<rect x="{cur_x:.2f}" y="{bar_y}" width="{seg_w:.2f}" height="{bar_height}" fill="{lang["color"]}" />'
        )
        cur_x += seg_w
    bar_svg = "\n            ".join(bar_svg_parts)

    # Legend
    legend_parts = []
    for idx, lang in enumerate(langs):
        col = idx % 2
        row = idx // 2
        x = 30 + col * 245
        y = 75 + row * 26
        legend_parts.append(f"""
        <g transform="translate({x}, {y})">
            <circle cx="6" cy="5" r="5" fill="{lang['color']}" />
            <text x="19" y="9" fill="#A9B1D6" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-size="12" font-weight="500">{lang['name']}</text>
            <text x="185" y="9" fill="#565F89" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-size="11.5" text-anchor="end">{lang['percentage']}%</text>
        </g>""")
    legend_svg = "\n".join(legend_parts)

    # Stats rows with icons
    stat_rows = [
        ("Total Stars",    stats["stars"],         "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.86L12 17.77l-6.18 3.23L7 14.14 2 9.27l6.91-1.01z", "#FFD43B"),
        ("Total Commits",  stats["commits"],       "M9 3v11.17L5.41 10.58 4 12l6 6 6-6-1.41-1.41L11 14.17V3H9zm-4 16h14v2H5z",               "#38BDAE"),
        ("Total PRs",      stats["prs"],           "M6 3a3 3 0 1 1 0 6 3 3 0 0 1 0-6zm12 0a3 3 0 1 1 0 6 3 3 0 0 1 0-6zm0 8c-1.5 0-4.5.67-6 2-1.5-1.33-4.5-2-6-2C2.33 11 0 12.08 0 15v2h24v-2c0-2.92-2.33-4-6-4z", "#70A5FD"),
        ("Total Issues",   stats["issues"],        "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z", "#FF9E64"),
        ("Contributed to", stats["contributions"], "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z", "#BF91F3"),
    ]
    stats_rows_svg = []
    for i, (label, value, icon_d, icon_color) in enumerate(stat_rows):
        y = i * 34
        stats_rows_svg.append(f"""
        <g transform="translate(0,{y})">
            <g transform="translate(0,-8) scale(0.75)"><path d="{icon_d}" fill="{icon_color}" opacity="0.9"/></g>
            <text x="22" y="4" fill="#8B97C8" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-size="13.5" font-weight="500">{label}:</text>
            <text x="185" y="4" fill="#E8ECF8" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-size="13.5" font-weight="700">{value}</text>
        </g>""")
    stats_svg = "\n".join(stats_rows_svg)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#13141f"/>
      <stop offset="100%" stop-color="#1a1b2e"/>
    </linearGradient>
    <linearGradient id="headerGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#BF91F3"/>
      <stop offset="100%" stop-color="#70A5FD"/>
    </linearGradient>
    <filter id="glow-grade" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="glow-streak" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="bar-clip">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="5"/>
    </clipPath>
  </defs>
  <style>
    @keyframes currstreak {{
      0% {{ font-size: 3px; opacity: 0.2; }}
      80% {{ font-size: 34px; opacity: 1; }}
      100% {{ font-size: 28px; opacity: 1; }}
    }}
    @keyframes fadein {{
      0% {{ opacity: 0; }} 100% {{ opacity: 1; }}
    }}
    @keyframes pulse {{
      0%,100% {{ opacity: 0.6; transform: scale(0.95); }}
      50% {{ opacity: 0.3; transform: scale(1.05); }}
    }}
  </style>

  <!-- Background -->
  <rect width="{width}" height="{height}" rx="16" fill="url(#bgGrad)"/>
  <rect width="{width}" height="{height}" rx="16" fill="none" stroke="#2A2C45" stroke-width="1"/>
  <!-- Top accent stripe -->
  <rect width="{width}" height="3" rx="1" fill="url(#headerGrad)" opacity="0.85"/>

  <!-- HEADER -->
  <g transform="translate(28,42)">
    <rect width="28" height="28" rx="6" y="-17" fill="#1F2240"/>
    <g transform="translate(4,-13) scale(0.83)">
      <path d="M0 12L5 12L5-2L0-2Z M8 12L13 12L13-14L8-14Z M16 12L21 12L21 2L16 2Z" fill="url(#headerGrad)"/>
    </g>
    <text x="38" y="2" fill="url(#headerGrad)" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-weight="800" font-size="17" letter-spacing="0.3">My GitHub Statistics</text>
  </g>

  <!-- STATS -->
  <g transform="translate(28,72)">
    {stats_svg}
    <!-- Grade Badge -->
    <g transform="translate(385,32)">
      <circle cx="45" cy="45" r="49" fill="none" stroke="{grade_color}" stroke-width="1" opacity="0.2" style="animation:pulse 3s ease-in-out infinite"/>
      <circle cx="45" cy="45" r="42" fill="#1A1C32" stroke="{grade_color}" stroke-width="3" filter="url(#glow-grade)" style="animation:fadein 0.5s linear forwards 0.3s"/>
      <circle cx="45" cy="45" r="36" fill="none" stroke="{grade_color}" stroke-width="0.8" opacity="0.3"/>
      <text x="45" y="56" fill="{grade_color}" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-weight="800" font-size="32" text-anchor="middle" filter="url(#glow-grade)" style="animation:fadein 0.5s linear forwards 0.5s">{grade}</text>
    </g>
  </g>

  <!-- Divider -->
  <line x1="28" y1="256" x2="532" y2="256" stroke="#252640" stroke-width="1"/>

  <!-- STREAKS -->
  <g transform="translate(18,265)">
    <!-- Current Streak -->
    <rect x="0" y="8" width="240" height="100" rx="10" fill="#17192C" stroke="#252640" stroke-width="1"/>
    <g transform="translate(120,62)">
      <g transform="translate(-12,-52)">
        <path d="M1.5.67S2.24 3.32 2.24 5.47C2.24 7.53.89 9.2-1.17 9.2-3.23 9.2-4.79 7.53-4.79 5.47l.03-.36C-6.78 7.51-8 10.62-8 13.99-8 18.41-4.42 22 0 22c4.42 0 8-3.59 8-8.01C8 8.6 5.41 3.79 1.5.67zM-.29 19c-1.78 0-3.22-1.4-3.22-3.14 0-1.62 1.05-2.76 2.81-3.12 1.77-.36 3.6-1.21 4.62-2.58.39 1.29.59 2.65.59 4.04C4.51 16.85 2.36 19-.29 19z" fill="#FF9E64" filter="url(#glow-streak)"/>
      </g>
      <circle cx="0" cy="5" r="26" fill="none" stroke="#BF91F3" stroke-width="3" filter="url(#glow-streak)"/>
      <text x="0" y="15" fill="#BF91F3" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-weight="700" font-size="26" text-anchor="middle" filter="url(#glow-streak)" style="animation:currstreak 0.6s linear forwards">{streak["current_streak"]}</text>
      <text x="0" y="55" fill="#BF91F3" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-weight="700" font-size="12" text-anchor="middle">Current Streak</text>
      <text x="0" y="72" fill="#565F89" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-size="11" text-anchor="middle">{streak["current_range"]}</text>
    </g>
    <!-- Longest Streak -->
    <rect x="284" y="8" width="240" height="100" rx="10" fill="#17192C" stroke="#252640" stroke-width="1"/>
    <g transform="translate(404,62)">
      <g transform="translate(-12,-52)">
        <path d="M19 5h-2V3H7v2H5c-1.1 0-2 .9-2 2v3c0 2.44 1.72 4.48 4 4.9V17c0 1.1.9 2 2 2h2v2H9v2h6v-2h-3v-2h2c1.1 0 2-.9 2-2v-2.1c2.28-.42 4-2.46 4-4.9V7c0-1.1-.9-2-2-2zM5 10V7h2v3H5zm14 0h-2V7h2v3z" fill="#FFD43B" opacity="0.9"/>
      </g>
      <text x="0" y="15" fill="#70A5FD" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-weight="700" font-size="26" text-anchor="middle" filter="url(#glow-streak)">{streak["longest_streak"]}</text>
      <text x="0" y="55" fill="#70A5FD" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-weight="700" font-size="12" text-anchor="middle">Longest Streak</text>
      <text x="0" y="72" fill="#565F89" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-size="11" text-anchor="middle">{streak["longest_range"]}</text>
    </g>
  </g>

  <!-- Divider -->
  <line x1="28" y1="388" x2="532" y2="388" stroke="#252640" stroke-width="1"/>

  <!-- LANGUAGES -->
  <g transform="translate(0,397)">
    <text x="28" y="28" fill="url(#headerGrad)" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Ubuntu,sans-serif" font-weight="800" font-size="17">Programming Languages</text>
    <!-- Bar track -->
    <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" fill="#1F2240" rx="5"/>
    <!-- Colored segments -->
    <g clip-path="url(#bar-clip)">
      {bar_svg}
    </g>
    <!-- Legend -->
    {legend_svg}
  </g>
</svg>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"SVG saved to {filepath}")


def main():
    username = "nigampalash"
    print(f"=== GitHub Stats Generator for {username} ===")
    token = os.environ.get("GITHUB_TOKEN")

    if token:
        print("GitHub token found — authenticated (5000 req/hr limit)")
    else:
        print("WARNING: No token — unauthenticated (60 req/hr). Commit counts may be incomplete.")

    # Fetch everything from GitHub API
    github_stats = fetch_from_github_api(username, token)

    stats = {
        "stars": "0",
        "commits": "0",
        "prs": "0",
        "issues": "0",
        "contributions": "0",
        "grade": "A+",
        "languages": [],
    }

    if github_stats:
        for k in ["stars", "commits", "prs", "issues", "contributions"]:
            v = github_stats.get(k, "0")
            if v and v != "0":
                stats[k] = v
        if github_stats.get("languages"):
            stats["languages"] = github_stats["languages"]

    # ── Manual commits floor from README ──────────────────────────────────
    # Format in README.md:  <!-- manual_commits: 401 -->
    # The README value is a FLOOR — if the API counts MORE, the API wins.
    # Use a leading '+' to add to the API count instead: <!-- manual_commits: +50 -->
    manual_commits = get_manual_commits()
    if manual_commits:
        if manual_commits.startswith(("+", "-")):
            try:
                original = int(stats["commits"])
                stats["commits"] = str(original + int(manual_commits))
                print(f"Applied relative commits offset {manual_commits}: {original} -> {stats['commits']}")
            except Exception as e:
                print("Error applying commits offset:", e)
        else:
            # Treat as a floor: use whichever is LARGER (API or manual)
            try:
                api_val = int(stats["commits"])
                floor_val = int(manual_commits)
                if floor_val > api_val:
                    stats["commits"] = manual_commits
                    print(f"API returned {api_val} commits — using manual floor {floor_val}")
                else:
                    print(f"API returned {api_val} commits — above floor {floor_val}, keeping API value")
            except Exception as e:
                print("Error applying commits floor:", e)

    # ── Manual stars floor from README ────────────────────────────────────
    # Format in README.md:  <!-- manual_stars: 48 -->
    manual_stars = get_manual_stars()
    if manual_stars:
        try:
            api_val = int(stats["stars"])
            floor_val = int(manual_stars)
            if floor_val > api_val:
                stats["stars"] = manual_stars
                print(f"API returned {api_val} stars — using manual floor {floor_val}")
            else:
                print(f"API returned {api_val} stars — above floor {floor_val}, keeping API value")
        except Exception as e:
            print("Error applying stars floor:", e)

    # Compute grade from final (floor-adjusted) stats
    try:
        stats["grade"] = compute_grade(
            int(stats["stars"]),
            int(stats["commits"]),
            int(stats["prs"]),
            int(stats["contributions"]),
        )
    except Exception as e:
        print("Warning: Could not compute grade:", e)
        stats["grade"] = "A+"

    print("\nFinal stats:")
    for k in ["stars", "commits", "prs", "issues", "contributions", "grade"]:
        print(f"  {k}: {stats[k]}")
    print(f"  languages: {len(stats['languages'])} entries")

    print("\nFetching streaks...")
    streak = get_streaks(username)
    print("Streaks:", streak)

    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "github_stats.svg"
    )
    generate_svg(stats, streak, stats["languages"], output_path)
    print("\nDone!")


if __name__ == "__main__":
    main()
