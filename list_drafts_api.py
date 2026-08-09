# -*- coding: utf-8 -*-
"""获取草稿列表的API，找到可以编辑的现有草稿"""
import os, json, time, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf_token = cookies_dict.get("passport_csrf_token", "")

headers = {
    "Cookie": cookie_str,
    "X-CSRFToken": csrf_token,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://mp.toutiao.com/profile_v4/manage/draft",
    "Accept": "application/json, text/plain, */*",
}

# 草稿列表API
DRAFT_LIST_URL = "https://mp.toutiao.com/mp/agw/article/draft_list?source=mp&aid=1231"

print("[1] 获取草稿列表...")
resp = requests.get(DRAFT_LIST_URL, headers=headers, timeout=30)
print(f"  HTTP状态: {resp.status_code}")
print(f"  响应体: {resp.text[:2000]}")

try:
    result = resp.json()
    drafts = result.get("data", {}).get("drafts", []) or result.get("data", {}).get("list", [])
    print(f"\n  草稿数: {len(drafts)}")
    for i, d in enumerate(drafts[:5]):
        print(f"  [{i}] id={d.get('id') or d.get('pgc_id')}, title={d.get('title','')[:40]}")
except Exception as e:
    print(f"  解析错误: {e}")

# 也尝试POST方式
print("\n[2] 尝试POST方式获取草稿列表...")
DRAFT_LIST_URL2 = "https://mp.toutiao.com/mp/agw/article/draft_list"
data = {"source": "mp", "aid": "1231", "offset": 0, "count": 20}
resp2 = requests.post(DRAFT_LIST_URL2, data=data, headers=headers, timeout=30)
print(f"  HTTP状态: {resp2.status_code}")
print(f"  响应体: {resp2.text[:2000]}")

print("\nDONE")
