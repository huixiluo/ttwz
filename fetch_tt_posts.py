# -*- coding: utf-8 -*-
"""批量抓取话题的今日头条文章/热评文字素材，保存为JSON供改写参考"""
import os
import json
import toutiao_hot_writer as ttw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    preview_path = os.path.join(BASE_DIR, "_preview_tt_result.json")
    with open(preview_path, "r", encoding="utf-8") as f:
        preview = json.load(f)

    items = []
    for cat in ["娱乐", "体育", "社会"]:
        for h in preview.get(cat, []):
            items.append((cat, h))

    print("获取头条HTTP session...")
    session = ttw.get_tt_session()
    print("  OK")

    all_posts = {}
    for i, (cat, item) in enumerate(items):
        keyword = item["word"]
        topic_url = item.get("url", "")
        print(f"\n[{i+1}/{len(items)}] [{cat}] 抓取头条话题文本：{keyword}")
        posts = ttw.fetch_toutiao_posts_text(
            session, keyword, topic_url=topic_url, count=8
        )
        print(f"  抓取到 {len(posts)} 条文本片段")
        all_posts[keyword] = {
            "category": cat,
            "rank": item.get("rank", i + 1),
            "url": topic_url,
            "posts": posts,
        }
        for j, p in enumerate(posts[:3], 1):
            print(f"  片段{j} | {p['user']}: {p['text'][:80]}...")

    output_path = os.path.join(BASE_DIR, "_toutiao_posts_raw.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)
    print(f"\n头条话题文本素材已保存：{output_path}")
    print(f"共 {len(all_posts)} 个话题")


if __name__ == "__main__":
    main()
