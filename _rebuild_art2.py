# -*- coding: utf-8 -*-
"""重建第2篇文章：使用打磨后正文重新生成HTML/封面，更新manifest"""
import os
import json
import datetime
import hot_news_writer as hnw
from batch_generate import save_cover_images

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
IMAGE_COUNT = 5

with open(os.path.join(BASE_DIR, "_manual_articles.json"), "r", encoding="utf-8") as f:
    arts = json.load(f)
art = arts[1]  # 第2篇：河北卫视/孙颖莎
cat, keyword, title, article = art["category"], art["keyword"], art["title"], art["article"]

title = hnw.clean_erhua(title)
article = hnw.clean_erhua(article)
print(f"[2/3] [{cat}] {keyword}")
print(f"  标题：{title}（{len(title)}字）  正文：{len(article)}字（打磨后）")
assert hnw._is_three_part_title(title) and len(article) > 600

session = hnw.get_visitor_session()
print("  获取配图（目标5张）...")
images = hnw.fetch_images_from_weibo(session, keyword, count=IMAGE_COUNT)
source = f"微博原帖({len(images)})"
if len(images) < IMAGE_COUNT:
    remaining = IMAGE_COUNT - len(images)
    extra = hnw.fetch_images_from_weibo(session, "孙颖莎省运会收视率第一", count=remaining)
    images.extend(extra)
    source = f"微博原帖({len(images)})"
    if len(images) < IMAGE_COUNT:
        remaining = IMAGE_COUNT - len(images)
        fb = hnw.fetch_images_baidu("孙颖莎 火炬手", count=remaining)
        images.extend(fb)
        if fb:
            source += f" + 百度({len(fb)})"
print(f"  配图：{len(images)}张（{source}）")
assert len(images) >= 3
if len(images) > IMAGE_COUNT:
    images = images[:IMAGE_COUNT]

html = hnw.build_html(title, article, images)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
prefix = f"{cat}_2_{timestamp}"
filepath = os.path.join(OUTPUT_DIR, f"hot_{prefix}.html")
with open(filepath, "w", encoding="utf-8") as f:
    f.write(html)
print(f"  已保存：{filepath}")

cover_paths = save_cover_images(images, OUTPUT_DIR, prefix)
print(f"  封面图：{len(cover_paths)}张已保存到 covers/")

manifest_path = os.path.join(OUTPUT_DIR, "batch_manifest.json")
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)
manifest[1] = {
    "category": cat,
    "keyword": keyword,
    "title": title,
    "article": article,
    "html_file": filepath,
    "cover_files": cover_paths,
    "word_count": len(article),
    "image_count": len(images),
    "image_source": source,
}
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
print("manifest第2篇已更新")

# 删除被替代的旧HTML
old = "/workspace/output/hot_体育_2_20261017_005532.html"
if os.path.exists(old) and os.path.abspath(old) != os.path.abspath(filepath):
    os.remove(old)
    print(f"旧文件已删除：{old}")
