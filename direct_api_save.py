# -*- coding: utf-8 -*-
"""直接用Python requests调用保存API，绕过浏览器自动化"""
import os, json, time, requests
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

# 构建cookies字符串
cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())

# 读取第2篇文章
with open("output/batch_manifest.json", "r", encoding="utf-8") as f:
    manifest = json.load(f)
art = manifest[1]  # 第2篇
title = art["title"][:30]
html_path = art["html_file"]

# 读取HTML正文
import re
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
content_html = ""
if body_match:
    body = body_match.group(1)
    # 提取所有p标签和img标签
    parts = []
    for m in re.finditer(r'<p>(.*?)</p>', body, re.DOTALL):
        clean = re.sub(r"<[^>]+>", "", m.group(1))
        if clean.strip():
            parts.append(f'<p>{clean}</p>')
    # 提取图片
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>', body, re.DOTALL):
        # 跳过base64图片，直接用文字占位
        parts.append('<p>图片</p>')
    content_html = "\n".join(parts)

print(f"文章: {title}")
print(f"正文段数: {content_html.count('<p>')}")

# 构建保存请求
SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"

# 构建请求体（URL-encoded form data）
extra = {
    "content_source": "100000000402",
    "content_word_cnt": len(re.sub(r'<[^>]+>', '', content_html)),
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
    "summary": re.sub(r'<[^>]+>', '', content_html)[:100],
    "summary_type": 0,
    "cover_media_type": 0,
    "has_cover": 0,
    "cover_num": 0,
    "media_title": title,
    "stick_top": 0,
    "stick_top_subject": 0,
    "original": 0,
    "is_original": 0,
    "prohibit_rewrite": 0,
    "wtt_content_line": 0,
    "stick_subject_id": "",
    "media_creation_source": 100000000402,
    "search_creation_source": 0,
    "high_quality": 0,
    "rel_subject": "",
    "enter_from": "mp",
    "is_fansub": 0,
    "pgc_id": ""
}

form_data = {
    "source": "29",
    "extra": json.dumps(extra, ensure_ascii=False),
    "content": content_html,
    "title": title,
    "search_creation_info": json.dumps(search_creation_info, ensure_ascii=False),
}

# 添加X-CSRFToken
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

print(f"\n[1] 直接调用保存API...")
print(f"  URL: {SAVE_URL}")
print(f"  CSRF Token: {csrf_token}")
print(f"  Content长度: {len(content_html)}")

# 发送请求
try:
    resp = requests.post(SAVE_URL, data=urlencode(form_data), headers=headers, timeout=30)
    print(f"\n[2] 响应:")
    print(f"  HTTP状态: {resp.status_code}")
    print(f"  响应体: {resp.text[:1000]}")

    # 解析响应
    try:
        result = resp.json()
        print(f"\n  code: {result.get('code')}")
        print(f"  message: {result.get('message')}")
        print(f"  pgc_id: {result.get('data', {}).get('pgc_id')}")
        if result.get("code") == 0:
            print("  [SUCCESS] 保存成功!")
        else:
            print(f"  [FAIL] 保存失败: {result.get('message')}")
    except:
        pass
except Exception as e:
    print(f"  请求错误: {e}")

print("\nDONE")
