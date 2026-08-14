#!/usr/bin/env python3
"""检查草稿箱状态"""
import json, requests

with open("/workspace/toutiao_cookies.json") as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://mp.toutiao.com/",
    "Origin": "https://mp.toutiao.com",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

csrf = cookies.get('passport_csrf_token', '')

# 1. 检查草稿列表
print("=== 草稿列表 ===")
resp = session.get("https://mp.toutiao.com/mp/agw/draft/draft_list", params={
    "format": "json", "category": "", "keyword": "", "page": 1, "size": 20,
    "compat": 1, "article_type": 0
})
try:
    data = resp.json()
    print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
except:
    print(f"Status: {resp.status_code}, Body: {resp.text[:500]}")

# 2. 检查登录状态
print("\n=== 登录状态 ===")
resp2 = session.get("https://mp.toutiao.com/mp/agw/info", params={"format": "json"})
try:
    data2 = resp2.json()
    print(json.dumps(data2, indent=2, ensure_ascii=False)[:1000])
except:
    print(f"Status: {resp2.status_code}, Body: {resp2.text[:500]}")