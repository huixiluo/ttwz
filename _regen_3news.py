# -*- coding: utf-8 -*-
"""用新图片布局逻辑重新生成3篇HTML（文章数据来自_articles_data，图片重新获取）"""
import os
import sys
import json
import time
import base64

import hot_news_writer as hnw
from _articles_data import ARTICLES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
COVER_DIR = os.path.join(OUTPUT_DIR, "covers")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(COVER_DIR, exist_ok=True)

IMAGE_COUNT = 5


def save_cover_images(images_b64, prefix):
    """从配图中选3张保存为封面图"""
    paths = []
    for i, b64 in enumerate(images_b64[:3]):
        img_bytes = base64.b64decode(b64)
        fp = os.path.join(COVER_DIR, f"{prefix}_cover_{i+1}.jpg")
        with open(fp, "wb") as f:
            f.write(img_bytes)
        paths.append(fp)
    return paths


print("=" * 60)
print("用新布局逻辑重新生成3篇HTML")
print("=" * 60)

session = hnw.get_visitor_session()
results = []

for i, art in enumerate(ARTICLES, 1):
    cat = art["category"]
    keyword = art["keyword"]
    title = art["title"]
    article = art["article"]

    print(f"\n[{i}/{len(ARTICLES)}] [{cat}] {keyword}")
    print(f"  标题: {title} ({len(title)}字)")
    print(f"  正文: {len(article)}字, {len([p for p in article.split(chr(10)) if p.strip()])}段")

    print("  [1/3] 获取配图（优先微博原帖，回退百度）...")
    images = hnw.fetch_images_from_weibo(session, keyword, count=IMAGE_COUNT)
    source = "微博原帖"
    if len(images) < IMAGE_COUNT:
        remaining = IMAGE_COUNT - len(images)
        fallback = hnw.fetch_images_baidu(keyword, count=remaining)
        images.extend(fallback)
        if fallback:
            source = f"微博({len(images)-len(fallback)})+百度({len(fallback)})"
    print(f"  配图: {len(images)}张（{source}）")

    print("  [2/3] 生成HTML（新动态布局）...")
    html = hnw.build_html(title, article, images)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    prefix = f"new_{cat}_{i}_{timestamp}"
    html_path = os.path.join(OUTPUT_DIR, f"hot_{prefix}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML: {html_path}")

    cover_paths = save_cover_images(images, prefix)
    print(f"  封面: {len(cover_paths)}张已保存")

    # 诊断布局
    para_count = len([p for p in article.split("\n") if p.strip()])
    layout = hnw._calc_image_layout(para_count, len(images))
    last_pic = max(layout.keys()) if layout else 0
    tail = para_count - last_pic
    print(f"  布局诊断: {para_count}段 → {layout}, 共{sum(layout.values())}张图, 结尾纯文字{tail}段")

    results.append({
        "category": cat,
        "keyword": keyword,
        "title": title,
        "article": article,
        "html_file": html_path,
        "cover_files": cover_paths,
    })
    time.sleep(2)

# 生成batch_manifest
manifest_path = os.path.join(OUTPUT_DIR, "batch_manifest.json")
manifest = []
for r in results:
    manifest.append({
        "category": r["category"],
        "keyword": r["keyword"],
        "title": r["title"],
        "article": r["article"],
        "html_file": r["html_file"],
        "cover_files": r["cover_files"],
    })
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 60)
print(f"重新生成完成！共 {len(results)} 篇")
print(f"清单: {manifest_path}")
print("=" * 60)
