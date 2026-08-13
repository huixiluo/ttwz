#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过 API 上传文章到头条草稿箱（Linux环境）
关键发现：
1. 保存草稿用 save=0 + form-urlencoded
2. 先获取 pgc_id: GET /mp/agw/article/new
3. POST /mp/agw/article/publish?source=mp&type=article&aid=1231
"""
import os
import re
import json
import time
import base64
import requests
from io import BytesIO
from PIL import Image

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

    paragraphs = []
    images = []

    pattern = r'(<p>(.*?)</p>)|(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>\s*<p[^>]*>(.*?)</p>\s*</div>)'
    for m in re.finditer(pattern, html, re.DOTALL):
        if m.group(1):
            text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if text:
                paragraphs.append(text)
        elif m.group(4):
            images.append(m.group(4))

    return paragraphs, images

def get_new_pgc_id(session):
    """获取新建文章的pgc_id"""
    resp = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
        "article_type": 0,
        "format": "json",
        "compat": 1,
        "column_no": "",
    })
    try:
        data = resp.json()
        pgc_id = data.get("data", {}).get("pgc_id", "")
        if pgc_id:
            print(f"  获取pgc_id: {pgc_id}")
            return pgc_id
        print(f"  获取pgc_id失败: {resp.text[:200]}")
    except:
        print(f"  获取pgc_id异常: {resp.text[:200]}")
    return ""

def save_draft(session, pgc_id, title, content_html, word_count):
    """保存草稿（form-urlencoded格式）"""
    api_url = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231"

    extra = json.dumps({
        "content_source": 100000000402,
        "content_word_cnt": word_count,
    })

    form_data = {
        "article_type": "0",
        "pgc_id": pgc_id,
        "source": "29",
        "title": title,
        "content": content_html,
        "save": "0",  # 0=草稿, 1=发布
        "entrance": "main",
        "timer_status": "0",
        "timer_time": "",
        "extra": extra,
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

    csrf = session.cookies.get('passport_csrf_token', '')

    try:
        resp = session.post(api_url, data=form_data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrf,
        })
        print(f"  响应状态: {resp.status_code}")
        print(f"  响应内容: {resp.text[:300]}")
        result = resp.json()
        if result.get('message') == 'success':
            return True, result
        if result.get('code') == 0:
            return True, result
        return False, result
    except Exception as e:
        print(f"  异常: {e}")
        return False, {"error": str(e)}

def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传到草稿箱")
    print("=" * 60)

    session = create_session()

    # 验证登录状态
    resp = session.get("https://mp.toutiao.com/profile_v4/manage/draft")
    if "登录" in resp.text and len(resp.text) < 5000:
        print("[ERROR] Cookie可能已过期，需要重新登录")
        return
    print("[OK] 登录状态有效\n")

    success_count = 0
    for i, art in enumerate(articles, 1):
        title = art["title"]
        html_path = art["html_file"]

        print(f"[{i}/{len(articles)}] {title}")

        # 提取文字和图片
        paragraphs, images = extract_html_text_and_images(html_path)
        print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

        if not paragraphs:
            print("  [ERROR] 未提取到文字内容")
            continue

        # 构建HTML内容（纯文字，暂不带图片）
        content_parts = [f"<p>{p}</p>" for p in paragraphs]
        content_html = "\n".join(content_parts)
        word_count = sum(len(p) for p in paragraphs)

        # 获取pgc_id
        pgc_id = get_new_pgc_id(session)
        if not pgc_id:
            print("  [ERROR] 无法获取pgc_id")
            continue

        # 保存到草稿箱
        print(f"  保存草稿 (pgc_id={pgc_id}, {word_count}字)...")
        ok, result = save_draft(session, pgc_id, title, content_html, word_count)
        if ok:
            print(f"  [SUCCESS] 草稿保存成功!")
            print(f"  pgc_id: {result.get('data', {}).get('pgc_id', pgc_id)}")
            success_count += 1
        else:
            code = result.get('code', '?')
            msg = result.get('message', str(result))
            print(f"  [FAIL] 保存失败: code={code}, msg={msg}")

        time.sleep(2)

    print(f"\n{'='*60}")
    print(f"上传完成: {success_count}/{len(articles)} 篇成功")

if __name__ == "__main__":
    main()