# -*- coding: utf-8 -*-
"""获取微博体育榜热搜，取前15条，保存并展示"""
import json
import hot_news_writer as hnw

session = hnw.get_visitor_session()

print("正在获取微博体育榜...")
hot_list = hnw.get_hotsearch_by_category(session, "体育")
print(f"体育榜共 {len(hot_list)} 条（已过滤广告）\n")

selected = hot_list[:15]

# 展示
print("=" * 60)
print("微博体育榜 Top 15")
print("=" * 60)
for i, h in enumerate(selected, 1):
    print(f"  {i:>2}. {h['title']}（热搜排名{h['rank']}，热度{h.get('num', '')}）")

with open("_sports15.json", "w", encoding="utf-8") as f:
    json.dump({"体育": selected}, f, ensure_ascii=False, indent=2)
print(f"\n已保存 {len(selected)} 条到 _sports15.json")
