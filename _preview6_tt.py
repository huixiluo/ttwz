# -*- coding: utf-8 -*-
"""预览6条：获取今日头条热榜并按分类展示6条资讯（2娱乐+2体育+2社会），跳过上次已用"""
import json
import toutiao_hot_writer as ttw

LAST_USED = set()

print("=" * 60)
print("获取今日头条热榜（6条版：2娱乐+2体育+2社会）...")
print("=" * 60)

session = ttw.get_tt_session()
hot_list = ttw.get_toutiao_hot_board(session)
print(f"  热榜共获取 {len(hot_list)} 条")

categories = ["娱乐", "体育", "社会"]
per_category = 2
used_titles = set(LAST_USED)
preview = {}

for cat in categories:
    all_cat_items = [h for h in hot_list if ttw.classify_tt_topic(h) == cat]
    candidates = [h for h in all_cat_items if h["word"] not in used_titles]
    selected = candidates[:per_category]
    if len(selected) < per_category:
        remaining = per_category - len(selected)
        global_pool = [h for h in hot_list if h["word"] not in used_titles and h["word"] not in {s["word"] for s in selected}]
        selected.extend(global_pool[:remaining])
    preview[cat] = selected
    for h in selected:
        used_titles.add(h["word"])
    print(f"  [{cat}] 已选 {len(selected)} 条")

print()
print("=" * 60)
print("已选6条资讯（待确认）")
print("=" * 60)
idx = 0
for cat in categories:
    print(f"\n【{cat}】板块")
    print("-" * 40)
    for h in preview[cat]:
        idx += 1
        num_str = f"热度{h.get('num', 0)}" if h.get("num") else f"排名{h.get('rank', idx)}"
        print(f"  {idx}. [{cat}] {h['title']}（{num_str}）")

with open("_preview_tt_result.json", "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)
print(f"\n共 {idx} 条资讯，已保存到 _preview_tt_result.json")
