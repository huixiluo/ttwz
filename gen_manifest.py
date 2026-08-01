# -*- coding: utf-8 -*-
"""生成单篇文章封面图+清单"""
import os, json, base64, re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(BASE, "output")

# Find latest HTML
html_files = [f for f in os.listdir(output_dir) if f.startswith("hot_娱乐_") and f.endswith(".html")]
html_files.sort(key=lambda f: os.path.getmtime(os.path.join(output_dir, f)), reverse=True)
html_file = os.path.join(output_dir, html_files[0])
print(f"HTML: {html_file}")

# Read HTML and extract images
with open(html_file, "r", encoding="utf-8") as f:
    html = f.read()

imgs = re.findall(r'data:image/jpeg;base64,([^"]+)', html)
print(f"Found {len(imgs)} images")

# Save first 3 as cover images
cover_dir = os.path.join(output_dir, "covers")
os.makedirs(cover_dir, exist_ok=True)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
prefix = f"娱乐_1_{ts}"

cover_paths = []
for i, b64 in enumerate(imgs[:3]):
    img_bytes = base64.b64decode(b64)
    fname = f"{prefix}_cover_{i+1}.jpg"
    fpath = os.path.join(cover_dir, fname)
    with open(fpath, "wb") as f:
        f.write(img_bytes)
    cover_paths.append(fpath)
    print(f"Cover {i+1}: {fpath}")

# Extract title from HTML
title_m = re.search(r"<h1>(.*?)</h1>", html)
title = title_m.group(1) if title_m else "Unknown"

# Create manifest
manifest = [{
    "category": "娱乐",
    "keyword": "电影悟空大圣宣布撤档",
    "title": title,
    "article": "",
    "html_file": html_file,
    "cover_files": cover_paths,
}]

# Save manifest
manifest_path = os.path.join(BASE, "single_manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print(f"Manifest: {manifest_path}")
print(f"Title: {title}")
print("DONE")