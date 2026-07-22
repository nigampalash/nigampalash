import urllib.request
import re
import os
import sys
import json
from datetime import datetime, timedelta, timezone

def fetch_from_github_api(username, token=None):
    base_headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/vnd.github.v3+json, application/vnd.github.cloak-preview+json'
    }
        
    def get_json(url, use_token=True):
        req_headers = dict(base_headers)
        if use_token and token:
            if token.startswith("Bearer ") or token.startswith("token "):
                req_headers['Authorization'] = token
            else:
                req_headers['Authorization'] = f"token {token}"
        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8')), resp.headers
        except urllib.error.HTTPError as e:
            if e.code == 401 and use_token and token:
                return get_json(url, use_token=False)
            raise e

    def get_json_data(url, use_token=True):
        data, _ = get_json(url, use_token)
        return data

    def parse_last_page(link_header):
        """Parse the last page number from a GitHub Link header."""
        if not link_header:
            return None
        # Link: <https://api.github.com/...&page=5>; rel="last"
        match = re.search(r'[<;,\s]page=(\d+)>;\s*rel=["\']last["\']', link_header)
        if match:
            return int(match.group(1))
        return None

    def count_commits_for_repo(owner, repo_name, author=None):
        """
        Use the GitHub API pagination trick: fetch 1 commit per page
        and read the last page number from the Link header.
        Returns the total commit count for the repo (optionally filtered by author).
        """
        if author:
            url = f"https://api.github.com/repos/{owner}/{repo_name}/commits?author={author}&per_page=1"
        else:
            url = f"https://api.github.com/repos/{owner}/{repo_name}/commits?per_page=1"
        
        req_headers = dict(base_headers)
        if token:
            if token.startswith("Bearer ") or token.startswith("token "):
                req_headers['Authorization'] = token
            else:
                req_headers['Authorization'] = f"token {token}"
        
        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req) as resp:
                link_header = resp.headers.get('Link', '')
                data = json.loads(resp.read().decode('utf-8'))
                
                last_page = parse_last_page(link_header)
                if last_page is not None:
                    return last_page
                elif isinstance(data, list):
                    return len(data)
                else:
                    return 0
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Empty repo (no commits)
                return 0
            print(f"  Warning: HTTP {e.code} for {owner}/{repo_name}: {e.reason}")
            return 0
        except Exception as e:
            print(f"  Warning: Error counting commits for {owner}/{repo_name}: {e}")
            return 0

    followers = 0
    total_stars = 0
    lang_bytes = {}
    total_commits = 0
    total_prs = 0
    total_issues = 0
    contributed_to = 0

    # 1. Fetch user profile
    try:
        print("Fetching user profile...")
        user_info = get_json_data(f"https://api.github.com/users/{username}")
        if user_info:
            followers = user_info.get("followers", 0)
    except Exception as e:
        print("Warning: Could not fetch user profile:", e)

    # 2. Fetch repos
    repos = []
    try:
        print("Fetching repositories...")
        page = 1
        while True:
            page_repos = get_json_data(f"https://api.github.com/user/repos?per_page=100&page={page}&affiliation=owner")
            if not page_repos or not isinstance(page_repos, list):
                break
            repos.extend(page_repos)
            if len(page_repos) < 100:
                break
            page += 1
            
        # Fallback to public repos if authenticated endpoint fails
        if not repos:
            page = 1
            while True:
                page_repos = get_json_data(f"https://api.github.com/users/{username}/repos?per_page=100&page={page}")
                if not page_repos or not isinstance(page_repos, list):
                    break
                repos.extend(page_repos)
                if len(page_repos) < 100:
                    break
                page += 1
                
        print(f"Found {len(repos)} repositories.")
        
        for r in repos:
            if r.get("fork"):
                continue
            total_stars += r.get("stargazers_count", 0)
            lang_url = r.get("languages_url")
            if lang_url:
                try:
                    langs = get_json_data(lang_url)
                    for lang, val in langs.items():
                        lang_bytes[lang] = lang_bytes.get(lang, 0) + val
                except Exception as e:
                    print(f"Warning: could not fetch languages for {r.get('name')}: {e}")
    except Exception as e:
        print("Warning: Could not fetch repositories:", e)

    # 3. Count commits across ALL own repos (not forks)
    # This is the most accurate approach: iterate every non-fork repo,
    # count commits authored by the user using the Link header trick
    print("Counting commits across all repositories (this is the most accurate method)...")
    own_repos = [r for r in repos if not r.get("fork")]
    for r in own_repos:
        repo_name = r.get("name", "")
        if not repo_name:
            continue
        count = count_commits_for_repo(username, repo_name, author=username)
        print(f"  {repo_name}: {count} commits by {username}")
        total_commits += count

    print(f"Total commits counted from all own repos: {total_commits}")

    # 4. Fetch PRs count
    try:
        print("Fetching PRs from search...")
        pr_data = get_json_data(f"https://api.github.com/search/issues?q=author:{username}+type:pr")
        if pr_data:
            total_prs = pr_data.get("total_count", 0)
    except Exception as e:
        print("Warning: Could not fetch PRs from search API:", e)

    # 5. Fetch Issues count
    try:
        print("Fetching issues from search...")
        issue_data = get_json_data(f"https://api.github.com/search/issues?q=author:{username}+type:issue")
        if issue_data:
            total_issues = issue_data.get("total_count", 0)
    except Exception as e:
        print("Warning: Could not fetch issues from search API:", e)

    # 6. Fetch Contributed to count
    try:
        print("Fetching contributions from search...")
        contrib_data = get_json_data(f"https://api.github.com/search/issues?q=author:{username}+type:pr+-user:{username}")
        contributed_repos = set()
        if contrib_data and "items" in contrib_data:
            for item in contrib_data["items"]:
                repo_url = item.get("repository_url")
                if repo_url:
                    repo_name = repo_url.split("/repos/")[-1]
                    contributed_repos.add(repo_name)
        contributed_to = len(contributed_repos)
    except Exception as e:
        print("Warning: Could not fetch contributions from search API:", e)

    # Format languages
    total_bytes = sum(lang_bytes.values())
    langs_list = []
    if total_bytes > 0:
        sorted_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)
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
            "SQL": "#e38c00"
        }
        for name, val in sorted_langs:
            pct = round((val / total_bytes) * 100, 2)
            color = color_map.get(name, "#858585")
            langs_list.append({
                "name": name,
                "percentage": pct,
                "color": color
            })
    langs_list = langs_list[:10]

    return {
        "stars": str(total_stars),
        "commits": str(total_commits),
        "prs": str(total_prs),
        "issues": str(total_issues),
        "contributions": str(contributed_to),
        "followers": followers,
        "languages": langs_list
    }

