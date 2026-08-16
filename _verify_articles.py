# -*- coding: utf-8 -*-
"""验证文章：字数>600、三段式标题、无儿话音，然后生成HTML和配图"""
import os
import re
import json
import base64
import time
from datetime import datetime

import hot_news_writer as hnw
from _articles_data import ARTICLES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# 儿话音检查
ERHUA_WORDS = ["事儿", "点儿", "地儿", "哥们儿", "玩意儿", "劲儿", "味儿",
               "脸儿", "份儿", "调儿", "孩儿", "老头儿", "聊天儿", "慢慢儿",
               "好好儿", "哪儿", "这儿", "那儿", "一会儿", "一阵儿",
               "差点儿", "早点儿", "晚点儿", "快点儿", "慢点儿",
               "没事儿", "好玩儿"]

def check_erhua(text):
    """检查文本中是否包含儿话音"""
    found = []
    for w in ERHUA_WORDS:
        if w in text:
            found.append(w)
    # 正则检查其他"X儿"后缀
    matches = re.findall(r'[\u4e00-\u9fa5]儿(?!女|童|子|科|歌|时|媳|郎|孙)', text)
    if matches:
        found.extend(matches)
    return found

def count_chinese(text):
    """统计中文字符数"""
    return len(re.findall(r'[\u4e00-\u9fa5]', text))

def is_three_part_title(title):
    """检查是否为三段式标题（恰好两个逗号）"""
    comma_count = title.count('，') + title.count(',')
    return comma_count == 2

print("=" * 60)
print("验证6篇文章")
print("=" * 60)

for i, art in enumerate(ARTICLES, 1):
    title = art["title"]
    article = art["article"]

    # 标题检查
    title_ok = is_three_part_title(title)
    title_len = len(title)

    # 字数检查
    char_count = count_chinese(article)
    total_len = len(article)

    # 儿话音检查
    erhua_found = check_erhua(article)
    erhua_in_title = check_erhua(title)

    print(f"\n[{i}] {art['category']} - {art['keyword']}")
    print(f"  标题：{title}（{title_len}字，三段式：{'✓' if title_ok else '✗'}）")
    print(f"  正文中文字数：{char_count}（总字符数：{total_len}，>600：{'✓' if char_count > 600 else '✗'}）")
    if erhua_found:
        print(f"  ⚠ 正文发现儿话音：{erhua_found}")
    else:
        print(f"  儿话音检查：✓ 无")
    if erhua_in_title:
        print(f"  ⚠ 标题发现儿话音：{erhua_in_title}")

print("\n" + "=" * 60)
print("验证完成，开始生成配图和HTML...")
print("=" * 60)

# 获取微博访客session
print("\n获取微博访客session...")
session = hnw.get_visitor_session()
print("  OK")

results = []
for i, art in enumerate(ARTICLES, 1):
    keyword = art["keyword"]
    title = art["title"]
    article = art["article"]
    category = art["category"]

    print(f"\n[{i}/6] [{category}] 处理：{keyword}")

    # 获取配图（优先微博原帖，回退百度）
    print(f"  获取配图...")
    images = hnw.fetch_images_from_weibo(session, keyword, count=5)
    source = "微博原帖"
    if len(images) < 5:
        remaining = 5 - len(images)
        try:
            fallback = hnw.fetch_images_baidu(keyword, count=remaining)
            images.extend(fallback)
            if fallback:
                source = f"微博原帖({len(images)-len(fallback)}张) + 百度({len(fallback)}张)"
        except Exception as e:
            print(f"  百度图片回退失败：{e}，仅使用微博图片")
            fallback = []
    print(f"  成功处理 {len(images)} 张配图（来源：{source}）")

    # 清除儿话音（双保险）
    article = hnw.clean_erhua(article)
    title = hnw.clean_erhua(title)

    # 生成HTML
    html = hnw.build_html(title, article, images)

    # 保存HTML
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{category}_{i}_{timestamp}"
    html_filename = f"hot_{prefix}.html"
    html_filepath = os.path.join(OUTPUT_DIR, html_filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(html_filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML：{html_filepath}")

    # 保存封面图
    cover_dir = os.path.join(OUTPUT_DIR, "covers")
    os.makedirs(cover_dir, exist_ok=True)
    cover_paths = []
    for j, b64 in enumerate(images[:3]):
        img_bytes = base64.b64decode(b64)
        fname = f"{prefix}_cover_{j+1}.jpg"
        fpath = os.path.join(cover_dir, fname)
        with open(fpath, "wb") as f:
            f.write(img_bytes)
        cover_paths.append(fpath)
    print(f"  封面图：{len(cover_paths)} 张已保存")

    results.append({
        "category": category,
        "keyword": keyword,
        "title": title,
        "article": article,
        "html_file": html_filepath,
        "cover_files": cover_paths,
    })

    time.sleep(2)

# 保存batch_manifest.json
manifest_path = os.path.join(OUTPUT_DIR, "batch_manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n{'=' * 60}")
print(f"生成完成！共 {len(results)} 篇文章")
print(f"清单文件：{manifest_path}")
print(f"HTML目录：{OUTPUT_DIR}")
print("=" * 60)
