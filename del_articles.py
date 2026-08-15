# -*- coding: utf-8 -*-
"""删除误发布的文章"""
import json, requests
from urllib.parse import urlencode

with open("/workspace/toutiao_cookies.json", "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)
cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf = cookies_dict.get("passport_csrf_token", "")

headers = {
    "Cookie": cookie_str,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://mp.toutiao.com",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/manage",
    "Accept": "application/json, text/plain, */*",
    "X-CSRFToken": csrf,
    "Content-Type": "application/x-www-form-urlencoded",
}

# 误发布: 2篇过审 + 1篇被拒 + 1篇测试
TARGET_IDS = [
    "7674328585989145122",  # 绿水青山（已发布）
    "7674328506301547034",  # 河南贾鲁河（已发布）
    "7674328511099732515",  # 纪念江泽民（被拒）
    "7674327342466040370",  # API保存测试（已发布）
]

def try_delete(pgc_id):
    attempts = [
        ("https://mp.toutiao.com/mp/agw/article/delete?source=mp&type=article&aid=1231",
         {"pgc_id": pgc_id, "group_id": pgc_id}),
        ("https://mp.toutiao.com/mp/agw/article/delete",
         {"pgc_id": pgc_id, "source": "mp", "type": "article"}),
    ]
    for url, data in attempts:
        try:
            resp = requests.post(url, data=urlencode(data), headers=headers, timeout=30)
            txt = resp.text[:200]
            print(f"  {resp.status_code} {txt}")
            try:
                r = resp.json()
                if r.get("code") == 0:
                    return True
            except Exception:
                pass
        except Exception as e:
            print(f"  ERR {e}")
    return False

for pid in TARGET_IDS:
    print(f"删除 {pid}:")
    if try_delete(pid):
        print("  --> 成功")
    print()

# 验证
time.sleep(2)
resp = requests.get(
    "https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=10&type=&source=0&_signature=",
    headers=headers, timeout=30,
)
arts = (resp.json().get("data") or {}).get("articles") or []
print("=== 剩余前6条 ===")
for a in arts[:6]:
    print(f"  [{'draft' if a.get('is_draft') else 'pub'}] {a.get('title', '')[:35]}")
