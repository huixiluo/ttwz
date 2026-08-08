# -*- coding: utf-8 -*-
"""批量生成9篇文章：读取预撰写内容+预览资讯，获取高清图片，生成HTML，保存batch_manifest.json
不使用DeepSeek API，文章内容由编辑直接撰写（已按真人校准标准，正文>600字）"""
import os
import json
import datetime
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    # 1. 读取预览资讯（按顺序：3娱乐+3体育+3社会）
    preview_path = os.path.join(BASE_DIR, "_preview_result.json")
    with open(preview_path, "r", encoding="utf-8") as f:
        preview = json.load(f)

    # 顺序排列9条资讯
    items = []
    for cat in ["娱乐", "体育", "社会"]:
        for h in preview.get(cat, []):
            items.append((cat, h))

    # 2. 读取预撰写文章内容
    articles_path = os.path.join(BASE_DIR, "articles_9.json")
    with open(articles_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    # 资讯word -> 文章key 映射（按顺序）
    keys = list(articles.keys())
    if len(keys) != len(items):
        print(f"警告：资讯数({len(items)})与文章数({len(keys)})不一致")

    # 3. 加载配置
    config = hnw.load_config()
    output_dir = os.path.join(BASE_DIR, config.get("output_dir", "./output"))
    image_count = config.get("image_count", 5)
    os.makedirs(output_dir, exist_ok=True)

    # 4. 获取访客session
    print("获取微博访客session...")
    session = hnw.get_visitor_session()
    print("  OK")

    manifest = []
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, (cat, item) in enumerate(items):
        keyword = item["word"]
        rank = item.get("rank", i + 1)
        key = keys[i] if i < len(keys) else keyword
        art = articles.get(key, {})
        title = hnw.clean_erhua(art.get("title", keyword))
        article = hnw.clean_erhua(art.get("article", ""))

        print()
        print("=" * 60)
        print(f"[{i+1}/9] [{cat}] {keyword}（排名{rank}）")
        print(f"  标题：{title}（{len(title)}字）")
        print(f"  正文：{len(article)}字")
        if not hnw._is_three_part_title(title):
            print(f"  [警告] 标题非三段式：{title}")

        if len(article) <= 600:
            print(f"  [警告] 正文未超过600字（当前{len(article)}字）")

        # 获取配图（优先微博原帖高清图，不足用百度补）
        print(f"  获取配图（目标{image_count}张，优先微博原帖）...")
        images = hnw.fetch_images_from_weibo(session, keyword, count=image_count)
        source = "微博原帖"
        if len(images) < image_count:
            remaining = image_count - len(images)
            fallback = hnw.fetch_images_baidu(keyword, count=remaining)
            images.extend(fallback)
            if fallback:
                source = f"微博原帖({len(images)-len(fallback)}) + 百度({len(fallback)})"
        print(f"  配图：{len(images)}张（{source}）")

        # 生成HTML
        html = hnw.build_html(title, article, images)
        filename = f"hot_{cat}_{i+1}_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  已保存：{filepath}")

        manifest.append({
            "title": title,
            "html_file": filepath,
            "cover_files": [],
            "category": cat,
            "keyword": keyword,
            "rank": rank,
            "word_count": len(article),
            "image_count": len(images),
            "image_source": source,
        })

    # 5. 保存manifest
    manifest_path = os.path.join(output_dir, "batch_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print()
    print("=" * 60)
    print(f"9篇文章生成完成，manifest已保存：{manifest_path}")
    print("=" * 60)
    for m in manifest:
        t = m["title"]
        print(f"  {m['category']} | {t}（{m['word_count']}字, {m['image_count']}图）")


if __name__ == "__main__":
    main()
