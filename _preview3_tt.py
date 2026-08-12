# -*- coding: utf-8 -*-
"""快速预览3条头条热榜（1娱乐+1体育+1社会），列出后等待确认"""
import json
import toutiao_hot_writer as ttw

print("=" * 60)
print("获取今日头条热榜，按关键词规则分类，每类取1条...")
print("=" * 60)

# 上一批已用话题，跳过避免重复
LAST_USED = {
    "网红峰哥炒股亏200万到回本只用1个月",
    "张雪机车车手德比斯开启中国行",
    "日全食将上演 最长持续约2分18秒",
}

session = ttw.get_tt_session()
hot_list = ttw.get_toutiao_hot_board(session)
print(f"  热榜共获取 {len(hot_list)} 条")

categories = ["娱乐", "体育", "社会"]
per_category = 1
preview = {}
# 用列表保存最终选中的话题，每条带真实分类
final_list = []
used_words = set(LAST_USED)

for cat in categories:
    all_cat_items = [h for h in hot_list if ttw.classify_tt_topic(h) == cat and h["word"] not in used_words]
    selected = all_cat_items[:per_category]
    if not selected:
        # 兜底：从未用过的整体热榜中取排名最高的
        pool = [h for h in hot_list if h["word"] not in used_words]
        selected = [pool[0]] if pool else []
    for h in selected:
        # 用话题的真实分类，而非当前循环的 cat 槽位
        real_cat = ttw.classify_tt_topic(h)
        h["category"] = real_cat
        used_words.add(h["word"])
        final_list.append(h)
    match_count = len(all_cat_items)
    if selected and ttw.classify_tt_topic(selected[0]) != cat:
        print(f"  [{cat}] 无匹配，兜底取 → {selected[0]['title']}（实际分类: {ttw.classify_tt_topic(selected[0])}）")
    else:
        print(f"  [{cat}] 分类匹配 {match_count} 条，已选 {len(selected)} 条")

# 展示
print()
print("=" * 60)
print("已选资讯列表（待确认）")
print("=" * 60)
idx = 0
for h in final_list:
    idx += 1
    cat = h["category"]
    num_str = f"热度{h.get('num', 0)}" if h.get('num') else f"排名{h.get('rank', idx)}"
    print(f"  {idx}. [{cat}] {h['title']}（{num_str}）")
    if h.get('url'):
        print(f"     链接: {h['url'][:80]}...")

# 按真实分类组织保存
preview = {}
for h in final_list:
    c = h["category"]
    preview.setdefault(c, []).append(h)

print()
print("=" * 60)
print(f"共 {idx} 条资讯，等待确认后保存。")
print("=" * 60)

# 保存结果
with open("_preview_tt_result.json", "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)
print(f"已保存到 _preview_tt_result.json")
