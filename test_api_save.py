# -*- coding: utf-8 -*-
"""测试API直接保存草稿（save=1）"""
import json, time, random, requests
from urllib.parse import urlencode

BASE_DIR = "/workspace"
with open(f"{BASE_DIR}/toutiao_cookies.json", "r", encoding="utf-8") as f:
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

SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"

title = "API保存测试-可删除"
content_html = "<p>这是一段测试文字，用来验证API保存草稿功能是否正常可用，需要超过一定字数才能通过校验。</p>" * 3
word_cnt = len("这是一段测试文字，用来验证API保存草稿功能是否正常可用，需要超过一定字数才能通过校验。") * 3

extra = {
    "content_source": "100000000402",
    "content_word_cnt": word_cnt,
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
    "title_id": f"{int(time.time()*1000)}_{random.randint(1000000000000000, 9999999999999999)}",
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

resp = requests.post(SAVE_URL, data=urlencode(form_data), headers=headers, timeout=30)
print("status:", resp.status_code)
print("resp:", resp.text[:500])
