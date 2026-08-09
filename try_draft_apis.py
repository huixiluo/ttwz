# -*- coding: utf-8 -*-
"""尝试常见的头条草稿列表API"""
import os, json, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "toutiao_cookies.json"), "r", encoding="utf-8") as f:
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

# 尝试多个可能的API端点
apis = [
    ("GET", "https://mp.toutiao.com/mp/agw/article/draft_list?source=mp&aid=1231&offset=0&count=20"),
    ("GET", "https://mp.toutiao.com/mp/agw/article/list?source=mp&aid=1231&status=draft&offset=0&count=20"),
    ("GET", "https://mp.toutiao.com/mp/agw/content/draft_list?source=mp&aid=1231&offset=0&count=20"),
    ("GET", "https://mp.toutiao.com/mp/agw/article/draft?source=mp&aid=1231&offset=0&count=20"),
    ("GET", "https://mp.toutiao.com/mp/agw/draft/list?source=mp&aid=1231&offset=0&count=20"),
    ("GET", "https://mp.toutiao.com/mp/agw/article/manage_list?source=mp&aid=1231&type=draft&offset=0&count=20"),
    ("GET", "https://mp.toutiao.com/mp/agw/content/list?source=mp&aid=1231&status=draft&offset=0&count=20"),
    ("GET", "https://mp.toutiao.com/mp/agw/article/all?source=mp&aid=1231&status=draft&offset=0&count=20"),
    ("POST", "https://mp.toutiao.com/mp/agw/article/draft_list"),
    ("POST", "https://mp.toutiao.com/mp/agw/content/draft_list"),
]

for method, url in apis:
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        else:
            resp = requests.post(url, data={"source": "mp", "aid": "1231", "offset": 0, "count": 20}, headers=headers, timeout=10)

        body = resp.text[:500]
        status = resp.status_code
        # 检查是否有有用数据
        has_data = any(kw in body for kw in ["pgc_id", "group_id", "draft", "title", "article"])
        marker = "***" if has_data else ""
        print(f"[{method}] {status} {marker} {url.split('/mp/agw/')[1][:60]}")
        if has_data:
            print(f"  -> {body[:300]}")
    except Exception as e:
        print(f"[{method}] ERR {url.split('/mp/agw/')[1][:60]}: {e}")

print("\nDONE")
