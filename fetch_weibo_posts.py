# -*- coding: utf-8 -*-
"""批量抓取6个话题的微博原帖文字素材，保存为JSON供改写参考"""
import os
import json
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    preview_path = os.path.join(BASE_DIR, "_preview_result.json")
    with open(preview_path, "r", encoding="utf-8") as f:
        preview = json.load(f)

    items = []
    for cat in ["娱乐", "体育", "社会"]:
        for h in preview.get(cat, []):
            items.append((cat, h))

    print("获取微博访客session...")
    session = hnw.get_visitor_session()
    print("  OK")

    all_posts = {}
    for i, (cat, item) in enumerate(items):
        keyword = item["word"]
        print(f"\n[{i+1}/6] [{cat}] 抓取原帖：{keyword}")
        posts = hnw.fetch_weibo_posts_text(session, keyword, count=8)
        print(f"  抓取到 {len(posts)} 条原帖")
        all_posts[keyword] = {
            "category": cat,
            "rank": item.get("rank", i + 1),
            "posts": posts,
        }
        for j, p in enumerate(posts[:3], 1):
            print(f"  帖{j} | {p['user']}: {p['text'][:80]}...")

    output_path = os.path.join(BASE_DIR, "_weibo_posts_raw.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)
    print(f"\n原帖素材已保存：{output_path}")
    print(f"共 {len(all_posts)} 个话题")


if __name__ == "__main__":
    main()
