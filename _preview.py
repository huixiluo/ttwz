# -*- coding: utf-8 -*-
"""预览：获取微博热搜并按分类展示6条资讯（2娱乐+2体育+2社会），跳过上次已用，不生成文章"""
import json
import hot_news_writer as hnw

# 上次已用话题（避免重复）
LAST_USED = {
    "周杰伦疑似回应私生子", "橹穆",
    "伊藤美诚 苍蝇拍打法", "吴梦洁伤愈回归女排",
    "梅姨真实姓名首曝光", "台风",
}

print("=" * 60)
print("获取微博分类热搜（文娱/体育/社会），跳过上次已用...")
print("=" * 60)

session = hnw.get_visitor_session()

categories = ["娱乐", "体育", "社会"]
per_category = 2
used_titles = set(LAST_USED)  # 跨类别去重，包含上次已用
preview = {}

for cat in categories:
    hot_list = hnw.get_hotsearch_by_category(session, cat)
    print(f"  [{cat}] 分类热搜共 {len(hot_list)} 条")
    candidates = [h for h in hot_list if h["word"] not in used_titles]
    selected = candidates[:per_category]
    preview[cat] = selected
    for h in selected:
        used_titles.add(h["word"])
print()

# 展示
print("=" * 60)
print("已选资讯列表（待确认）")
print("=" * 60)
idx = 0
for cat in categories:
    print(f"\n【{cat}】板块")
    print("-" * 40)
    for h in preview[cat]:
        idx += 1
        print(f"  {idx}. [{cat}] {h['title']}（热搜排名{h['rank']}）")

with open("_preview_result.json", "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)
print(f"\n共 {idx} 条资讯，已保存预览结果到 _preview_result.json")
