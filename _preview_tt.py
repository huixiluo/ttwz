# -*- coding: utf-8 -*-
"""预览：获取今日头条热榜并按分类展示9条资讯（3娱乐+3体育+3社会），跳过上次已用，不生成文章。
列出后暂停等待用户确认，确认后才保存 _preview_tt_result.json 供下游使用。"""
import json
import toutiao_hot_writer as ttw

# 上次已用话题（避免重复，按需扩充）
LAST_USED = set()

print("=" * 60)
print("获取今日头条热榜并按关键词规则分类（娱乐/体育/社会），跳过上次已用...")
print("=" * 60)

session = ttw.get_tt_session()
hot_list = ttw.get_toutiao_hot_board(session)
print(f"  热榜共获取 {len(hot_list)} 条")

categories = ["娱乐", "体育", "社会"]
per_category = 3
used_titles = set(LAST_USED)  # 跨类别去重
preview = {}

for cat in categories:
    # 按 classify_tt_topic 分类后取排名前per_category条
    all_cat_items = [h for h in hot_list if ttw.classify_tt_topic(h) == cat]
    candidates = [h for h in all_cat_items if h["word"] not in used_titles]
    selected = candidates[:per_category]
    # 若某分类不足，从整体未用中兜底补足
    if len(selected) < per_category:
        remaining = per_category - len(selected)
        global_pool = [h for h in hot_list if h["word"] not in used_titles and h["word"] not in {s["word"] for s in selected}]
        selected.extend(global_pool[:remaining])
    preview[cat] = selected
    for h in selected:
        used_titles.add(h["word"])
    print(f"  [{cat}] 分类匹配 {len(all_cat_items)} 条，已选 {len(selected)} 条")

# 展示
print()
print("=" * 60)
print("已选资讯列表（待确认）")
print("=" * 60)
idx = 0
for cat in categories:
    print(f"\n【{cat}】板块")
    print("-" * 40)
    for h in preview[cat]:
        idx += 1
        num_str = f"热度{h.get('num', 0)}" if h.get("num") else f"排名{h.get('rank', idx)}"
        print(f"  {idx}. [{cat}] {h['title']}（{num_str}）")

print()
print("=" * 60)
print("⚠ 以上为待确认资讯列表，尚未保存。")
print("请检查后回复：")
print("  - 确认无误 → 回复 确认 ，将保存到 _preview_tt_result.json 并继续后续步骤")
print("  - 需要调整 → 回复如 去掉第3条 / 第2条改成体育 / 换一批")
print("  - 取消     → 回复 取消")
print("=" * 60)

# 交互式确认
while True:
    user_input = input("\n请确认 >>> ").strip()
    if user_input in ("确认", "确定", "ok", "OK", "y", "Y", "继续"):
        with open("_preview_tt_result.json", "w", encoding="utf-8") as f:
            json.dump(preview, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已确认，共 {idx} 条资讯，已保存到 _preview_tt_result.json")
        print("可继续运行 fetch_tt_posts.py / generate_9_tt.py / batch_generate_tt.py")
        break
    elif user_input in ("取消", "退出", "cancel", "q", "Q", "n", "N"):
        print("\n❌ 已取消，不保存结果。")
        break
    else:
        print("  收到反馈，请手动编辑脚本中的 LAST_USED 或调整分类后重新运行。")
        print("  （如需删除/调整特定条目，请直接告知，重新运行 _preview_tt.py）")
        # 仍然保存当前结果作为参考，但提示未最终确认
        with open("_preview_tt_result_draft.json", "w", encoding="utf-8") as f:
            json.dump(preview, f, ensure_ascii=False, indent=2)
        print("  草稿已保存到 _preview_tt_result_draft.json（非最终版）")
        break
