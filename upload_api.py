#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过 API 上传文章到头条草稿箱（Linux环境）"""
import os
import re
import json
import time
import base64
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def load_cookies():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://mp.toutiao.com/",
        "Origin": "https://mp.toutiao.com",
    })
    cookies = load_cookies()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".toutiao.com", path="/")
    return session

def extract_html_text_and_images(html_path):
    """从HTML文件中提取纯文字段落和图片base64"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')
    body = soup.find('body')
    if not body:
        return [], []

    paragraphs = []
    images = []

    for child in body.find_all(['p', 'div'], recursive=True):
        if child.name == 'p' and not child.find('img'):
            text = child.get_text(strip=True)
            if text:
                paragraphs.append(text)
        elif child.name == 'div' and 'img-wrap' in child.get('class', []):
            img = child.find('img')
            if img and img.get('src', '').startswith('data:image/'):
                images.append(img['src'])

    if not paragraphs:
        # Fallback: try regular p tags
        for p in body.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)

    return paragraphs, images

def upload_image_to_mp(session, base64_data_url):
    """上传图片到头条MP，返回图片URL"""
    from io import BytesIO
    from PIL import Image

    # 解析base64
    header, b64 = base64_data_url.split(',', 1)
    img_data = base64.b64decode(b64)

    # 压缩图片
    img = Image.open(BytesIO(img_data))
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=85)
    img_bytes = buf.getvalue()

    # 上传图片
    upload_url = "https://mp.toutiao.com/tools/upload_photo/"
    files = {
        'photo': ('image.jpg', img_bytes, 'image/jpeg')
    }
    resp = session.post(upload_url, files=files)
    try:
        result = resp.json()
        print(f"    图片上传响应: {result}")
        if result.get('message') == 'success':
            return result.get('data', {}).get('url', '') or result.get('url', '')
    except:
        print(f"    图片上传失败: {resp.text[:200]}")
    return ""

def save_draft(session, title, content_html, cover_urls=None):
    """保存草稿到头条"""
    # 尝试不同的API端点
    endpoints = [
        "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft",
        "https://mp.toutiao.com/mp/agw/draft/save",
        "https://mp.toutiao.com/mp/agw/article/save_draft",
    ]

    for endpoint in endpoints:
        for article_type in [0, 1, 2, 3, 10, 100]:
            payload = {
                "title": title,
                "content": content_html,
                "article_type": article_type,
                "cover_type": 3 if cover_urls else 0,
            }
            if cover_urls:
                payload["cover_images"] = cover_urls[:3]

            try:
                resp = session.post(endpoint, json=payload)
                result = resp.json()
                print(f"  {endpoint} article_type={article_type}: {result}")
                if result.get('message') == 'success' or result.get('code') == 0:
                    return True
            except Exception as e:
                print(f"  {endpoint} article_type={article_type}: 异常 {e}")

    return False

def save_draft_v2(session, title, content, paragraphs, images, cover_urls=None):
    """通过MP管理后台API保存草稿"""
    # 首先获取CSRF token
    mp_url = "https://mp.toutiao.com/profile_v4/graphic/publish"
    resp = session.get(mp_url)
    csrf = ""
    for cookie_name in ['passport_csrf_token', 'csrf_session_id']:
        if cookie_name in session.cookies:
            csrf = session.cookies[cookie_name]
            break

    print(f"  CSRF token: {csrf}")

    # 尝试API
    api_url = "https://mp.toutiao.com/mp/agw/draft/save_ugc_draft"

    # 尝试多种payload格式
    payloads = [
        # 格式1: 简单格式
        {
            "title": title,
            "content": content,
            "article_type": 0,
            "cover_type": 3 if cover_urls else 0,
        },
        # 格式2: 带更多字段
        {
            "title": title,
            "content": content,
            "article_type": 1,
            "cover_type": 3 if cover_urls else 0,
            "source": "ugc",
            "publish_type": 0,
        },
        # 格式3: FormData格式
        {
            "title": title,
            "content": content,
            "article_type": "ugc",
            "cover_type": 3 if cover_urls else 0,
        },
    ]

    headers_extra = {
        "X-CSRFToken": csrf,
        "Content-Type": "application/json",
    }

    for i, payload in enumerate(payloads):
        print(f"  尝试payload {i+1}: {json.dumps({k: str(v)[:50] for k, v in payload.items()}, ensure_ascii=False)}")
        try:
            resp = session.post(api_url, json=payload, headers=headers_extra)
            print(f"  响应: {resp.status_code} {resp.text[:300]}")
            try:
                result = resp.json()
                if result.get('message') == 'success' or result.get('code') == 0:
                    return True
            except:
                pass
        except Exception as e:
            print(f"  异常: {e}")

    return False

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")
    print("=" * 60)

    session = create_session()

    # 验证登录状态
    resp = session.get("https://mp.toutiao.com/profile_v4/manage/draft")
    print(f"草稿箱页面: {resp.status_code}, 长度: {len(resp.text)}")
    if "登录" in resp.text and len(resp.text) < 5000:
        print("[ERROR] Cookie可能已过期，需要重新登录")
        return

    print("[OK] 登录状态有效")

    for i, art in enumerate(articles, 1):
        title = art["title"]
        html_path = art["html_file"]
        cover_files = art.get("cover_files", [])

        print(f"\n[{i}/{len(articles)}] {title}")
        print(f"  HTML: {html_path}")
        print(f"  封面: {len(cover_files)}张")

        # 提取文字和图片
        paragraphs, images = extract_html_text_and_images(html_path)
        print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

        if not paragraphs:
            print("  [ERROR] 未提取到文字内容")
            continue

        # 构建纯文字内容
        text_content = "\n\n".join(paragraphs)
        print(f"  文字内容: {len(text_content)}字")

        # 尝试上传
        result = save_draft_v2(session, title, text_content, paragraphs, images, cover_files)
        if result:
            print(f"  [SUCCESS] 文章已保存到草稿箱")
        else:
            print(f"  [FAIL] 保存失败")

        time.sleep(2)

if __name__ == "__main__":
    main()