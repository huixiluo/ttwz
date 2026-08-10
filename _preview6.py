# -*- coding: utf-8 -*-
"""预览6条资讯（2娱乐+2体育+2社会），跳过已用"""
import json
import hot_news_writer as hnw

LAST_USED = {
    "胡彦斌歌王", "金智秀发文道歉", "歌手排名",
    "国乒男单 梯队建设", "湖人 詹姆斯", "湖人官方宣传被指除名詹眉",
    "一个没有空调外挂机的城市", "黄金", "中山大学23岁直博生确诊胃癌晚期",
    "西村力大吧发长文回应", "西村力 Mina", "苍兰诀",
    "韩国足协7场比赛性贿赂20名裁判", "罗德里加盟皇马几乎告吹", "U17国足三战全胜",
    "Mina轻生前求西村力粉丝别网暴自己", "日本女网红自杀更多细节曝光", "租房柜中发现遗像租客吓哭连夜搬离",
    "周杰伦疑似回应私生子", "TFBOYS发文祝出道十三周年快乐",
    "王艺迪3比1伊藤美诚", "王艺迪 止藤片",
    "戴手链美甲给宝宝打针护士已停职", "李亚鹏向地铁吐血女孩捐99999元",
}

session = hnw.get_visitor_session()
categories = ["娱乐", "体育", "社会"]
per_category = 2
used_titles = set(LAST_USED)
preview = {}

print("=" * 60)
print("获取微博分类热搜（跳过已用）...")
print("=" * 60)
for cat in categories:
    hot_list = hnw.get_hotsearch_by_category(session, cat)
    print(f"  [{cat}] 分类热搜共 {len(hot_list)} 条")
    candidates = [h for h in hot_list if h["word"] not in used_titles]
    selected = candidates[:per_category]
    preview[cat] = selected
    for h in selected:
        used_titles.add(h["word"])

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
        print(f"  {idx}. [{cat}] {h['title']}（热搜排名{h['rank']}，热度{h['num']}）")

with open("_preview_result.json", "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)
print(f"\n共 {idx} 条资讯，已保存到 _preview_result.json")
