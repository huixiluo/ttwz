#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量生成9篇头条热榜文章（3娱乐+3体育+3社会）—— DeepSeek API 模式
每篇>600字，5张配图（优先头条话题页，回退百度），选3张作为封面图单独保存
用法：python batch_generate_tt.py
"""
import os
import io
import json
import base64
import time
from datetime import datetime

import toutiao_hot_writer as ttw


def save_cover_images(images_b64, output_dir, prefix):
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
    config = ttw.load_config()
    api_key = config["api_key"]
    model = config.get("model", "deepseek-chat")
    api_url = config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
    output_dir = os.path.join(ttw.BASE_DIR, config.get("output_dir", "./output"))
    image_count = 5
    os.makedirs(output_dir, exist_ok=True)

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise RuntimeError("请在 config.json 中填写API Key")

    print("=" * 60)
    print("批量生成9篇头条热榜文章（3娱乐+3体育+3社会）—— DeepSeek API 模式")
    print("=" * 60)

    print("\n[准备] 获取今日头条热榜...")
    session = ttw.get_tt_session()
    hot_list = ttw.get_toutiao_hot_board(session)
    print(f"  热榜共获取 {len(hot_list)} 条")

    categories = ["娱乐", "体育", "社会"]
    per_category = 3
    manifest = []
    used_titles = set()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for cat in categories:
        print(f"\n{'='*60}")
        print(f"开始处理【{cat}】类，共{per_category}篇")
        print("=" * 60)

        # 按分类取排名最高的per_category条（跳过已用）
        all_cat_items = [h for h in hot_list if ttw.classify_tt_topic(h) == cat and h["word"] not in used_titles]
        selected = all_cat_items[:per_category]
        if len(selected) < per_category:
            remaining = per_category - len(selected)
            global_pool = [h for h in hot_list if h["word"] not in used_titles and h not in selected]
            selected.extend(global_pool[:remaining])

        for idx, hot in enumerate(selected, 1):
            keyword = hot["word"]
            used_titles.add(keyword)
            rank = hot.get("rank", idx)
            topic_url = hot.get("url", "")
            topic_image = hot.get("image", "")
            print()
            print(f"  [{cat} {idx}/{per_category}] {keyword}（排名 {rank}）")

            # ---- 1. DeepSeek 改写 ----
            try:
                print(f"    DeepSeek改写...")
                title, article = ttw.rewrite_article(keyword, rank, api_key, model, api_url)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 402:
                    print(f"    [402] DeepSeek余额不足，自动切换为编辑兜底模式（请稍后补写/再试）")
                    continue
                raise
            print(f"    标题：{title}（{len(title)}字）")
            print(f"    正文：{len(article)}字")

            # ---- 2. 真人编辑润色 ----
            print(f"    真人编辑润色...")
            article = ttw.polish_article(article, api_key, model, api_url)
            print(f"    润色后：{len(article)}字")

            if not ttw._is_three_part_title(title):
                print(f"    [警告] 标题非三段式：{title}")
            if len(article) <= 600:
                print(f"    [警告] 正文未超过600字（当前{len(article)}字）")

            # ---- 3. 配图 ----
            print(f"    获取配图（目标{image_count}张，优先头条话题页）...")
            images = ttw.fetch_images_from_toutiao(
                session, keyword,
                topic_image_url=topic_image, topic_url=topic_url,
                count=image_count
            )
            source = "头条话题"
            if len(images) < image_count:
                remaining = image_count - len(images)
                fallback = ttw.fetch_images_baidu(keyword, count=remaining)
                images.extend(fallback)
                if fallback:
                    source = f"头条话题({len(images)-len(fallback)}) + 百度({len(fallback)})"
            print(f"    配图：{len(images)}张（{source}）")
            if len(images) < 3:
                print(f"    [警告] 配图不足3张，跳过此篇")
                continue

            # ---- 4. HTML + 封面 ----
            html = ttw.build_html(title, article, images)
            prefix = f"tt_{cat}_{idx}_{timestamp}"
            filename = f"tt_hot_{prefix}.html"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"    已保存HTML：{filepath}")

            cover_paths = save_cover_images(images, output_dir, prefix)
            print(f"    封面图：{len(cover_paths)}张")

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

    manifest_path = os.path.join(output_dir, "batch_manifest_tt.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print()
    print("=" * 60)
    print(f"生成完成！共 {len(manifest)} 篇，manifest已保存：{manifest_path}")
    print("=" * 60)
    for m in manifest:
        print(f"  {m['category']} | {m['title']}（{m['word_count']}字, {m['image_count']}图）")


if __name__ == "__main__":
    import requests  # 供 402 异常捕获使用
    batch_generate()
