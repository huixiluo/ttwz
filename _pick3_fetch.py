# -*- coding: utf-8 -*-
"""筛选用户选定的3条体育资讯（第2、4、12条），生成预览结果并抓取微博原帖素材"""
import json
import hot_news_writer as hnw

# 用户选择的序号（对应 _sports15.json 中的顺序）
PICKS = [2, 4, 12]

with open("_sports15.json", "r", encoding="utf-8") as f:
    data = json.load(f)

hot_list = data["体育"]
selected = [hot_list[i - 1] for i in PICKS]

# 保存预览结果（供 fetch_weibo_posts 等后续流程使用）
preview = {"体育": selected}
with open("_preview_result.json", "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)

print("已选话题：")
for h in selected:
    print(f"  - {h['title']}（热搜排名{h['rank']}）")

# 抓取微博原帖素材
print("\n获取微博访客session...")
session = hnw.get_visitor_session()
print("  OK")

all_posts = {}
for i, item in enumerate(selected):
    keyword = item["word"]
    print(f"\n[{i+1}/{len(selected)}] [体育] 抓取原帖：{keyword}")
    posts = hnw.fetch_weibo_posts_text(session, keyword, count=8)
    print(f"  抓取到 {len(posts)} 条原帖")
    all_posts[keyword] = {
        "category": "体育",
        "rank": item.get("rank", i + 1),
        "posts": posts,
    }
    for j, p in enumerate(posts[:3], 1):
        print(f"  帖{j} | {p['user']}: {p['text'][:80]}...")

with open("_weibo_posts_raw.json", "w", encoding="utf-8") as f:
    json.dump(all_posts, f, ensure_ascii=False, indent=2)
print(f"\n原帖素材已保存：_weibo_posts_raw.json（共 {len(all_posts)} 个话题）")
