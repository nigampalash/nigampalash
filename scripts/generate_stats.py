import urllib.request
import re
import os
import sys
import json
from datetime import datetime, timedelta, timezone

def fetch_from_github_api(username, token=None):
    headers = {'User-Agent': 'Mozilla/5.0'}
    if token:
        headers['Authorization'] = f"Bearer {token}"
        
    def get_json(url):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
            
    try:
        # 1. Fetch user profile for followers
        print("Fetching user profile...")
        user_info = get_json(f"https://api.github.com/users/{username}")
        followers = user_info.get("followers", 0) if user_info else 0
        
        # 2. Fetch repos for stars and languages
        print("Fetching repositories...")
        repos = get_json(f"https://api.github.com/users/{username}/repos?per_page=100")
        total_stars = 0
        lang_bytes = {}
        
        # We will get languages for each non-fork repository
        for r in repos:
            if r.get("fork"):
                continue
            total_stars += r.get("stargazers_count", 0)
            
            # Fetch language details
            lang_url = r.get("languages_url")
            if lang_url:
                try:
                    langs = get_json(lang_url)
                    for lang, val in langs.items():
                        lang_bytes[lang] = lang_bytes.get(lang, 0) + val
                except Exception as e:
                    print(f"Warning: could not fetch languages for {r['name']}: {e}")
                    
        # 3. Fetch commits count
        print("Fetching commits from search...")
        commit_data = get_json(f"https://api.github.com/search/commits?q=author:{username}")
        total_commits = commit_data.get("total_count", 0) if commit_data else 0
        
        # 4. Fetch PRs count
        print("Fetching PRs from search...")
        pr_data = get_json(f"https://api.github.com/search/issues?q=author:{username}+type:pr")
        total_prs = pr_data.get("total_count", 0) if pr_data else 0
        
        # 5. Fetch Issues count
        print("Fetching issues from search...")
        issue_data = get_json(f"https://api.github.com/search/issues?q=author:{username}+type:issue")
        total_issues = issue_data.get("total_count", 0) if issue_data else 0
        
        # 6. Fetch Contributed to count
        print("Fetching contributions from search...")
        contrib_data = get_json(f"https://api.github.com/search/issues?q=author:{username}+type:pr+-user:{username}")
        contributed_repos = set()
        if contrib_data and "items" in contrib_data:
            for item in contrib_data["items"]:
                repo_url = item.get("repository_url")
                if repo_url:
                    repo_name = repo_url.split("/repos/")[-1]
                    contributed_repos.add(repo_name)
        contributed_to = len(contributed_repos)
        
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
    except Exception as e:
        print("Error fetching from direct GitHub API:", e)
        return None

def get_manual_commits():
    try:
        readme_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Match query param: github_stats.svg?commits=+100 or github_stats.svg?commits=450
            match_param = re.search(r'github_stats\.svg\?(?:commits|manual_commits)=([+-]?\d+)', content)
            if match_param:
                return match_param.group(1)
            # Match HTML comment: <!-- manual_commits: +100 --> or <!-- manual_commits: 450 -->
            match_comment = re.search(r'<!--\s*(?:manual_commits|commits_override):\s*([+-]?\d+)\s*-->', content)
            if match_comment:
                return match_comment.group(1)
    except Exception as e:
        print("Error reading manual commits:", e)
    return None

def get_stats(username):
    url = f"https://github-readme-stats-eight-theta.vercel.app/api?username={username}&count_private=true&include_all_commits=true&v={int(datetime.now().timestamp())}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
        
        texts = re.findall(r'<text[^>]*>([^<]+)</text>', content)
        texts_clean = [t.strip() for t in texts]
        
        stats = {
            "stars": "0",
            "commits": "0",
            "prs": "0",
            "issues": "0",
            "contributions": "0",
            "grade": "A+"
        }
        
        # Parse fields based on text layout
        try:
            if "Total Stars:" in texts_clean:
                idx = texts_clean.index("Total Stars:")
                stats["stars"] = texts_clean[idx + 1]
                if idx > 0:
                    stats["grade"] = texts_clean[idx - 1]
            if "Total Commits:" in texts_clean:
                idx = texts_clean.index("Total Commits:")
                stats["commits"] = texts_clean[idx + 1]
            if "Total PRs:" in texts_clean:
                idx = texts_clean.index("Total PRs:")
                stats["prs"] = texts_clean[idx + 1]
            if "Total Issues:" in texts_clean:
                idx = texts_clean.index("Total Issues:")
                stats["issues"] = texts_clean[idx + 1]
            if "Contributed to:" in texts_clean:
                idx = texts_clean.index("Contributed to:")
                stats["contributions"] = texts_clean[idx + 1]
        except Exception as e:
            print("Warning parsing stats lists:", e)
            
        return stats
    except Exception as e:
        print("Error fetching stats card:", e)
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

