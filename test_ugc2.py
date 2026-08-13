#!/usr/bin/env python
"""测试save_ugc_draft - 尝试纯文本格式（微头条/短内容）"""
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

with open(MANIFEST_FILE) as f:
    articles = json.load(f)
art = articles[0]
title = art["title"]
with open(art["html_file"], "r", encoding="utf-8") as f:
    html = f.read()
paragraphs = re.findall(r'<p>([^<]+)</p>', html)
plain_text = "\n\n".join(p for p in paragraphs if p.strip())[:500]  # 短文本
csrf = saved_cookies.get('passport_csrf_token', '')

api_url = "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft"

# 尝试微头条格式
tests = [
    # 纯文本 + content字段
    {"content": plain_text, "title": ""},
    # 纯文本 + text字段
    {"text": plain_text},
    # 带article_type的各种值
    {"article_type": 0, "content": plain_text},
    {"article_type": 1, "content": plain_text},
    {"article_type": 2, "content": plain_text},
    {"article_type": 3, "content": plain_text},
    {"article_type": 10, "content": plain_text},
    {"article_type": 100, "content": plain_text},
    # 带aid
    {"article_type": 0, "aid": 1231, "content": plain_text},
    # 带content_type
    {"content_type": 0, "content": plain_text},
    {"content_type": 1, "content": plain_text},
    {"content_type": "ugc", "content": plain_text},
]

for i, params in enumerate(tests):
    print(f"\n--- 测试{i+1}: {json.dumps({k: str(v)[:30] for k, v in params.items()})} ---")
    try:
        resp = session.post(api_url, json=params, headers={
            "Content-Type": "application/json", "X-CSRFToken": csrf
        })
        print(f"  {resp.status_code}: {resp.text[:200]}")
        result = resp.json()
        if result.get('message') == 'success' or result.get('code') == 0:
            print("  *** SUCCESS! ***")
            break
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(0.5)