def get_manual_commits():
    try:
        readme_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Match HTML comment: <!-- manual_commits: +100 --> or <!-- manual_commits: 149 -->
            match_comment = re.search(r'<!--\s*(?:manual_commits|commits_override|commits):\s*([+-]?\d+)\s*-->', content)
            if match_comment:
                return match_comment.group(1)
            # Match query param: github_stats.svg?commits=+100 or github_stats.svg?commits=450
            match_param = re.search(r'github_stats\.svg\?(?:commits|manual_commits)=([+-]?\d+)', content)
            if match_param:
                return match_param.group(1)
    except Exception as e:
        print("Error reading manual commits:", e)
    return None

def get_streaks(username):
    contributions = {}
    # Fetch from 2023 to current year
    current_year = datetime.now().year
    years = list(range(2023, current_year + 1))
    
    for year in years:
        url = f"https://github.com/users/{username}/contributions?from={year}-01-01&to={year}-12-31"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')
            
            # Extract id and data-date from class ContributionCalendar-day
            day_tags = re.findall(r'<td\s+[^>]*class="[^"]*ContributionCalendar-day[^"]*"[^>]*>', html)
            id_to_date = {}
            for tag in day_tags:
                date_match = re.search(r'data-date="([^"]+)"', tag)
                id_match = re.search(r'id="([^"]+)"', tag)
                if date_match and id_match:
                    id_to_date[id_match.group(1)] = date_match.group(1)
            
            tooltips = re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]+)</tool-tip>', html)
            for tid, t in tooltips:
                t_clean = t.strip()
                if tid not in id_to_date:
                    continue
                date_str = id_to_date[tid]
                
                count = 0
                if "No contributions" in t_clean:
                    count = 0
                else:
                    match = re.match(r'(\d+)\s+contribution', t_clean)
                    if match:
                        count = int(match.group(1))
                contributions[date_str] = count
        except Exception as e:
            print(f"Error fetching contributions for {year}:", e)
            
    if not contributions:
        return {
            "current_streak": 0,
            "current_start": "-",
            "current_end": "-",
            "longest_streak": 0,
            "longest_start": "-",
            "longest_end": "-"
        }
        
    sorted_dates = sorted(contributions.keys())
    
    # Calculate Longest Streak
    longest_streak = 0
    longest_streak_start = None
    longest_streak_end = None
    
    temp_streak = 0
    temp_start = None
    
    for date_str in sorted_dates:
        count = contributions[date_str]
        if count > 0:
            if temp_streak == 0:
                temp_start = date_str
            temp_streak += 1
            if temp_streak > longest_streak:
                longest_streak = temp_streak
                longest_streak_start = temp_start
                longest_streak_end = date_str
        else:
            temp_streak = 0
            
    # Calculate Current Streak in Asia/Kolkata timezone (UTC + 5.5 hours)
    kolkata_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    today_str = kolkata_now.strftime("%Y-%m-%d")
    yesterday_str = (kolkata_now - timedelta(days=1)).strftime("%Y-%m-%d")
    
    current_streak = 0
    current_start = None
    current_end = None
    
    active_dates = [d for d in sorted_dates if contributions.get(d, 0) > 0]
    if active_dates:
        last_active = active_dates[-1]
        last_active_dt = datetime.strptime(last_active, "%Y-%m-%d").date()
        today_dt = datetime.strptime(today_str, "%Y-%m-%d").date()
        
        # Streak remains active if the last active contribution day was today or yesterday
        if today_dt - last_active_dt <= timedelta(days=1):
            idx = sorted_dates.index(last_active)
            current_streak = 0
            current_end = last_active
            for i in range(idx, -1, -1):
                d = sorted_dates[i]
                if contributions.get(d, 0) > 0:
                    current_streak += 1
                    current_start = d
                else:
                    break
                    
    # Format dates
    def format_date(d_str):
        if not d_str or d_str == "-":
            return "-"
        try:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            return dt.strftime("%b %d")
        except:
            return d_str
            
    return {
        "current_streak": current_streak,
        "current_range": f"{format_date(current_start)} - {format_date(current_end)}" if current_streak > 0 else "No active streak",
        "longest_streak": longest_streak,
        "longest_range": f"{format_date(longest_streak_start)} - {format_date(longest_streak_end)}" if longest_streak > 0 else "No streak recorded"
    }