def get_languages(username):
    url = f"https://github-readme-stats-eight-theta.vercel.app/api/top-langs/?username={username}&langs_count=8&layout=compact&theme=tokyonight&border_radius=10&count_private=true&v={int(datetime.now().timestamp())}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
            
        texts = re.findall(r'<text[^>]*>([^<]+)</text>', content)
        texts_clean = [t.strip() for t in texts]
        
        # Find all circles with fill attributes
        circles = re.findall(r'<circle[^>]*fill="([^"]+)"[^>]*>', content)
        
        langs = []
        lang_idx = 0
        for t in texts_clean:
            # Match JavaScript (39.21%)
            match = re.match(r'([^)]+) \(([^%]+)%\)', t)
            if match:
                name = match.group(1).strip()
                percentage = float(match.group(2).strip())
                color = "#858585" # fallback gray
                if lang_idx < len(circles):
                    color = circles[lang_idx]
                langs.append({
                    "name": name,
                    "percentage": percentage,
                    "color": color
                })
                lang_idx += 1
        return langs
    except Exception as e:
        print("Error fetching languages card:", e)
        return []

def generate_svg(stats, streak, langs, filepath):
    # Ensure dir exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    width = 560
    
    # Calculate dynamic height based on language count (2 columns)
    rows = (len(langs) + 1) // 2
    # Base height without legend = 385 (header/stats/streaks) + 75 (language title + progress bar) = 460
    # Legend rows take rows * 24px, plus 15px margin
    height = 460 + (rows * 24) + 15
    if height < 550:
        height = 550
    
    # Compute grade circle colors
    grade_color = "#70A5FD"
    if stats["grade"] == "A+":
        grade_color = "#BF91F3"
    elif stats["grade"].startswith("A"):
        grade_color = "#38BDAE"
    elif stats["grade"].startswith("B"):
        grade_color = "#FF9E64"
        
    # Build Lang Progress Bar segments
    bar_x = 30
    bar_y = 50
    bar_width = 500
    bar_height = 8
    bar_segments = []
    
    total_percentage = sum(l["percentage"] for l in langs)
    if total_percentage == 0:
        total_percentage = 1
        
    current_x = bar_x
    for i, lang in enumerate(langs):
        seg_w = (lang["percentage"] / total_percentage) * bar_width
        # Rounded corners for the very left and very right segments
        rx = 4 if i == 0 or i == len(langs) - 1 else 0
        bar_segments.append(
            f'<rect x="{current_x}" y="{bar_y}" width="{seg_w}" height="{bar_height}" fill="{lang["color"]}" />'
        )
        current_x += seg_w

    # Build Lang Legend grid
    legend_items = []
    grid_cols = 2
    col_width = 240
    start_x = 35
    start_y = 75
    row_height = 24
    
    for idx, lang in enumerate(langs):
        col = idx % grid_cols
        row = idx // grid_cols
        x = start_x + (col * col_width)
        y = start_y + (row * row_height)
        legend_items.append(f"""
        <g transform="translate({x}, {y})">
            <circle cx="5" cy="5" r="5" fill="{lang["color"]}" />
            <text x="18" y="9" fill="#A9B1D6" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-size="12px" font-weight="500">{lang["name"]}</text>
            <text x="180" y="9" fill="#565F89" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-size="12px" text-anchor="end">{lang["percentage"]}%</text>
        </g>
        """)
        
    legend_svg = "\n".join(legend_items)
    bar_svg = "\n".join(bar_segments)
    
    # Formulate whole SVG content
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px" viewBox="0 0 {width} {height}" direction="ltr">
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
        .title {{
            fill: #BF91F3;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-weight: 700;
            font-size: 18px;
        }}
        .stat-label {{
            fill: #70A5FD;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-size: 14px;
            font-weight: 500;
        }}
        .stat-value {{
            fill: #38BDAE;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-size: 14px;
            font-weight: 700;
        }}
        .card-border {{
            stroke: #2F3147;
            stroke-width: 1.5;
            fill: #1A1B27;
            rx: 10px;
        }}
    </style>
    
    <!-- Outer Card Background -->
    <rect class="card-border" width="{width - 2}" height="{height - 2}" x="1" y="1" />
    
    <!-- HEADER -->
    <g transform="translate(30, 45)">
        <!-- GitHub Stats Icon (Simplified Graph Icon) -->
        <path d="M 0 10 L 5 10 L 5 -5 L 0 -5 Z M 8 10 L 13 10 L 13 -15 L 8 -15 Z M 16 10 L 21 10 L 21 0 L 16 0 Z" fill="#BF91F3" stroke="none"/>
        <text x="32" y="8" class="title">My GitHub Statistics</text>
    </g>
    
    <!-- SECTION 1: Key Statistics -->
    <g transform="translate(30, 80)">
        <!-- Stats list -->
        <g transform="translate(0, 0)">
            <!-- Stars -->
            <g transform="translate(0, 10)">
                <text class="stat-label">Total Stars:</text>
                <text x="180" class="stat-value">{stats["stars"]}</text>
            </g>
            <!-- Commits -->
            <g transform="translate(0, 40)">
                <text class="stat-label">Total Commits:</text>
                <text x="180" class="stat-value">{stats["commits"]}</text>
            </g>
            <!-- PRs -->
            <g transform="translate(0, 70)">
                <text class="stat-label">Total PRs:</text>
                <text x="180" class="stat-value">{stats["prs"]}</text>
            </g>
            <!-- Issues -->
            <g transform="translate(0, 100)">
                <text class="stat-label">Total Issues:</text>
                <text x="180" class="stat-value">{stats["issues"]}</text>
            </g>
            <!-- Contributed to -->
            <g transform="translate(0, 130)">
                <text class="stat-label">Contributed to:</text>
                <text x="180" class="stat-value">{stats["contributions"]}</text>
            </g>
        </g>
        
        <!-- Right side: Grade Badge -->
        <g transform="translate(390, 45)">
            <!-- Circle border -->
            <circle cx="45" cy="45" r="45" fill="none" stroke="{grade_color}" stroke-width="4.5" style="opacity: 0.8; animation: fadein 0.5s linear forwards 0.3s" />
            <!-- Grade character -->
            <text x="45" y="56" fill="{grade_color}" stroke="none" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="800" font-size="34px" text-anchor="middle" style="animation: fadein 0.5s linear forwards 0.5s">
                {stats["grade"]}
            </text>
        </g>
    </g>
    
    <!-- Divider Line -->
    <line x1="30" y1="245" x2="530" y2="245" stroke="#2F3147" stroke-width="1.5" />
    
    <!-- SECTION 2: Streaks -->
    <g transform="translate(0, 250)">
        <!-- Current Streak -->
        <g transform="translate(140, 50)">
            <!-- Fire Icon -->
            <g transform="translate(-10, -50)" scale="0.9">
                <path d="M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 C 4.51 16.85 2.36 19 -0.29 19 Z" fill="#FF9E64"/>
            </g>
            <!-- Number Circle -->
            <circle cx="0" cy="5" r="28" fill="none" stroke="#BF91F3" stroke-width="4.5" />
            <text x="0" y="15" fill="#BF91F3" stroke="none" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="700" font-size="28px" text-anchor="middle" style="animation: currstreak 0.6s linear forwards">
                {streak["current_streak"]}
            </text>
            
            <text x="0" y="55" fill="#BF91F3" stroke="none" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="700" font-size="14px" text-anchor="middle">Current Streak</text>
            <text x="0" y="75" fill="#38BDAE" stroke="none" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="400" font-size="12px" text-anchor="middle">{streak["current_range"]}</text>
        </g>
        
        <!-- Divider -->
        <line x1="280" y1="15" x2="280" y2="105" stroke="#2F3147" stroke-width="1.5" />
        
        <!-- Longest Streak -->
        <g transform="translate(420, 50)">
            <text x="0" y="15" fill="#70A5FD" stroke="none" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="700" font-size="28px" text-anchor="middle">
                {streak["longest_streak"]}
            </text>
            <text x="0" y="55" fill="#70A5FD" stroke="none" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="700" font-size="14px" text-anchor="middle">Longest Streak</text>
            <text x="0" y="75" fill="#38BDAE" stroke="none" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Ubuntu, sans-serif" font-weight="400" font-size="12px" text-anchor="middle">{streak["longest_range"]}</text>
        </g>
    </g>
    
    <!-- Divider Line -->
    <line x1="30" y1="375" x2="530" y2="375" stroke="#2F3147" stroke-width="1.5" />
    
    <!-- SECTION 3: Programming Languages -->
    <g transform="translate(0, 385)">
        <text x="30" y="25" class="title">My Programming Languages</text>
        
        <!-- Progress Bar Background (Rounded Track) -->
        <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" fill="#2F3147" rx="4" />
        
        <!-- Progress Bar Segments -->
        <g clip-path="url(#bar-clip)">
            {bar_svg}
        </g>
        
        <!-- Clip Path to round progress bar edges -->
        <clipPath id="bar-clip">
            <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="4" />
        </clipPath>
        
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
    
    # Try direct GitHub API first
    github_stats = fetch_from_github_api(username, token)
    
    # Fetch from Vercel for fallback and for grade
    print("Fetching Vercel stats card...")
    vercel_stats = get_stats(username)
    
    stats = {}
    if github_stats:
        print("Successfully fetched stats from direct GitHub API.")
        stats = github_stats
        # Use grade from Vercel if available, otherwise default to A+
        stats["grade"] = vercel_stats.get("grade", "A+") if vercel_stats else "A+"
    else:
        print("Falling back to Vercel API stats...")
        if vercel_stats:
            stats = vercel_stats
            print("Fetching Vercel languages card...")
            stats["languages"] = get_languages(username)
        else:
            print("Error: Both GitHub API and Vercel failed. Cannot proceed.")
            sys.exit(1)
            
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
            stats["commits"] = manual_commits_val
            print(f"Applied absolute commits override {manual_commits_val} from README.md.")
            
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
