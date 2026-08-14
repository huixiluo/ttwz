#!/usr/bin/env python3
"""测试 save_ugc_draft - draft_type=1 正确，尝试不同内容格式"""
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
api_url = "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft"

# 测试 draft_type=1 的各种内容格式
tests = [
    # 不同内容字段名
    {"draft_type": 1, "text": "测试内容"},
    {"draft_type": 1, "body": "测试内容"},
    {"draft_type": 1, "description": "测试内容"},
    {"draft_type": 1, "summary": "测试内容"},
    # 尝试 content 和 text 同时
    {"draft_type": 1, "content": "测试内容", "text": "测试内容"},
    # 尝试 HTML
    {"draft_type": 1, "content": "<p>测试内容</p>"},
    {"draft_type": 1, "text": "<p>测试内容</p>"},
    # 尝试 form 格式
    {"draft_type": 1, "content": "测试内容", "title": "测试标题"},
    {"draft_type": 1, "text": "测试内容", "title": "测试标题"},
    # 尝试不同的 content-type
    {"draft_type": 1, "content": "测试内容", "draft_content": "测试内容"},
    # 尝试记录在 draft_list 中看到的格式
    {"draft_type": 1, "content": "测试内容", "abstract": "测试摘要"},
]

for i, params in enumerate(tests):
    print(f"\n--- 测试{i+1}: {json.dumps(params, ensure_ascii=False)[:120]} ---")
    try:
        # 先试 JSON
        resp = session.post(api_url, json=params, headers={
            "Content-Type": "application/json", "X-CSRFToken": csrf
        })
        try:
            result = resp.json()
        except:
            result = {"raw": resp.text[:200]}
        print(f"  JSON: {json.dumps(result, ensure_ascii=False)[:200]}")
        
        # 也试 form-urlencoded
        resp2 = session.post(api_url, data=params, headers={
            "Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrf
        })
        try:
            result2 = resp2.json()
        except:
            result2 = {"raw": resp2.text[:200]}
        print(f"  FORM: {json.dumps(result2, ensure_ascii=False)[:200]}")
        
        if result.get('code') == 0 or result2.get('code') == 0:
            print(f"  *** SUCCESS! ***")
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(0.3)