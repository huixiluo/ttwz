# -*- coding: utf-8 -*-
"""重建配图失败的第1、3篇文章：新访客会话+重试+百度兜底，重组manifest为1,2,3顺序"""
import os
import json
import time
import datetime
import hot_news_writer as hnw
from batch_generate import save_cover_images

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
IMAGE_COUNT = 5
# 百度兜底短词（微博话题搜不到时用）
BAIDU_KW = {
    "樊振东出席活动又帅出新高度": "樊振东",
    "张继科说我和那些人不在一个段位": "张继科 乒乓球",
}

with open(os.path.join(BASE_DIR, "_manual_articles.json"), "r", encoding="utf-8") as f:
    arts = json.load(f)

manifest_path = os.path.join(OUTPUT_DIR, "batch_manifest.json")
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)  # 目前只有第2篇

print(f"现有manifest {len(manifest)} 篇：{[m['title'][:12] for m in manifest]}")

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

for idx in [0, 2]:  # 第1、3篇
    art = arts[idx]
    cat, keyword, title, article = art["category"], art["keyword"], art["title"], art["article"]
    title = hnw.clean_erhua(title)
    article = hnw.clean_erhua(article)
    print()
    print("=" * 60)
    print(f"[{idx+1}/3] [{cat}] {keyword}")
    print(f"  标题：{title}（{len(title)}字）  正文：{len(article)}字")

    images = []
    source = ""
    # 尝试两轮：每轮新会话
    for attempt in range(1, 3):
        print(f"  [尝试{attempt}] 新访客session...")
        try:
            session = hnw.get_visitor_session()
        except Exception as e:
            print(f"    session失败: {e}")
            time.sleep(5)
            continue
        imgs = hnw.fetch_images_from_weibo(session, keyword, count=IMAGE_COUNT)
        print(f"    微博话题图: {len(imgs)}张")
        if imgs:
            images = imgs
            source = f"微博原帖({len(imgs)})"
            break
        time.sleep(8)
    # 百度兜底
    if len(images) < 3:
        bkw = BAIDU_KW.get(keyword, keyword)
        print(f"  [百度兜底] 关键词: {bkw}")
        try:
            fb = hnw.fetch_images_baidu(bkw, count=IMAGE_COUNT)
            print(f"    百度图: {len(fb)}张")
            if fb:
                images = fb
                source = f"百度({len(fb)})"
        except Exception as e:
            print(f"    百度失败: {e}")
    # 微博关键词兜底（不带##）
    if len(images) < 3:
        print("  [微博关键词兜底]")
        try:
            session = hnw.get_visitor_session()
            imgs = hnw.fetch_images_from_weibo(session, BAIDU_KW.get(keyword, keyword), count=IMAGE_COUNT)
            print(f"    微博关键词图: {len(imgs)}张")
            if imgs:
                images = imgs
                source = f"微博关键词({len(imgs)})"
        except Exception as e:
            print(f"    失败: {e}")

    print(f"  最终配图：{len(images)}张（{source}）")
    assert len(images) >= 3, f"配图不足3张: {keyword}"
    images = images[:IMAGE_COUNT]

    html = hnw.build_html(title, article, images)
    prefix = f"{cat}_{idx+1}_{timestamp}"
    filepath = os.path.join(OUTPUT_DIR, f"hot_{prefix}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已保存：{filepath}")
    cover_paths = save_cover_images(images, OUTPUT_DIR, prefix)
    print(f"  封面图：{len(cover_paths)}张")

    manifest.append({
        "category": cat,
        "keyword": keyword,
        "title": title,
        "article": article,
        "html_file": filepath,
        "cover_files": cover_paths,
        "word_count": len(article),
        "image_count": len(images),
        "image_source": source,
    })
    time.sleep(2)

# 按 _manual_articles.json 顺序重排manifest（1,2,3）
order = {a["keyword"]: i for i, a in enumerate(arts)}
manifest.sort(key=lambda m: order.get(m["keyword"], 99))
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print()
print("=" * 60)
print(f"manifest重组完成（{len(manifest)}篇）：")
for m in manifest:
    print(f"  {m['title']}（{m['word_count']}字, {m['image_count']}图, {m['image_source']}）")