def compute_grade(stars, commits, prs, contributions):
    """Compute a letter grade based on overall stats."""
    score = 0
    score += min(stars * 4, 100)
    score += min(commits * 1.65, 250)
    score += min(prs * 0.5, 20)
    score += min(contributions * 2, 10)

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
    else:
        return "C"

def generate_svg(stats, streak, langs, filepath):
    # Ensure dir exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    width = 560
    
    # Calculate dynamic height based on language count (2 columns)
    rows = (len(langs) + 1) // 2
    # Base height = 400 (header/stats/streaks) + 90 (lang title+bar) + rows*26 + 20 padding
    height = 400 + 90 + (rows * 26) + 20
    if height < 560:
        height = 560
    
    # Compute grade circle colors
    grade = stats.get("grade", "A+")
    grade_color = "#70A5FD"
    grade_glow = "rgba(112,165,253,0.35)"
    if grade == "A+":
        grade_color = "#BF91F3"
        grade_glow = "rgba(191,145,243,0.35)"
    elif grade.startswith("A"):
        grade_color = "#38BDAE"
        grade_glow = "rgba(56,189,174,0.35)"
    elif grade.startswith("B"):
        grade_color = "#FF9E64"
        grade_glow = "rgba(255,158,100,0.35)"
        
    # Build Lang Progress Bar segments
    bar_x = 30
    bar_y = 50
    bar_width = 500
    bar_height = 10
    bar_segments = []
    
    total_percentage = sum(l["percentage"] for l in langs)
    if total_percentage == 0:
        total_percentage = 1
        
    current_x = bar_x
    for i, lang in enumerate(langs):
        seg_w = (lang["percentage"] / total_percentage) * bar_width
        bar_segments.append(
            f'<rect x="{current_x:.2f}" y="{bar_y}" width="{seg_w:.2f}" height="{bar_height}" fill="{lang["color"]}" />'
        )
        current_x += seg_w

    # Build Lang Legend grid (2 columns)
    legend_items = []
    grid_cols = 2
    col_width = 245
    start_x = 30
    start_y = 75
    row_height = 26
    
    for idx, lang in enumerate(langs):
        col = idx % grid_cols
        row = idx // grid_cols
        x = start_x + (col * col_width)
        y = start_y + (row * row_height)
        legend_items.append(f"""
        <g transform="translate({x}, {y})">
            <circle cx="6" cy="5" r="5" fill="{lang["color"]}" />
            <text x="19" y="9" fill="#A9B1D6" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-size="12px" font-weight="500">{lang["name"]}</text>
            <text x="185" y="9" fill="#565F89" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-size="11.5px" text-anchor="end">{lang["percentage"]}%</text>
        </g>
        """)
        
    legend_svg = "\n".join(legend_items)
    bar_svg = "\n".join(bar_segments)

    # Stats rows with mini icons
    stat_rows = [
        ("Total Stars",      stats["stars"],         "M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14l-5-4.87 6.91-1.01z", "#FFD43B"),
        ("Total Commits",    stats["commits"],       "M9 3v11.17L5.41 10.58 4 12l6 6 6-6-1.41-1.41L11 14.17V3H9zm-4 16h14v2H5z",              "#38BDAE"),
        ("Total PRs",        stats["prs"],           "M6 3a3 3 0 1 1 0 6 3 3 0 0 1 0-6zm0 8c2.67 0 8 1.34 8 4v2H-2v-2c0-2.66 5.33-4 8-4zm12-5h-4v2h4v4h2v-4h4v-2h-4V2h-2v4z", "#70A5FD"),
        ("Total Issues",     stats["issues"],        "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z", "#FF9E64"),
        ("Contributed to",   stats["contributions"], "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z", "#BF91F3"),
    ]

    stats_svg_rows = []
    for i, (label, value, icon_d, icon_color) in enumerate(stat_rows):
        y = i * 34
        stats_svg_rows.append(f"""
        <g transform="translate(0, {y})">
            <g transform="translate(0, -8) scale(0.75)">
                <path d="{icon_d}" fill="{icon_color}" opacity="0.9"/>
            </g>
            <text x="22" y="4" class="stat-label">{label}:</text>
            <text x="185" y="4" class="stat-value">{value}</text>
        </g>""")
    stats_svg = "\n".join(stats_svg_rows)
    
    # Formulate whole SVG content
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px" viewBox="0 0 {width} {height}" direction="ltr">
    <defs>
        <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#13141f;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#1a1b2e;stop-opacity:1" />
        </linearGradient>
        <linearGradient id="headerGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" style="stop-color:#BF91F3;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#70A5FD;stop-opacity:1" />
        </linearGradient>
        <filter id="glow-grade">
            <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
            <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
            </feMerge>
        </filter>
        <filter id="glow-streak">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
            </feMerge>
        </filter>
        <clipPath id="card-clip">
            <rect width="{width}" height="{height}" rx="16" ry="16"/>
        </clipPath>
        <clipPath id="bar-clip">
            <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="5" />
        </clipPath>
    </defs>
    
    <style>
        @keyframes currstreak {{
            0% {{ font-size: 3px; opacity: 0.2; }}
            80% {{ font-size: 34px; opacity: 1; }}
            100% {{ font-size: 28px; opacity: 1; }}
        }}
        @keyframes fadein {{
            0% {{ opacity: 0; }}
            100% {{ opacity: 1; }}
        }}
        @keyframes pulse-ring {{
            0% {{ opacity: 0.8; transform: scale(0.95); }}
            50% {{ opacity: 0.4; transform: scale(1.05); }}
            100% {{ opacity: 0.8; transform: scale(0.95); }}
        }}
        @keyframes shimmer {{
            0% {{ opacity: 0.6; }}
            50% {{ opacity: 1; }}
            100% {{ opacity: 0.6; }}
        }}
        .title {{
            fill: url(#headerGrad);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-weight: 800;
            font-size: 17px;
            letter-spacing: 0.3px;
        }}
        .stat-label {{
            fill: #8B97C8;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-size: 13.5px;
            font-weight: 500;
        }}
        .stat-value {{
            fill: #E8ECF8;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-size: 13.5px;
            font-weight: 700;
        }}
        .section-divider {{
            stroke: #252640;
            stroke-width: 1;
        }}
        .streak-label {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-weight: 700;
            font-size: 12px;
        }}
        .streak-range {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-weight: 400;
            font-size: 11px;
            fill: #565F89;
        }}
    </style>
    
    <!-- Card Background -->
    <rect width="{width}" height="{height}" rx="16" ry="16" fill="url(#bgGrad)" />
    <!-- Subtle border -->
    <rect width="{width - 1}" height="{height - 1}" x="0.5" y="0.5" rx="16" ry="16" fill="none" stroke="#2A2C45" stroke-width="1" />
    <!-- Top accent stripe -->
    <rect width="{width}" height="3" rx="1" fill="url(#headerGrad)" opacity="0.8"/>
    
    <!-- === HEADER === -->
    <g transform="translate(28, 42)">
        <!-- Icon -->
        <g transform="translate(0, -16)">
            <rect width="28" height="28" rx="6" fill="#1F2240"/>
            <g transform="translate(4, 4) scale(0.83)">
                <path d="M 0 12 L 5 12 L 5 -2 L 0 -2 Z M 8 12 L 13 12 L 13 -14 L 8 -14 Z M 16 12 L 21 12 L 21 2 L 16 2 Z" fill="url(#headerGrad)"/>
            </g>
        </g>
        <text x="38" y="2" class="title">My GitHub Statistics</text>
    </g>
    
    <!-- === SECTION 1: Key Statistics === -->
    <g transform="translate(28, 72)">
        {stats_svg}
        
        <!-- Grade Badge -->
        <g transform="translate(385, 32)">
            <!-- Outer glow ring (animated) -->
            <circle cx="45" cy="45" r="48" fill="none" stroke="{grade_color}" stroke-width="1" opacity="0.25" style="animation: pulse-ring 3s ease-in-out infinite;"/>
            <!-- Main ring -->
            <circle cx="45" cy="45" r="42" fill="#1A1C32" stroke="{grade_color}" stroke-width="3" opacity="0.9" filter="url(#glow-grade)" style="animation: fadein 0.5s linear forwards 0.3s"/>
            <!-- Inner accent ring -->
            <circle cx="45" cy="45" r="36" fill="none" stroke="{grade_color}" stroke-width="0.8" opacity="0.3"/>
            <!-- Grade text -->
            <text x="45" y="56" fill="{grade_color}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="800" font-size="32px" text-anchor="middle" filter="url(#glow-grade)" style="animation: fadein 0.5s linear forwards 0.5s">
                {grade}
            </text>
        </g>
    </g>
    
    <!-- Section Divider -->
    <line x1="28" y1="256" x2="532" y2="256" class="section-divider"/>
    
    <!-- === SECTION 2: Streaks === -->
    <g transform="translate(0, 265)">
        <!-- Current Streak box -->
        <g transform="translate(0, 0)">
            <rect x="18" y="8" width="240" height="100" rx="10" fill="#17192C" stroke="#252640" stroke-width="1"/>
            <g transform="translate(138, 62)">
                <!-- Fire Icon -->
                <g transform="translate(-12, -52)">
                    <path d="M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 C 4.51 16.85 2.36 19 -0.29 19 Z" fill="#FF9E64" filter="url(#glow-streak)"/>
                </g>
                <!-- Number circle -->
                <circle cx="0" cy="5" r="26" fill="none" stroke="#BF91F3" stroke-width="3" filter="url(#glow-streak)"/>
                <text x="0" y="15" fill="#BF91F3" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="700" font-size="26px" text-anchor="middle" filter="url(#glow-streak)" style="animation: currstreak 0.6s linear forwards">
                    {streak["current_streak"]}
                </text>
                <text x="0" y="55" class="streak-label" fill="#BF91F3" text-anchor="middle">Current Streak</text>
                <text x="0" y="72" class="streak-range" text-anchor="middle">{streak["current_range"]}</text>
            </g>
        </g>
        
        <!-- Longest Streak box -->
        <g transform="translate(302, 0)">
            <rect x="0" y="8" width="240" height="100" rx="10" fill="#17192C" stroke="#252640" stroke-width="1"/>
            <g transform="translate(120, 62)">
                <!-- Trophy icon -->
                <g transform="translate(-12, -52)">
                    <path d="M 5 0 L 19 0 L 19 2 L 21 2 C 22.1 2 23 2.9 23 4 L 23 7 C 23 9.44 21.28 11.48 19 11.9 L 19 14 C 19 15.1 18.1 16 17 16 L 15 16 L 15 18 L 18 18 L 18 20 L 6 20 L 6 18 L 9 18 L 9 16 L 7 16 C 5.9 16 5 15.1 5 14 L 5 11.9 C 2.72 11.48 1 9.44 1 7 L 1 4 C 1 2.9 1.9 2 3 2 L 5 2 Z M 3 4 L 3 7 L 5 7 L 5 4 Z M 19 7 L 21 7 L 21 4 L 19 4 Z" fill="#FFD43B" opacity="0.9"/>
                </g>
                <text x="0" y="15" fill="#70A5FD" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="700" font-size="26px" text-anchor="middle" filter="url(#glow-streak)">
                    {streak["longest_streak"]}
                </text>
                <text x="0" y="55" class="streak-label" fill="#70A5FD" text-anchor="middle">Longest Streak</text>
                <text x="0" y="72" class="streak-range" text-anchor="middle">{streak["longest_range"]}</text>
            </g>
        </g>
    </g>
    
    <!-- Section Divider -->
    <line x1="28" y1="388" x2="532" y2="388" class="section-divider"/>
    
    <!-- === SECTION 3: Programming Languages === -->
    <g transform="translate(0, 397)">
        <text x="28" y="28" class="title">Programming Languages</text>
        
        <!-- Progress Bar Background (Rounded Track) -->
        <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" fill="#1F2240" rx="5" />
        
        <!-- Progress Bar Segments -->
        <g clip-path="url(#bar-clip)">
            {bar_svg}
        </g>
        
        <!-- Legend Grid -->
        {legend_svg}
    </g>
</svg>
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"SVG saved to {filepath}")

