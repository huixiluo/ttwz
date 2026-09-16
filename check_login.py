# -*- coding: utf-8 -*-
"""检查cookie登录状态"""
import json, requests

with open("/workspace/toutiao_cookies.json", "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

print("cookie字段:", list(cookies_dict.keys()))
print("sessionid存在:", bool(cookies_dict.get("sessionid")))
print("csrf存在:", bool(cookies_dict.get("passport_csrf_token")))

cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
headers = {
    "Cookie": cookie_str,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/manage",
    "Accept": "application/json, text/plain, */*",
}

# 1) 文章列表
r1 = requests.get(
    "https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=10&type=&source=0&_signature=",
    headers=headers, timeout=30,
)
print("\n文章列表:", r1.status_code, r1.text[:200])

# 2) 草稿数
r2 = requests.get(
    "https://mp.toutiao.com/mp/agw/creator_center/draft_count?type=0&app_id=1231",
    headers=headers, timeout=30,
)
print("\n草稿数:", r2.status_code, r2.text[:200])

# 3) 用户信息
r3 = requests.get(
    "https://mp.toutiao.com/mp/agw/account/info?app_id=1231",
    headers=headers, timeout=30,
)
print("\n账号信息:", r3.status_code, r3.text[:300])
