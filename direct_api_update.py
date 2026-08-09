# -*- coding: utf-8 -*-
"""直接用API更新现有草稿，包含pgc_id"""
import os, json, time, requests, random, re
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "toutiao_cookies.json"), "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf_token = cookies_dict.get("passport_csrf_token", "")

# 读取第2篇文章
with open("output/batch_manifest.json", "r", encoding="utf-8") as f:
    manifest = json.load(f)
art = manifest[1]
title = art["title"][:30]
html_path = art["html_file"]

# 读取HTML正文
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
content_html = ""
if body_match:
    body = body_match.group(1)
    parts = []
    for m in re.finditer(r'<p>(.*?)</p>', body, re.DOTALL):
        clean = re.sub(r"<[^>]+>", "", m.group(1))
        if clean.strip():
            parts.append(f'<p>{clean}</p>')
    content_html = "\n".join(parts)

word_cnt = len(re.sub(r'<[^>]+>', '', content_html))
print(f"文章: {title}")
print(f"正文字数: {word_cnt}")

# 读取草稿ID
with open("draft_ids.json", "r", encoding="utf-8") as f:
    editable_drafts = json.load(f)

pgc_id = editable_drafts[0]["gid"]
print(f"目标草稿pgc_id: {pgc_id}")
print(f"原标题: {editable_drafts[0]['title'][:40]}")

# 生成title_id
title_id = f"{int(time.time()*1000)}_{random.randint(1000000000000000, 9999999999999999)}"

# 构建请求体 - 包含pgc_id
extra = {
    "content_source": "100000000402",
    "content_word_cnt": word_cnt,
    "is_multi_title": 0,
    "sub_titles": [],
    "gd_ext": {
        "entrance": "",
        "from_page": "publisher_mp",
        "enter_from": "PC",
        "device_platform": "mp",
        "is_message": 0
    },
    "tuwen_wtt_transfer_switch": "1"
}

search_creation_info = {
    "searchTopOne": 0,
    "abstract": "",
    "clue_id": ""
}

form_data = {
    "source": "29",
    "extra": json.dumps(extra, ensure_ascii=False),
    "content": content_html,
    "title": title,
    "search_creation_info": json.dumps(search_creation_info, ensure_ascii=False),
    "title_id": title_id,
    "mp_editor_stat": "{}",
    "is_refute_rumor": "0",
    "save": "0",
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
    "pgc_id": pgc_id,  # 关键：包含pgc_id表示更新现有草稿
}

headers = {
    "Cookie": cookie_str,
    "Content-Type": "application/x-www-form-urlencoded",
    "X-CSRFToken": csrf_token,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": f"https://mp.toutiao.com/profile_v4/graphic/publish?pgc_id={pgc_id}",
    "Origin": "https://mp.toutiao.com",
    "Accept": "application/json, text/plain, */*",
}

SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"

print(f"\n[1] 调用保存API (更新现有草稿, pgc_id={pgc_id})...")

resp = requests.post(SAVE_URL, data=urlencode(form_data), headers=headers, timeout=30)
print(f"\n[2] 响应:")
print(f"  HTTP状态: {resp.status_code}")
print(f"  响应体: {resp.text[:1000]}")

try:
    result = resp.json()
    print(f"\n  code: {result.get('code')}")
    print(f"  pgc_id: {result.get('data', {}).get('pgc_id')}")
    if result.get("code") == 0:
        print("  [SUCCESS] 保存成功!")
    else:
        print(f"  [FAIL] code={result.get('code')}, message={result.get('message')}")
except:
    pass

# 也尝试save=1
print(f"\n[3] 尝试 save=1...")
form_data["save"] = "1"
resp2 = requests.post(SAVE_URL, data=urlencode(form_data), headers=headers, timeout=30)
print(f"  HTTP状态: {resp2.status_code}")
print(f"  响应体: {resp2.text[:500]}")

# 也尝试不带pgc_id但save=1
print(f"\n[4] 尝试 无pgc_id, save=1...")
form_data2 = form_data.copy()
del form_data2["pgc_id"]
form_data2["save"] = "1"
resp3 = requests.post(SAVE_URL, data=urlencode(form_data2), headers=headers, timeout=30)
print(f"  HTTP状态: {resp3.status_code}")
print(f"  响应体: {resp3.text[:500]}")

print("\nDONE")
