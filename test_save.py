#!/usr/bin/env python
"""测试多种保存草稿的方式"""
import os, json, time, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

with open(COOKIE_FILE) as f:
    cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://mp.toutiao.com/",
    "Origin": "https://mp.toutiao.com",
})
for name, value in cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 读取第一篇文章
import re
with open(MANIFEST_FILE) as f:
    articles = json.load(f)
art = articles[0]
title = art["title"]
with open(art["html_file"], "r", encoding="utf-8") as f:
    html = f.read()
paragraphs = re.findall(r'<p>([^<]+)</p>', html)
text_content = "\n".join(p for p in paragraphs if p.strip())
content_html = "\n".join(f"<p>{p}</p>" for p in paragraphs if p.strip())
word_count = sum(len(p) for p in paragraphs)

# csrf = cookies.get('passport_csrf_token', '')
csrf = cookies.get('passport_csrf_token', '')
print(f"csrf={csrf}")
print(f"title={title}")
print(f"word_count={word_count}")

api_url = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231"

extra = json.dumps({"content_source": 100000000402, "content_word_cnt": word_count})

test_cases = [
    # 1. form-urlencoded, pgc_id为空
    {
        "name": "form-urlencoded, pgc_id=''",
        "method": "form",
        "data": {
            "article_type": "0", "pgc_id": "", "source": "29",
            "title": title, "content": content_html,
            "save": "0", "entrance": "main",
            "timer_status": "0", "timer_time": "",
            "extra": extra,
        }
    },
    # 2. JSON, pgc_id为空  
    {
        "name": "JSON, pgc_id=''",
        "method": "json",
        "data": {
            "article_type": 0, "pgc_id": "", "source": 29,
            "title": title, "content": content_html,
            "save": 0, "entrance": "main",
            "timer_status": 0, "timer_time": "",
            "extra": extra,
        }
    },
    # 3. JSON, 不带pgc_id
    {
        "name": "JSON, 不带pgc_id",
        "method": "json",
        "data": {
            "article_type": 0, "source": 29,
            "title": title, "content": content_html,
            "save": 0, "entrance": "main",
            "timer_status": 0, "timer_time": "",
            "extra": extra,
        }
    },
    # 4. form-urlencoded, 不带pgc_id
    {
        "name": "form-urlencoded, 不带pgc_id",
        "method": "form",
        "data": {
            "article_type": "0", "source": "29",
            "title": title, "content": content_html,
            "save": "0", "entrance": "main",
            "timer_status": "0", "timer_time": "",
            "extra": extra,
        }
    },
]

for tc in test_cases:
    print(f"\n--- {tc['name']} ---")
    try:
        if tc['method'] == 'form':
            resp = session.post(api_url, data=tc['data'], headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": csrf,
            })
        else:
            resp = session.post(api_url, json=tc['data'], headers={
                "Content-Type": "application/json",
                "X-CSRFToken": csrf,
            })
        print(f"  status: {resp.status_code}")
        print(f"  response: {resp.text[:500]}")
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(1)