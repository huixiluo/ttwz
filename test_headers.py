#!/usr/bin/env python
"""尝试更完整的浏览器模拟"""
import os, re, json, time, requests, uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

with open(COOKIE_FILE) as f:
    saved_cookies = json.load(f)

session = requests.Session()
# 模拟完整浏览器请求头
session.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
})
for name, value in saved_cookies.items():
    session.cookies.set(name, value, domain=".toutiao.com", path="/")

# 访问发布页面
print("访问发布页面...")
resp = session.get("https://mp.toutiao.com/profile_v4/graphic/publish")
print(f"状态: {resp.status_code}, 长度: {len(resp.text)}")

# 提取CSRF
csrf_match = re.search(r'PASSPORT_CSRF_TOKEN["\s:=]+["\']([a-f0-9]+)', resp.text) or \
             re.search(r'passport_csrf_token["\s:=]+["\']([a-f0-9]+)', resp.text)
if csrf_match:
    page_csrf = csrf_match.group(1)
    print(f"页面CSRF: {page_csrf}")
else:
    page_csrf = saved_cookies.get('passport_csrf_token', '')
    print(f"Cookie CSRF: {page_csrf}")

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

# 更新请求头为API调用
session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Origin": "https://mp.toutiao.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
    "X-CSRFToken": page_csrf,
})

api_url = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231"
extra = json.dumps({"content_source": 100000000402, "content_word_cnt": word_count})

# 尝试不同的pgc_id生成方式
pgc_ids = [
    "",  # 空
    "0",  # 0
    str(uuid.uuid4()).replace("-", "")[:16],  # 随机
    str(int(time.time() * 1000)),  # 时间戳
]

for pgc_id in pgc_ids:
    payload = {
        "article_type": 0,
        "pgc_id": pgc_id,
        "source": 29,
        "title": title,
        "content": content_html,
        "save": 0,
        "entrance": "main",
        "timer_status": 0,
        "timer_time": "",
        "extra": extra,
    }
    print(f"\npgc_id='{pgc_id}'...")
    try:
        resp = session.post(api_url, json=payload)
        print(f"  {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(1)