import os
import json
import sys

def generate_svg():
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(workspace_dir, "scripts", "icons_cache.json")
    output_path = os.path.join(workspace_dir, "assets", "languages_tools.svg")
    
    if not os.path.exists(cache_path):
        print(f"Error: Cache file {cache_path} not found. Run download_and_format_icons.py first.")
        sys.exit(1)
        
    with open(cache_path, "r", encoding="utf-8") as f:
        icons = json.load(f)
        
    width = 560
    height = 340
    
    # Categories definition
    categories = [
        {
            "title": "Languages",
            "x": 30,
            "y": 98,
            "icons": [
                {"name": "java", "data": icons.get("java")},
                {"name": "python", "data": icons.get("python")},
                {"name": "cplusplus", "data": icons.get("cplusplus")},
                {"name": "javascript", "data": icons.get("javascript")}
            ]
        },
        {
            "title": "Frontend",
            "x": 295,
            "y": 98,
            "icons": [
                {"name": "html5", "data": icons.get("html5")},
                {"name": "css3", "data": icons.get("css3")},
                {"name": "react", "data": icons.get("react")},
                {"name": "bootstrap", "data": icons.get("bootstrap")}
            ]
        },
        {
            "title": "Backend &amp; Databases",
            "x": 30,
            "y": 223,
            "icons": [
                {"name": "nodejs", "data": icons.get("nodejs")},
                {"name": "express", "data": icons.get("express")},
                {"name": "mongodb", "data": icons.get("mongodb")},
                {"name": "mysql", "data": icons.get("mysql")}
            ]
        },
        {
            "title": "AI / ML &amp; Tools",
            "x": 295,
            "y": 223,
            "icons": [
                {"name": "tensorflow", "data": icons.get("tensorflow")},
                {"name": "pytorch", "data": icons.get("pytorch")},
                {"name": "git", "data": icons.get("git")},
                {"name": "vscode", "data": icons.get("vscode")},
                {"name": "arduino", "data": icons.get("arduino")}
            ]
        }
    ]
    
    # Generate XML elements for the icons
    # We assign a floating animation class class="float-X" from 1 to 6
    float_idx = 1
    content_svg = []
    
    for cat in categories:
        col_x = cat["x"]
        title_y = cat["y"]
        title = cat["title"]
        icons_list = cat["icons"]
        
        # Category Title
        content_svg.append(f'    <text x="{col_x}" y="{title_y}" class="category-title">{title}</text>')
        
        # Calculate x coordinates for the icons row
        n = len(icons_list)
        box_w = 42
        col_w = 235
        
        # Determine gap
        if n > 1:
            gap = (col_w - (n * box_w)) / (n - 1)
        else:
            gap = 0
            
        icons_y = title_y + 14 # y start for icons row
        
        for i, icon in enumerate(icons_list):
            if not icon["data"]:
                print(f"Warning: Icon data for {icon['name']} is missing!")
                continue
                
            x_pos = col_x + i * (box_w + gap)
            
            # Wrap the icon box and image inside a floating group
            content_svg.append(f"""
    <g class="float-{float_idx}">
        <!-- Icon Container Box -->
        <rect x="{x_pos:.1f}" y="{icons_y}" width="{box_w}" height="{box_w}" class="icon-box" rx="8" />
        <!-- Base64 Devicon Image -->
        <image xlink:href="{icon['data']}" x="{x_pos + 8:.1f}" y="{icons_y + 8}" width="26" height="26" />
    </g>""")
            
            # Rotate floating animation index from 1 to 6
            float_idx = (float_idx % 6) + 1
            
    svg_body = "\n".join(content_svg)
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}px" height="{height}px" viewBox="0 0 {width} {height}" direction="ltr">
    <style>
        @keyframes float-keyframes-1 {{
            0% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-4px); }}
            100% {{ transform: translateY(0px); }}
        }}
        @keyframes float-keyframes-2 {{
            0% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-2.5px); }}
            100% {{ transform: translateY(0px); }}
        }}
        @keyframes float-keyframes-3 {{
            0% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-3.5px); }}
            100% {{ transform: translateY(0px); }}
        }}
        
        .float-1 {{ animation: float-keyframes-1 3.5s ease-in-out infinite; }}
        .float-2 {{ animation: float-keyframes-2 4.0s ease-in-out infinite; animation-delay: 0.4s; }}
        .float-3 {{ animation: float-keyframes-3 4.5s ease-in-out infinite; animation-delay: 0.8s; }}
        .float-4 {{ animation: float-keyframes-1 3.8s ease-in-out infinite; animation-delay: 1.2s; }}
        .float-5 {{ animation: float-keyframes-2 4.3s ease-in-out infinite; animation-delay: 1.6s; }}
        .float-6 {{ animation: float-keyframes-3 4.8s ease-in-out infinite; animation-delay: 2.0s; }}
        
        .title {{
            fill: #BF91F3;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Ubuntu, sans-serif;
            font-weight: 700;
            font-size: 18px;
        }}
        .category-title {{
            fill: #70A5FD;
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
        .icon-box {{
            fill: #1F2335;
            stroke: #2F3147;
            stroke-width: 1.2;
            transition: all 0.3s ease;
        }}
        .icon-box:hover {{
            stroke: #BF91F3;
            fill: #24283B;
            filter: drop-shadow(0 0 4px rgba(191, 145, 243, 0.4));
        }}
    </style>
    
    <!-- Outer Card Background -->
    <rect class="card-border" width="{width - 2}" height="{height - 2}" x="1" y="1" />
    
    <!-- HEADER -->
    <g transform="translate(30, 45)">
        <!-- Wrench/Screwdriver Tool Icon -->
        <path d="M 0 5 Q 0 0 5 0 Q 7 0 9 2 C 11 0 14 0 16 2 L 18 4 Q 20 6 20 9 Q 20 11 18 13 L 13 18 Q 11 20 8 20 L 0 20 Z" fill="none" stroke="#BF91F3" stroke-width="2" />
        <circle cx="14" cy="6" r="2" fill="#BF91F3" />
        <path d="M 0 20 L 7 13" stroke="#BF91F3" stroke-width="2.5" stroke-linecap="round" />
        <text x="32" y="8" class="title">Languages &amp; Tools</text>
    </g>
    
    <!-- GRID CONTENT -->
{svg_body}
</svg>
"""
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Successfully generated tools SVG at {output_path}")

if __name__ == "__main__":
    generate_svg()