def main():
    username = "nigampalash"
    print(f"Fetching GitHub stats for user: {username}")
    token = os.environ.get("GITHUB_TOKEN")
    
    if token:
        print("GitHub token found - using authenticated API (5000 req/hr limit)")
    else:
        print("WARNING: No GitHub token found - using unauthenticated API (60 req/hr limit)")
        print("         Commit counts may be inaccurate due to rate limiting.")
    
    # Fetch from GitHub API (primary source - most accurate)
    github_stats = fetch_from_github_api(username, token)
    
    stats = {
        "stars": "0",
        "commits": "0",
        "prs": "0",
        "issues": "0",
        "contributions": "0",
        "grade": "A+",
        "languages": []
    }
    
    if github_stats:
        print("Merging GitHub API stats...")
        for k in ["stars", "commits", "prs", "issues", "contributions"]:
            val = github_stats.get(k)
            if val and val != "0":
                stats[k] = val
        if github_stats.get("languages") and len(github_stats["languages"]) > 0:
            stats["languages"] = github_stats["languages"]
            
    # Compute grade from actual stats
    try:
        computed_grade = compute_grade(
            int(stats["stars"]),
            int(stats["commits"]),
            int(stats["prs"]),
            int(stats["contributions"])
        )
        stats["grade"] = computed_grade
        print(f"Computed grade: {computed_grade}")
    except Exception as e:
        print(f"Warning: Could not compute grade: {e}")
        stats["grade"] = "A+"

    # Apply manual commits override if present in README.md
    manual_commits_val = get_manual_commits()
    if manual_commits_val:
        if manual_commits_val.startswith(("+", "-")):
            try:
                offset = int(manual_commits_val)
                original = int(stats["commits"])
                stats["commits"] = str(original + offset)
                print(f"Applied relative commits offset {manual_commits_val} from README.md: {original} -> {stats['commits']}")
            except Exception as e:
                print("Error applying relative commits offset:", e)
        else:
            # Only use manual override if we got 0 from the API (fallback)
            if stats["commits"] == "0":
                stats["commits"] = manual_commits_val
                print(f"API returned 0 commits - applied manual override {manual_commits_val} from README.md.")
            else:
                print(f"API returned {stats['commits']} commits - ignoring manual override {manual_commits_val} in README.md.")
            
    print("Final stats calculated:")
    print(" - Stars:", stats["stars"])
    print(" - Commits:", stats["commits"])
    print(" - PRs:", stats["prs"])
    print(" - Issues:", stats["issues"])
    print(" - Contributed to:", stats["contributions"])
    print(" - Grade:", stats["grade"])
    print(" - Languages count:", len(stats["languages"]))
    
    print("Fetching streak information...")
    streak = get_streaks(username)
    print("Streaks calculated:", streak)
    
    # Target SVG file
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "github_stats.svg")
    generate_svg(stats, streak, stats["languages"], output_path)
    print("Done!")

if __name__ == "__main__":
    main()
