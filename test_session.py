#!/usr/bin/env python
"""测试：先访问发布页面建立session，再调用API"""
import os, re, json, time, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

with open(COOKIE_FILE) as f:
    saved_cookies = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
})
for name, value in saved_cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 第1步：访问发布页面，建立session
print("第1步：访问发布页面...")
resp = session.get("https://mp.toutiao.com/profile_v4/graphic/publish")
print(f"  状态: {resp.status_code}, 长度: {len(resp.text)}")

# 检查新的cookies
print(f"  当前cookies: {dict(session.cookies.get_dict())}")

# 从页面提取CSRF token
csrf_match = re.search(r'csrf_token["\s:=]+["\']?([a-f0-9]{32})', resp.text)
if csrf_match:
    csrf = csrf_match.group(1)
    print(f"  页面CSRF: {csrf}")
else:
    csrf = saved_cookies.get('passport_csrf_token', '')
    print(f"  使用cookie CSRF: {csrf}")

# 第2步：改为API请求头
session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Origin": "https://mp.toutiao.com",
})

# 读取文章
with open(MANIFEST_FILE) as f:
    articles = json.load(f)
art = articles[0]
title = art["title"]
with open(art["html_file"], "r", encoding="utf-8") as f:
    html = f.read()
paragraphs = re.findall(r'<p>([^<]+)</p>', html)
content_html = "\n".join(f"<p>{p}</p>" for p in paragraphs if p.strip())
word_count = sum(len(p) for p in paragraphs)

api_url = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231"
extra = json.dumps({"content_source": 100000000402, "content_word_cnt": word_count})

# 第3步：尝试多种方式
methods = [
    ("form-urlencoded + save=0", {
        "method": "form",
        "data": {"article_type": "0", "pgc_id": "", "source": "29", "title": title, "content": content_html, "save": "0", "entrance": "main", "timer_status": "0", "timer_time": "", "extra": extra},
        "headers": {"X-CSRFToken": csrf, "Content-Type": "application/x-www-form-urlencoded"},
    }),
    ("JSON + save=0", {
        "method": "json",
        "data": {"article_type": 0, "pgc_id": "", "source": 29, "title": title, "content": content_html, "save": 0, "entrance": "main", "timer_status": 0, "timer_time": "", "extra": extra},
        "headers": {"X-CSRFToken": csrf, "Content-Type": "application/json"},
    }),
    ("JSON + type=1", {
        "method": "json",
        "data": {"article_type": 0, "pgc_id": "", "source": 29, "title": title, "content": content_html, "type": 1, "entrance": "main", "extra": extra},
        "headers": {"X-CSRFToken": csrf, "Content-Type": "application/json"},
    }),
]

for name, cfg in methods:
    print(f"\n第3步：{name}")
    try:
        if cfg['method'] == 'form':
            resp = session.post(api_url, data=cfg['data'], headers=cfg['headers'])
        else:
            resp = session.post(api_url, json=cfg['data'], headers=cfg['headers'])
        print(f"  status: {resp.status_code}")
        print(f"  response: {resp.text[:500]}")
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(1)