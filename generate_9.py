# -*- coding: utf-8 -*-
"""批量生成文章：读取预撰写内容，获取高清配图，生成HTML+封面，保存batch_manifest.json
不使用DeepSeek API，文章内容由编辑直接撰写（已按真人校准标准，正文>600字）。
支持两种文章源格式：
  - list格式：_manual_articles.json（自带category/keyword，推荐）
  - dict格式：articles_9.json（需配合_preview_result.json提供category）
不依赖config.json，output_dir/image_count有默认值。
用法：python generate_9.py
"""
import os
import json
import datetime
import hot_news_writer as hnw
from batch_generate import save_cover_images

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_articles():
    """加载预撰写文章，兼容list和dict两种格式。返回 [(category, keyword, title, article), ...]"""
    # 优先 list 格式（_manual_articles.json，自带category/keyword）
    list_path = os.path.join(BASE_DIR, "_manual_articles.json")
    if os.path.exists(list_path):
        with open(list_path, "r", encoding="utf-8") as f:
            arts = json.load(f)
        return [(a["category"], a["keyword"], a["title"], a["article"]) for a in arts]

    # 回退 dict 格式（articles_9.json + _preview_result.json）
    dict_path = os.path.join(BASE_DIR, "articles_9.json")
    preview_path = os.path.join(BASE_DIR, "_preview_result.json")
    if not (os.path.exists(dict_path) and os.path.exists(preview_path)):
        raise RuntimeError("未找到文章源：请提供 _manual_articles.json 或 articles_9.json+_preview_result.json")
    with open(dict_path, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(preview_path, "r", encoding="utf-8") as f:
        preview = json.load(f)
    items = []
    for cat in ["娱乐", "体育", "社会"]:
        for h in preview.get(cat, []):
            items.append((cat, h))
    keys = list(articles.keys())
    result = []
    for i, (cat, item) in enumerate(items):
        key = keys[i] if i < len(keys) else item["word"]
        art = articles.get(key, {})
        result.append((cat, item["word"], art.get("title", item["word"]), art.get("article", "")))
    return result


def main():
    # 1. 加载预撰写文章
    print("加载预撰写文章...")
    articles = load_articles()
    print(f"  共 {len(articles)} 篇")

    # 2. 配置（不依赖config.json，有默认值）
    output_dir = os.path.join(BASE_DIR, "output")
    image_count = 5
    os.makedirs(output_dir, exist_ok=True)

    # 3. 获取访客session
    print("获取微博访客session...")
    session = hnw.get_visitor_session()
    print("  OK")

    manifest = []
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, (cat, keyword, title, article) in enumerate(articles):
        # 清儿化音（双保险）
        title = hnw.clean_erhua(title)
        article = hnw.clean_erhua(article)

        print()
        print("=" * 60)
        print(f"[{i+1}/{len(articles)}] [{cat}] {keyword}")
        print(f"  标题：{title}（{len(title)}字）")
        print(f"  正文：{len(article)}字")
        if not hnw._is_three_part_title(title):
            print(f"  [警告] 标题非三段式：{title}")
        if len(article) <= 600:
            print(f"  [警告] 正文未超过600字（当前{len(article)}字）")

        # 获取配图（话题标签搜，优先微博原帖，不足用百度补）
        print(f"  获取配图（目标{image_count}张，优先微博话题原帖）...")
        images = hnw.fetch_images_from_weibo(session, keyword, count=image_count)
        source = "微博原帖"
        if len(images) < image_count:
            remaining = image_count - len(images)
            fallback = hnw.fetch_images_baidu(keyword, count=remaining)
            images.extend(fallback)
            if fallback:
                source = f"微博原帖({len(images)-len(fallback)}) + 百度({len(fallback)})"
        print(f"  配图：{len(images)}张（{source}）")
        if len(images) < 3:
            print(f"  [警告] 配图不足3张，跳过此篇")
            continue

        # 生成HTML
        html = hnw.build_html(title, article, images)
        prefix = f"{cat}_{i+1}_{timestamp}"
        filename = f"hot_{prefix}.html"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  已保存：{filepath}")

        # 保存封面（3张，取正文前3张去重图）
        cover_paths = save_cover_images(images, output_dir, prefix)
        print(f"  封面图：{len(cover_paths)}张已保存到 covers/")

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
        import time
        time.sleep(2)

    # 4. 保存manifest
    manifest_path = os.path.join(output_dir, "batch_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print()
    print("=" * 60)
    print(f"生成完成！共 {len(manifest)} 篇，manifest已保存：{manifest_path}")
    print("=" * 60)
    for m in manifest:
        print(f"  {m['category']} | {m['title']}（{m['word_count']}字, {m['image_count']}图）")


if __name__ == "__main__":
    main()
