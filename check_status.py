# -*- coding: utf-8 -*-
"""检查3篇新文章的详细状态"""
import json, requests

with open("/workspace/toutiao_cookies.json", "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)
cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())

headers = {
    "Cookie": cookie_str,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/manage",
    "Accept": "application/json, text/plain, */*",
}

resp = requests.get(
    "https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=10&type=&source=0&_signature=",
    headers=headers, timeout=30,
)
arts = (resp.json().get("data") or {}).get("articles") or []
print(f"共{len(arts)}条，取前6条详情:")
for a in arts[:6]:
    keep = {k: a.get(k) for k in [
        "title", "is_draft", "status", "is_passed", "is_unpass", "pass_time",
        "create_time", "article_url", "group_id", "can_user_del", "audit_status",
    ]}
    print(json.dumps(keep, ensure_ascii=False)[:400])
    print()

# 也查草稿专用列表接口
resp2 = requests.get(
    "https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=0&count=20&app_id=1231",
    headers=headers, timeout=30,
)
print("=== 草稿专用列表 ===")
try:
    d2 = resp2.json()
    dl = (d2.get("data") or {}).get("draft_list") or d2.get("draft_list") or []
    print(f"草稿数: {len(dl)}")
    for d in dl[:8]:
        t = ""
        try:
            ge = json.loads(d.get("graphic_extra") or "{}")
            t = ge.get("title", "")
        except Exception:
            pass
        print(f"  {t[:30] or d.get('title', '')[:30] if d.get('title') else '(空)'}")
except Exception as e:
    print("解析失败:", e, str(resp2.text)[:200])
