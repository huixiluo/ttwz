# -*- coding: utf-8 -*-
"""上传图片到头条图床 + 保存文章到草稿箱"""

import json, os, time, base64, requests, re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
ARTICLES_FILE = os.path.join(BASE_DIR, "_articles_3_tt.json")
IMAGES_DIR = os.path.join(BASE_DIR, "output", "body_imgs")
COVERS_DIR = os.path.join(BASE_DIR, "output", "covers")

with open(COOKIE_FILE, "r") as f:
    cookies = json.load(f)

with open(ARTICLES_FILE, "r") as f:
    articles = json.load(f)

# ===== 构建请求headers =====
session = requests.Session()
for k, v in cookies.items():
    session.cookies.set(k, v)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://mp.toutiao.com",
    "Referer": "https://mp.toutiao.com/",
}

# ===== Step 1: 上传图片到头条图床 =====
print("Step 1: 上传图片到头条图床...")
print("=" * 60)

all_image_urls = {}  # article_index -> [url1, url2, ...]

def upload_image(filepath):
    """上传一张图片到头条图床，返回URL"""
    with open(filepath, "rb") as f:
        img_data = f.read()
    
    # 读取文件
    ext = os.path.splitext(filepath)[1].lower()
    mime_type = f"image/{ext[1:]}" if ext != ".jpg" else "image/jpeg"
    
    # 头条图片上传API
    url = "https://mp.toutiao.com/mp/agw/spice/image"
    files = {
        "file": (f"image{ext}", img_data, mime_type)
    }
    data = {
        "source": "mp",
        "type": "article",
    }
    
    try:
        resp = session.post(url, files=files, data=data, headers={
            **headers,
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=30)
        print(f"  Upload response: {resp.status_code}")
        result = resp.json()
        print(f"  Result: {json.dumps(result, ensure_ascii=False)[:200]}")
        if result.get("code") == 0:
            img_url = result.get("data", {}).get("url") or result.get("url", "")
            return img_url
        else:
            print(f"  Upload failed: {result.get('message', 'unknown')}")
            return None
    except Exception as e:
        print(f"  Upload error: {e}")
        return None

for art_idx, art in enumerate(articles, 1):
    keyword = art["keyword"]
    print(f"\n[{art_idx}/{len(articles)}] {keyword}")
    
    urls = []
    for i in range(1, 6):
        fname = f"body_img_{art_idx}_{i}.jpg"
        fpath = os.path.join(IMAGES_DIR, fname)
        if os.path.exists(fpath):
            print(f"  上传图片{i}: {fname}...")
            img_url = upload_image(fpath)
            if img_url:
                urls.append(img_url)
                print(f"    ✓ {img_url[:80]}...")
            else:
                print(f"    ✗ 上传失败")
        else:
            print(f"  图片{i}: 文件不存在")
    
    all_image_urls[art_idx] = urls
    print(f"  共上传 {len(urls)} 张")

# ===== Step 2: 保存文章到草稿箱 =====
print("\n" + "=" * 60)
print("Step 2: 保存文章到草稿箱...")

def calc_layout(para_count, img_count=5):
    """计算图片布局 {1:1, 3:2, 5:2}"""
    if para_count < 1:
        return {}
    n_groups = (img_count - 1) // 2
    if n_groups <= 0:
        return {1: 1} if img_count >= 1 else {}
    first = 1
    result = {1: 1}
    # 简单的均匀分布
    for g in range(1, n_groups + 1):
        pos = first + g * 2
        if pos < para_count:
            result[pos] = 2
    return result

for art_idx, art in enumerate(articles, 1):
    print(f"\n[{art_idx}/{len(articles)}] {art['title']}")
    
    # 获取图片URL
    img_urls = all_image_urls.get(art_idx, [])
    print(f"  图片URL: {len(img_urls)}张")
    
    if len(img_urls) < 5:
        print(f"  ⚠ 图片不足5张，跳过")
        continue
    
    # 构建content HTML: 6段文字 + 5张图片按布局 {1:1, 3:2, 5:2}
    paragraphs = art["content"].split("\n\n")
    # 清理空段落
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    layout = {1: 1, 3: 2, 5: 2}
    content_html = ""
    img_idx = 0
    
    for p_idx, para in enumerate(paragraphs):
        content_html += f"<p>{para}</p>\n"
        para_num = p_idx + 1
        if para_num in layout:
            n_imgs = layout[para_num]
            for _ in range(n_imgs):
                if img_idx < len(img_urls):
                    content_html += f'<img src="{img_urls[img_idx]}" alt="图片来源于网络">\n<p style="text-align:center;font-size:12px;color:#999;">图片来源于网络</p>\n'
                    img_idx += 1
    
    print(f"  内容HTML: {len(content_html)}字符")
    
    # 封面图（前3张）
    covers = []
    for i in range(3):
        if i < len(img_urls):
            covers.append({
                "url": img_urls[i],
                "uri": img_urls[i].split("/")[-1].split("?")[0] if "?" in img_urls[i] else img_urls[i].split("/")[-1]
            })
    
    # 调用保存API
    ts = int(time.time() * 1000)
    save_url = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"
    
    form_data = {
        "source": "29",
        "extra": json.dumps({
            "content_source": "100000000402",
            "content_word_cnt": art["word_cnt"],
            "is_multi_title": 0,
            "sub_titles": [],
            "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
            "tuwen_wtt_transfer_switch": "1"
        }),
        "content": content_html,
        "title": art["title"],
        "search_creation_info": json.dumps({"searchTopOne": 0, "abstract": "", "clue_id": ""}),
        "title_id": f"{ts}_{ts * 1000}",
        "mp_editor_stat": "{}",
        "is_refute_rumor": "0",
        "save": "0",  # 保存为草稿
        "entrance": "",
        "timer_status": "0",
        "timer_time": "",
        "educluecard": "",
        "draft_form_data": json.dumps({"coverType": 3}),
        "pgc_feed_covers": json.dumps(covers),
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
        "stain_article": "0",
        "stain_article_type": "",
        "stain_article_id": "",
        "stain_article_title": "",
        "stain_article_reason": "",
        "stain_article_url": "",
        "link_show_type": "0",
        "related_article": "",
        "related_article_type": "",
        "is_short_content": "0",
        "short_content_type": "",
        "short_content_title": "",
        "short_content_video_id": "",
        "short_content_video_url": "",
        "short_content_video_cover": "",
        "short_content_video_duration": "",
        "short_content_video_width": "",
        "short_content_video_height": "",
    }
    
    try:
        resp = session.post(save_url, data=form_data, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://mp.toutiao.com",
            "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
            "Content-Type": "application/x-www-form-urlencoded",
        }, timeout=30)
        print(f"  保存响应: {resp.status_code}")
        result = resp.json()
        print(f"  结果: {json.dumps(result, ensure_ascii=False)[:300]}")
        if result.get("code") == 0:
            print(f"  ✓ 保存成功!")
        else:
            print(f"  ✗ 保存失败: {result.get('message', 'unknown')}")
    except Exception as e:
        print(f"  ✗ 保存异常: {e}")

print("\nDONE")