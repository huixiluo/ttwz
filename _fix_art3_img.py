# -*- coding: utf-8 -*-
"""第3篇补足第5张配图：解析现有HTML的4张图 + 新抓1张，重建HTML/封面/manifest"""
import os
import re
import json
import time
import datetime
import hot_news_writer as hnw
from batch_generate import save_cover_images

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
MANIFEST = os.path.join(OUTPUT_DIR, "batch_manifest.json")

with open(MANIFEST, "r", encoding="utf-8") as f:
    manifest = json.load(f)
art = manifest[2]
assert "张继科" in art["keyword"], "第3篇应为张继科话题"
title, article, old_html = art["title"], art["article"], art["html_file"]

# 从现有HTML提取base64图片（保持顺序）
with open(old_html, "r", encoding="utf-8") as f:
    html = f.read()
images = re.findall(r'<img src="data:image/jpeg;base64,([^"]+)"', html)
print(f"现有配图 {len(images)} 张")
assert len(images) == 4

# 补1张：关联话题 -> 百度
session = hnw.get_visitor_session()
extra = hnw.fetch_images_from_weibo(session, "张继科回应刘丁硕段位不够", count=2)
source = art["image_source"]
if extra:
    images.append(extra[0])
    source = source + " + 关联话题(1)"
    print("关联话题补图: 1张")
else:
    fb = hnw.fetch_images_baidu("张继科 乒乓球", count=1)
    if fb:
        images.append(fb[0])
        source = source + " + 百度(1)"
        print("百度补图: 1张")
assert len(images) >= 5, f"补图失败，仍{len(images)}张"
images = images[:5]

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
prefix = f"体育_3_{timestamp}"
new_html = hnw.build_html(title, article, images)
filepath = os.path.join(OUTPUT_DIR, f"hot_{prefix}.html")
with open(filepath, "w", encoding="utf-8") as f:
    f.write(new_html)
cover_paths = save_cover_images(images, OUTPUT_DIR, prefix)

manifest[2].update({
    "html_file": filepath,
    "cover_files": cover_paths,
    "image_count": len(images),
    "image_source": source,
})
with open(MANIFEST, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

# 删旧HTML
if os.path.exists(old_html) and os.path.abspath(old_html) != os.path.abspath(filepath):
    os.remove(old_html)

print(f"第3篇已重建：{len(images)}图 -> {filepath}")
for i, m in enumerate(manifest, 1):
    print(f"  {i}. {m['title']}（{m['word_count']}字, {m['image_count']}图）")
