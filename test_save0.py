# -*- coding: utf-8 -*-
"""测试save=0（草稿）直接API"""
import json, time, random, requests
from urllib.parse import urlencode

with open("/workspace/toutiao_cookies.json", "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)
cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf = cookies_dict.get("passport_csrf_token", "")

headers = {
    "Cookie": cookie_str,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://mp.toutiao.com",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Accept": "application/json, text/plain, */*",
    "X-CSRFToken": csrf,
    "Content-Type": "application/x-www-form-urlencoded",
}

SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"

title = "草稿参数测试-可删除"
content_html = "<p>测试save参数0是否保存为草稿，这段文字需要足够长以通过校验要求，继续补充内容以满足字数。</p>" * 2
word_cnt = 66

def make_form(save_val):
    ts = int(time.time() * 1000)
    extra = {
        "content_source": "100000000402",
        "content_word_cnt": word_cnt,
        "is_multi_title": 0,
        "sub_titles": [],
        "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
        "tuwen_wtt_transfer_switch": "1",
    }
    return {
        "source": "29",
        "extra": json.dumps(extra, ensure_ascii=False),
        "content": content_html,
        "title": title,
        "search_creation_info": json.dumps({"searchTopOne": 0, "abstract": "", "clue_id": ""}, ensure_ascii=False),
        "title_id": f"{ts}_{random.randint(10**15, 10**16 - 1)}",
        "mp_editor_stat": "{}",
        "is_refute_rumor": "0",
        "save": save_val,
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

resp = requests.post(SAVE_URL, data=urlencode(make_form("0")), headers=headers, timeout=60)
print("save=0:", resp.status_code, resp.text[:300])

# 检查该文章状态
time.sleep(3)
r2 = requests.get(
    "https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=5&type=&source=0&_signature=",
    headers=headers, timeout=30,
)
arts = (r2.json().get("data") or {}).get("articles") or []
for a in arts[:3]:
    print(f"  [{'draft' if a.get('is_draft') else 'pub'}] status={a.get('status')} {a.get('title', '')[:30]}")
