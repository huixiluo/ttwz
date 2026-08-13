#!/usr/bin/env python
"""测试save_ugc_draft端点 - 尝试各种参数组合"""
import os, re, json, time, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

with open(COOKIE_FILE) as f:
    saved_cookies = json.load(f)

session = requests.Session()
session.headers.update({"User-Agent": UA, "Origin": "https://mp.toutiao.com", "Referer": "https://mp.toutiao.com/"})
for name, value in saved_cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 先访问发布页面
session.get("https://mp.toutiao.com/profile_v4/graphic/publish")

# 读取文章
with open(MANIFEST_FILE) as f:
    articles = json.load(f)
art = articles[0]
title = art["title"]
with open(art["html_file"], "r", encoding="utf-8") as f:
    html = f.read()
paragraphs = re.findall(r'<p>([^<]+)</p>', html)
content_html = "\n".join(f"<p>{p}</p>" for p in paragraphs if p.strip())

csrf = saved_cookies.get('passport_csrf_token', '')

# 测试save_ugc_draft
api_url = "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft"

# 尝试不同的参数名和值
test_params = [
    # 不同参数名
    {"article_type": 0, "title": title, "content": content_html},
    {"article_type": "0", "title": title, "content": content_html},
    {"draft_type": 0, "title": title, "content": content_html},
    {"type": 0, "title": title, "content": content_html},
    {"type": 1, "title": title, "content": content_html},
    {"article_type": 0, "type": 1, "title": title, "content": content_html},
    # 带pgc_id
    {"article_type": 0, "pgc_id": "", "title": title, "content": content_html},
    # 带source
    {"article_type": 0, "source": 29, "title": title, "content": content_html},
    # 完整参数
    {"article_type": 0, "pgc_id": "", "source": 29, "title": title, "content": content_html, "save": 0},
]

for i, params in enumerate(test_params):
    print(f"\n--- 测试{i+1}: {params} ---")
    try:
        resp = session.post(api_url, json=params, headers={
            "Content-Type": "application/json", "X-CSRFToken": csrf
        })
        print(f"  {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(0.5)

# 也尝试form-urlencoded
print("\n\n=== form-urlencoded ===")
try:
    resp = session.post(api_url, data={
        "article_type": "0", "title": title, "content": content_html
    }, headers={"Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrf})
    print(f"  {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    print(f"  error: {e}")