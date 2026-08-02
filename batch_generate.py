#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量生成9篇文章（3娱乐+3体育+3社会）
每篇600-1000字，5张配图（优先微博原帖，回退百度），选3张作为封面图单独保存
用法：python batch_generate.py
"""

import os
import io
import json
import base64
import time
from datetime import datetime

import hot_news_writer as hnw


def save_cover_images(images_b64, output_dir, prefix):
    """从文章配图中选3张保存为封面图文件（JPEG）"""
    cover_dir = os.path.join(output_dir, "covers")
    os.makedirs(cover_dir, exist_ok=True)
    covers = images_b64[:3]
    saved_paths = []
    for i, b64 in enumerate(covers):
        img_bytes = base64.b64decode(b64)
        filename = f"{prefix}_cover_{i+1}.jpg"
        filepath = os.path.join(cover_dir, filename)
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        saved_paths.append(filepath)
    return saved_paths


def batch_generate():
    config = hnw.load_config()
    api_key = config["api_key"]
    model = config.get("model", "deepseek-chat")
    api_url = config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
    output_dir = os.path.join(hnw.BASE_DIR, config.get("output_dir", "./output"))
    image_count = 5
    os.makedirs(output_dir, exist_ok=True)

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise RuntimeError("请在 config.json 中填写API Key")

    print("=" * 60)
    print("批量生成6篇文章（2娱乐+2体育+2社会）")
    print("=" * 60)

    print("\n[准备] 获取微博分类热搜...")
    session = hnw.get_visitor_session()

    categories = ["娱乐", "体育", "社会"]
    per_category = 3
    results = []
    used_titles = set()  # 跨类别去重，确保9条热搜不重复

    for cat in categories:
        print(f"\n{'='*60}")
        print(f"开始处理【{cat}】类，共{per_category}篇")
        print("=" * 60)

        # 直接从微博分类热搜API获取该分类的热搜
        hot_list = hnw.get_hotsearch_by_category(session, cat)
        print(f"  [{cat}] 分类热搜共 {len(hot_list)} 条")
        # 排除已用的，按排名取前per_category条
        candidates = [h for h in hot_list if h["word"] not in used_titles]
        selected = candidates[:per_category]

        for idx, hot in enumerate(selected, 1):
            keyword = hot["word"]
            used_titles.add(keyword)  # 标记已用
            print(f"\n--- [{cat} {idx}/{per_category}] 热搜：{hot['title']}（排名{hot['rank']}）---")

            print("  [1/4] DeepSeek改写文章...")
            title, article = hnw.rewrite_article(
                keyword, hot["rank"], api_key, model, api_url
            )
            print(f"  标题：{title}（{len(title)}字）")
            print(f"  正文：共 {len(article)} 字")

            print("  [2/4] 获取配图（优先微博原帖素材，回退百度）...")
            images = hnw.fetch_images_from_weibo(session, keyword, count=image_count)
            source = "微博原帖"
            if len(images) < image_count:
                remaining = image_count - len(images)
                fallback = hnw.fetch_images_baidu(keyword, count=remaining)
                images.extend(fallback)
                if fallback:
                    source = f"微博原帖({len(images)-len(fallback)}张) + 百度({len(fallback)}张)"
            print(f"  成功处理 {len(images)} 张配图（来源：{source}）")

            print("  [3/4] 生成HTML...")
            html = hnw.build_html(title, article, images)

            print("  [4/4] 保存文件...")
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
    print(f"批量生成完成！共 {len(results)} 篇文章")
    print(f"清单文件：{manifest_path}")
    print(f"HTML目录：{output_dir}")
    print(f"封面图目录：{os.path.join(output_dir, 'covers')}")
    print("=" * 60)
    return results


if __name__ == "__main__":
    batch_generate()
