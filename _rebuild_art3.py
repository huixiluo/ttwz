# -*- coding: utf-8 -*-
"""重建第3篇文章：使用打磨后正文 + 补足第5张配图（关联话题），更新HTML/封面/manifest"""
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
art = arts[2]  # 第3篇：张继科
cat, keyword, title, article = art["category"], art["keyword"], art["title"], art["article"]

title = hnw.clean_erhua(title)
article = hnw.clean_erhua(article)
print(f"[3/3] [{cat}] {keyword}")
print(f"  标题：{title}（{len(title)}字）")
print(f"  正文：{len(article)}字（打磨后）")
assert hnw._is_three_part_title(title), "标题非三段式"
assert len(article) > 600, "正文未超过600字"

session = hnw.get_visitor_session()

# 配图：主话题原帖 + 关联话题补足 + 百度兜底
print("  获取配图（目标5张）...")
images = hnw.fetch_images_from_weibo(session, keyword, count=IMAGE_COUNT)
source = f"微博原帖({len(images)})"
if len(images) < IMAGE_COUNT:
    remaining = IMAGE_COUNT - len(images)
    extra = hnw.fetch_images_from_weibo(session, "张继科回应刘丁硕段位不够", count=remaining)
    images.extend(extra)
    source = f"微博原帖({len(images)})"
    if len(images) < IMAGE_COUNT:
        remaining = IMAGE_COUNT - len(images)
        fb = hnw.fetch_images_baidu("张继科", count=remaining)
        images.extend(fb)
        if fb:
            source += f" + 百度({len(fb)})"
print(f"  配图：{len(images)}张（{source}）")
assert len(images) >= 3, "配图不足3张"
if len(images) > IMAGE_COUNT:
    images = images[:IMAGE_COUNT]

html = hnw.build_html(title, article, images)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
prefix = f"{cat}_3_{timestamp}"
filename = f"hot_{prefix}.html"
filepath = os.path.join(OUTPUT_DIR, filename)
with open(filepath, "w", encoding="utf-8") as f:
    f.write(html)
print(f"  已保存：{filepath}")

cover_paths = save_cover_images(images, OUTPUT_DIR, prefix)
print(f"  封面图：{len(cover_paths)}张已保存到 covers/")

# 更新manifest第3篇
manifest_path = os.path.join(OUTPUT_DIR, "batch_manifest.json")
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)
manifest[2] = {
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
print("\nmanifest第3篇已更新")

# 删除旧的第3篇HTML（已被新文件替代）
old = "/workspace/output/hot_体育_3_20261017_005532.html"
if os.path.exists(old) and os.path.abspath(old) != os.path.abspath(filepath):
    os.remove(old)
    print(f"旧文件已删除：{old}")
