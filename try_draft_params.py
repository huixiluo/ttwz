# -*- coding: utf-8 -*-
"""尝试不同的参数获取草稿列表"""
import os, json, requests
from urllib.parse import urlencode

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

# 尝试不同的status和type参数
params_to_try = [
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "all"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "unpublished"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "0"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "1"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "2"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "type": "draft"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "type": "article", "status": "draft"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "list_status": "draft"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "article_status": "draft"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "filter": "draft"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "category": "draft"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "draft", "type": "article"},
    # 也尝试manage/content/all的API
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "all", "type": "article"},
    {"source": "mp", "aid": "1231", "offset": 0, "count": 20},  # 无status
]

base_url = "https://mp.toutiao.com/mp/agw/article/list"

for params in params_to_try:
    url = f"{base_url}?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        body = resp.text[:800]
        # 检查articles是否有内容
        try:
            data = resp.json()
            articles = data.get("data", {}).get("articles", [])
            count = data.get("data", {}).get("count", 0)
            marker = "***" if len(articles) > 0 or count > 0 else ""
            param_str = "&".join(f"{k}={v}" for k, v in params.items() if k not in ["source", "aid"])
            print(f"[{marker}] count={count} articles={len(articles)} params={param_str}")
            if len(articles) > 0:
                for a in articles[:3]:
                    print(f"  -> id={a.get('id') or a.get('pgc_id') or a.get('group_id')}, title={a.get('title','')[:40]}")
        except:
            print(f"[?] {body[:200]}")
    except Exception as e:
        print(f"ERR: {e}")

# 也尝试 manage/content API
print("\n=== 尝试manage/content API ===")
manage_apis = [
    "https://mp.toutiao.com/mp/agw/manage/content/list",
    "https://mp.toutiao.com/mp/agw/manage/content/draft",
    "https://mp.toutiao.com/mp/agw/manage/draft/list",
    "https://mp.toutiao.com/mp/agw/manage/article/list",
    "https://mp.toutiao.com/mp/agw/article/manage/list",
]

for api_url in manage_apis:
    params = {"source": "mp", "aid": "1231", "offset": 0, "count": 20, "status": "draft"}
    url = f"{api_url}?{urlencode(params)}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"[{resp.status_code}] {api_url.split('/mp/agw/')[1]}: {resp.text[:200]}")
    except Exception as e:
        print(f"ERR: {api_url}: {e}")

print("\nDONE")
