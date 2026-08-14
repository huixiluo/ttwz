#!/usr/bin/env python3
"""检查 new API 返回的完整数据结构"""
import json, requests

BASE_DIR = "/workspace"
COOKIE_FILE = f"{BASE_DIR}/toutiao_cookies.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://mp.toutiao.com/",
    "Origin": "https://mp.toutiao.com",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 测试 new API
resp = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
    "article_type": 0, "format": "json", "compat": 1, "column_no": "",
})
data = resp.json()
print("=== new API 完整响应 ===")
print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])

# 也测试 edit API
print("\n=== edit API (已知pgc_id) ===")
resp2 = session.get("https://mp.toutiao.com/mp/agw/article/edit", params={
    "pgc_id": "7673588172474942006", "wxstyle": 0, "format": "json"
})
data2 = resp2.json()
print(json.dumps(data2, indent=2, ensure_ascii=False)[:3000])