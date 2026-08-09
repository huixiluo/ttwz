# -*- coding: utf-8 -*-
"""获取草稿ID列表"""
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

url = "https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=0&count=50&app_id=1231"
resp = requests.get(url, headers=headers, timeout=15)
print(f"HTTP状态: {resp.status_code}")

data = resp.json()
drafts = data.get("draft_list", [])
print(f"草稿数: {len(drafts)}")

# 我们的9篇文章标题关键词
our_titles = ["网红揭恶毒闺蜜", "神仙姐姐下沉市场", "复旦王水牛走红",
              "进球悼念故友", "孙颖莎登青年榜", "C罗表情包回应婚礼",
              "上海迎台风天", "拜登癌症扩散", "杭州地铁引热议"]

editable_drafts = []
for i, d in enumerate(drafts):
    gid = d.get("gid", "")
    title = ""
    # 从graphic_extra中获取标题
    ge = d.get("graphic_extra", "{}")
    try:
        ge_json = json.loads(ge) if isinstance(ge, str) else ge
        title = ge_json.get("title", "")
    except:
        pass

    is_ours = any(t in title for t in our_titles)
    marker = "[我们的]" if is_ours else "[可编辑]"

    print(f"  [{i}] {marker} gid={gid} title={title[:40]}")

    if not is_ours:
        editable_drafts.append({"gid": gid, "title": title, "index": i})

print(f"\n可编辑的草稿数: {len(editable_drafts)}")

# 保存草稿ID列表
with open(os.path.join(BASE_DIR, "draft_ids.json"), "w", encoding="utf-8") as f:
    json.dump(editable_drafts, f, ensure_ascii=False, indent=2)
print("已保存到 draft_ids.json")

print("\nDONE")
