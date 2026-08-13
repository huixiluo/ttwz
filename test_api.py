#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试API：只上传纯文字到草稿箱"""
import os, json, time, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

with open(COOKIE_FILE) as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://mp.toutiao.com/",
    "Origin": "https://mp.toutiao.com",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 验证登录
resp = session.get("https://mp.toutiao.com/profile_v4/manage/draft")
print(f"登录状态: {resp.status_code}, 长度: {len(resp.text)}")

# 读取第一篇文章
with open(MANIFEST_FILE) as f:
    articles = json.load(f)
art = articles[0]

# 用正则提取纯文字
import re
with open(art["html_file"], "r", encoding="utf-8") as f:
    html = f.read()
paragraphs = re.findall(r'<p>([^<]+)</p>', html)
text_content = "\n".join(p for p in paragraphs if p.strip())

csrf = cookies.get('passport_csrf_token', '')

# ===== 测试多种API和参数组合 =====
test_cases = [
    # 1. /mp/agw/article/publish (type=1草稿)
    {
        "url": "https://mp.toutiao.com/mp/agw/article/publish",
        "payload": {
            "article_type": 0,
            "source": 29,
            "type": 1,
            "title": art["title"],
            "content": text_content,
            "extra": json.dumps({"content_source": 100000000402}),
        }
    },
    # 2. /mp/agw/article/publish (不带extra)
    {
        "url": "https://mp.toutiao.com/mp/agw/article/publish",
        "payload": {
            "article_type": 0,
            "source": 29,
            "type": 1,
            "title": art["title"],
            "content": text_content,
        }
    },
    # 3. /mp/agw/draft/save_ugc_draft
    {
        "url": "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft",
        "payload": {
            "article_type": 0,
            "title": art["title"],
            "content": text_content,
        }
    },
    # 4. /mp/agw/article/publish (type=0发布，看返回什么)
    {
        "url": "https://mp.toutiao.com/mp/agw/article/publish",
        "payload": {
            "article_type": 0,
            "source": 29,
            "type": 0,
            "title": art["title"],
            "content": text_content,
        }
    },
]

for i, tc in enumerate(test_cases):
    print(f"\n--- 测试{i+1}: {tc['url']} ---")
    print(f"  payload keys: {list(tc['payload'].keys())}")
    try:
        resp = session.post(tc["url"], json=tc["payload"], headers={
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
        })
        print(f"  status: {resp.status_code}")
        print(f"  response: {resp.text[:500]}")
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(1)