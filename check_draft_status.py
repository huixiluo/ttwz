#!/usr/bin/env python3
"""检查现有草稿状态 + 尝试用新pgc_id保存"""
import json, requests, re

BASE_DIR = "/workspace"
COOKIE_FILE = f"{BASE_DIR}/toutiao_cookies.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

with open(COOKIE_FILE) as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": UA, "Origin": "https://mp.toutiao.com", "Referer": "https://mp.toutiao.com/",
    "Accept": "application/json, text/plain, */*",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

csrf = cookies.get('passport_csrf_token', '')

# 1. 检查现有草稿
print("=== 草稿列表 ===")
resp = session.get("https://mp.toutiao.com/mp/agw/creator_center/draft_list", params={
    "type": 2, "count": 5, "app_id": 1231
})
data = resp.json()
if data.get('code') == 0:
    for draft in data.get('draft_list', [])[:3]:
        print(f"  gid={draft.get('gid')}, title={draft.get('title','')[:30]}")
        extra = draft.get('graphic_extra', '{}')
        try:
            extra_data = json.loads(extra)
            print(f"    article_type={extra_data.get('article_type')}, draft_type={draft.get('draft_type')}")
        except:
            pass

# 2. 检查现有草稿的详细信息
print("\n=== 草稿详情 (pgc_id=7673588172474942006) ===")
resp2 = session.get("https://mp.toutiao.com/mp/agw/article/edit", params={
    "pgc_id": "7673588172474942006", "wxstyle": 0, "format": "json"
})
data2 = resp2.json()
pgc = data2.get('article_pgc', {})
cc = pgc.get('content_cache', {})
print(f"  group_id: {cc.get('group_id')}")
print(f"  is_draft: {cc.get('is_draft')}")
print(f"  content length: {len(pgc.get('content', ''))}")
print(f"  title: {pgc.get('title', '')[:50]}")
print(f"  modify_count: {cc.get('modify_count')}")
print(f"  online_item_status: {cc.get('online_item_status')}")

# 3. 尝试用新创建的pgc_id保存
print("\n=== 尝试用新参数保存 ===")
# 先获取新的article info
resp3 = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
    "article_type": 0, "format": "json", "compat": 1, "column_no": "",
})
new_data = resp3.json()
media_id = new_data.get('data', {}).get('media', {}).get('id', '')
print(f"  media_id: {media_id}")

# 使用 media_id 作为 pgc_id 尝试保存
test_content = "<p>这是一段测试内容，用于验证保存功能。</p>"
test_title = "API测试保存"

extra = json.dumps({
    "content_source": 100000000402,
    "content_word_cnt": 15,
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
})

# 尝试各种pgc_id组合
for pgc_id_val in [str(media_id), "0", ""]:
    form_data = {
        "article_type": "0",
        "pgc_id": pgc_id_val,
        "source": "29",
        "title": test_title,
        "content": test_content,
        "extra": extra,
        "save": "0",
        "entrance": "main",
        "timer_status": "0",
        "timer_time": "",
        "title_id": "",
        "ic_uri_list": "[]",
        "search_creation_info": "",
        "is_refute_rumor": "0",
        "appid_list": "[]",
        "stock_ids": "[]",
        "concern_list": "[]",
        "comic_attr": "",
        "is_app_preview": "",
        "externalLinkChecked": "false",
        "externalLink": "",
        "claimOrigin": "0",
        "copyRightChecked": "1",
        "subTitle": "",
        "subCoverList": "[]",
        "coverList": "[]",
        "coverType": "0",
        "articleAdType": "0",
        "isFansArticle": "0",
        "activityId": "",
        "communitySync": "0",
    }
    
    resp = session.post(
        "https://mp.toutiao.com/mp/agw/article/publish",
        params={"source": "mp", "type": "article", "aid": "1231"},
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrf}
    )
    result = resp.json()
    print(f"  pgc_id={pgc_id_val}: code={result.get('code')}, msg={result.get('message')}")