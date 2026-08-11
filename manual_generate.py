#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
手动文章配图+HTML生成脚本
读取 _manual_articles.json（已写好的标题+正文），调 hnw 抓配图、生成HTML、保存封面。
不调用任何LLM API，不需要 config.json。
用法：python manual_generate.py
"""
import os
import json
import time
from datetime import datetime

import hot_news_writer as hnw
from batch_generate import save_cover_images


def main():
    base_dir = hnw.BASE_DIR
    articles_path = os.path.join(base_dir, "_manual_articles.json")
    output_dir = os.path.join(base_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    with open(articles_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print("=" * 60)
    print(f"手动文章配图生成，共 {len(articles)} 篇（不调用LLM API）")
    print("=" * 60)

    print("\n[准备] 获取微博访客session（抓配图用）...")
    session = hnw.get_visitor_session()

    image_count = 5
    results = []

    for idx, art in enumerate(articles, 1):
        cat = art["category"]
        keyword = art["keyword"]
        title = art["title"]
        article = art["article"]
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(articles)}] [{cat}] {title}")
        print(f"  关键词：{keyword}")
        print(f"  正文：{len(article)} 字")

        print("  [1/3] 获取配图（优先微博原帖，回退百度）...")
        images = hnw.fetch_images_from_weibo(session, keyword, count=image_count)
        source = "微博原帖"
        if len(images) < image_count:
            remaining = image_count - len(images)
            fallback = hnw.fetch_images_baidu(keyword, count=remaining)
            images.extend(fallback)
            if fallback:
                source = f"微博原帖({len(images)-len(fallback)}张) + 百度({len(fallback)}张)"
        print(f"  成功处理 {len(images)} 张配图（来源：{source}）")
        if len(images) < 3:
            print(f"  [警告] 配图不足3张，跳过此篇")
            continue

        print("  [2/3] 生成HTML...")
        html = hnw.build_html(title, article, images)

        print("  [3/3] 保存文件...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"{cat}_{idx}_{timestamp}"
        html_filename = f"hot_{prefix}.html"
        html_filepath = os.path.join(output_dir, html_filename)
        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  HTML：{html_filepath}")

        cover_paths = save_cover_images(images, output_dir, prefix)
        print(f"  封面图：{len(cover_paths)} 张已保存到 covers/")

        results.append({
            "category": cat,
            "keyword": keyword,
            "title": title,
            "article": article,
            "html_file": html_filepath,
            "cover_files": cover_paths,
        })
        time.sleep(2)

    manifest_path = os.path.join(output_dir, "batch_manifest.json")
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

    print(f"\n{'='*60}")
    print(f"生成完成！共 {len(results)} 篇")
    print(f"清单：{manifest_path}")
    print(f"HTML目录：{output_dir}")
    print("=" * 60)
    return results


if __name__ == "__main__":
    main()
