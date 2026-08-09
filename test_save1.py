# -*- coding: utf-8 -*-
"""测试save=1是否真的创建草稿"""
import os, json, time, requests, random, re
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "toutiao_cookies.json"), "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf_token = cookies_dict.get("passport_csrf_token", "")

headers = {
    "Cookie": cookie_str,
    "Content-Type": "application/x-www-form-urlencoded",
    "X-CSRFToken": csrf_token,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Origin": "https://mp.toutiao.com",
    "Accept": "application/json, text/plain, */*",
}

# 获取当前草稿数
def get_draft_count():
    resp = requests.get("https://mp.toutiao.com/mp/agw/creator_center/draft_count?type=0&app_id=1231", headers=headers, timeout=10)
    return resp.json().get("count", 0)

def get_draft_list():
    resp = requests.get("https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=0&count=50&app_id=1231", headers=headers, timeout=10)
    return resp.json().get("draft_list", [])

print(f"保存前草稿数: {get_draft_count()}")

# 构建简单的测试文章
title = "测试文章save1请删除"
content_html = "<p>这是一段测试内容。</p><p>用于验证save=1是否创建草稿。</p>"

title_id = f"{int(time.time()*1000)}_{random.randint(1000000000000000, 9999999999999999)}"

extra = {
    "content_source": "100000000402",
    "content_word_cnt": 30,
    "is_multi_title": 0,
    "sub_titles": [],
    "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
    "tuwen_wtt_transfer_switch": "1"
}

form_data = {
    "source": "29",
    "extra": json.dumps(extra, ensure_ascii=False),
    "content": content_html,
    "title": title,
    "search_creation_info": json.dumps({"searchTopOne": 0, "abstract": "", "clue_id": ""}, ensure_ascii=False),
    "title_id": title_id,
    "mp_editor_stat": "{}",
    "is_refute_rumor": "0",
    "save": "1",
    "entrance": "",
    "timer_status": "0",
    "timer_time": "",
    "educluecard": "",
    "draft_form_data": json.dumps({"coverType": 2}, ensure_ascii=False),
    "pgc_feed_covers": "[]",
    "article_ad_type": "3",
    "claim_exclusive": "0",
    "is_fans_article": "0",
    "govern_forward": "0",
    "praise": "0",
    "disable_praise": "0",
    "tree_plan_article": "0",
    "star_order_id": "",
    "star_order_name": "",
    "customer_nick_name": "",
    "activity_tag": "0",
    "trends_writing_tag": "0",
}

SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"

print(f"\n[1] 调用save=1...")
resp = requests.post(SAVE_URL, data=urlencode(form_data), headers=headers, timeout=30)
result = resp.json()
print(f"  code: {result.get('code')}")
print(f"  data keys: {list(result.get('data', {}).keys())}")
print(f"  pgc_id in data: {result.get('data', {}).get('pgc_id', 'N/A')}")
print(f"  响应体前500字: {resp.text[:500]}")

# 等待一下再检查
time.sleep(3)
print(f"\n[2] 保存后草稿数: {get_draft_count()}")

# 检查草稿列表
drafts = get_draft_list()
print(f"  草稿列表数: {len(drafts)}")
found = False
for d in drafts:
    ge = d.get("graphic_extra", "{}")
    try:
        ge_json = json.loads(ge) if isinstance(ge, str) else ge
        t = ge_json.get("title", "")
        if "测试" in t or "save1" in t:
            print(f"  *** 找到测试草稿: gid={d.get('gid')} title={t}")
            found = True
    except:
        pass
if not found:
    print("  未找到测试草稿")

# 也尝试type=1和其他类型
for t in [1, 2, 3]:
    resp2 = requests.get(f"https://mp.toutiao.com/mp/agw/creator_center/draft_count?type={t}&app_id=1231", headers=headers, timeout=10)
    count = resp2.json().get("count", 0)
    if count > 0:
        print(f"  type={t} 草稿数: {count}")

print("\nDONE")
