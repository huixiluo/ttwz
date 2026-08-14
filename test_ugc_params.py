#!/usr/bin/env python3
"""测试 save_ugc_draft - 尝试各种 draft_type 参数"""
import json, requests, time

BASE_DIR = "/workspace"
COOKIE_FILE = f"{BASE_DIR}/toutiao_cookies.json"
MANIFEST_FILE = f"{BASE_DIR}/output/batch_manifest_tt.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

with open(COOKIE_FILE) as f:
    cookies = json.load(f)
with open(MANIFEST_FILE) as f:
    articles = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": UA, "Origin": "https://mp.toutiao.com", "Referer": "https://mp.toutiao.com/",
    "Accept": "application/json, text/plain, */*",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

csrf = cookies.get('passport_csrf_token', '')

# 测试 save_ugc_draft 的各种参数
api_url = "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft"

# 尝试不同的 draft_type 和相关参数
tests = [
    # 直接尝试 draft_type
    {"draft_type": 0, "content": "测试内容"},
    {"draft_type": 1, "content": "测试内容"},
    {"draft_type": 2, "content": "测试内容"},
    {"draft_type": 3, "content": "测试内容"},
    {"draft_type": "0", "content": "测试内容"},
    {"draft_type": "1", "content": "测试内容"},
    {"draft_type": "2", "content": "测试内容"},
    # 尝试 ugc_draft_type
    {"ugc_draft_type": 0, "content": "测试内容"},
    {"ugc_draft_type": 1, "content": "测试内容"},
    {"ugc_draft_type": 2, "content": "测试内容"},
    # 尝试 type
    {"type": 0, "content": "测试内容"},
    {"type": 1, "content": "测试内容"},
    {"type": 2, "content": "测试内容"},
    {"type": 3, "content": "测试内容"},
    # 尝试 content_type
    {"content_type": 0, "content": "测试内容"},
    {"content_type": 1, "content": "测试内容"},
    {"content_type": 2, "content": "测试内容"},
    # 尝试 genre
    {"genre": 0, "content": "测试内容"},
    {"genre": 1, "content": "测试内容"},
    {"genre": 2, "content": "测试内容"},
    # 完整文章参数
    {
        "draft_type": 2, "article_type": 0, "title": "测试",
        "content": "<p>测试内容</p>", "pgc_id": "", "source": 29
    },
    {
        "draft_type": 2, "article_type": "0", "title": "测试",
        "content": "<p>测试内容</p>", "pgc_id": "", "source": "29"
    },
    # 微头条格式尝试
    {"type": 1, "draft_type": 1, "content": "测试内容"},
    {"type": 2, "draft_type": 2, "content": "测试内容"},
    {"type": 0, "draft_type": 0, "content": "测试内容"},
]

for i, params in enumerate(tests):
    print(f"\n--- 测试{i+1}: {json.dumps(params, ensure_ascii=False)[:100]} ---")
    try:
        resp = session.post(api_url, json=params, headers={
            "Content-Type": "application/json", "X-CSRFToken": csrf
        })
        result = resp.json()
        code = result.get('code', '?')
        msg = result.get('message', '')
        gid = result.get('gid', '')
        print(f"  code={code}, msg={msg}, gid={gid}")
        if code == 0:
            print(f"  *** SUCCESS! gid={gid} ***")
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(0.3)