# -*- coding: utf-8 -*-
"""预览：获取微博热搜并按分类展示9条资讯（3娱乐+3体育+3社会），跳过上次已用，不生成文章"""
import json
import hot_news_writer as hnw

# 上次已用话题（避免重复）
LAST_USED = {
    "周杰伦疑似回应私生子", "橹穆",
    "伊藤美诚 苍蝇拍打法", "吴梦洁伤愈回归女排",
    "梅姨真实姓名首曝光", "台风",
    "TFBOYS发文祝出道十三周年快乐", "周杰伦 私生子",
    "王艺迪3比1伊藤美诚", "王艺迪 止藤片",
    "戴手链美甲给宝宝打针护士已停职", "李亚鹏向地铁吐血女孩捐99999元",
    "西村力大吧发长文回应", "西村力 Mina", "苍兰诀",
    "Mina轻生前求西村力粉丝别网暴自己", "日本女网红自杀更多细节曝光",
    "租房柜中发现遗像租客吓哭连夜搬离",
    "韩国足协7场比赛性贿赂20名裁判", "罗德里加盟皇马几乎告吹", "U17国足三战全胜",
}

print("=" * 60)
print("获取微博分类热搜（文娱/体育/社会），跳过上次已用...")
print("=" * 60)

session = hnw.get_visitor_session()

categories = ["娱乐", "体育", "社会"]
per_category = 3
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
