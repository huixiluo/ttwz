# -*- coding: utf-8 -*-
"""获取3条热门资讯(1娱乐+1体育+1社会)并抓取微博原帖文字素材"""
import os
import json
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
    "白海豚已闭眼", "小心这种手机壳正在偷拍你的隐私",
    "富婆带资进组硬加60多场吻戏", "松岛辉空4比3张禹珍", "名创优品一次性内裤颜面尽失",
    "阿根廷队长父亲去世", "王橹杰 张元英", "茜拉自曝父亲出轨自己闺蜜",
    "田曦薇化的妆被质疑", "曼联vs巴黎圣日耳曼", "韩乔生谈阿根廷队长父亲去世",
    "阿森纳官宣吉马良斯加盟", "女孩遭性侵被不雅视频威胁多次轻生",
    "柬埔寨一园区围殴中国人致1死3伤", "河南三支一扶成绩全部作废公平吗",
    "陈思诚在家里气哭了", "瑞典大满贯 男单32强", "泰国 电诈园区",
    "白海豚突然大拐弯", "以后救市别求沈腾王宝强了",
    "暑期档 撤档", "白鹿柳智敏 蛇塑",
    "张本智和说面对国乒年轻选手压力消失了", "陈幸同4比0大藤沙月",
    "张睿一看手机天又塌了", "王俊凯王源TOP张峻豪TF四代同时演出",
    "曝谷爱凌LV三公子恋情", "王楚钦兼项引争议",
    "打赏要求陪睡男子为9家企业法人", "女儿产后自杀母亲回应被指重男轻女",
    "王俊凯口误了", "丁程鑫从不遮掩自己农村家庭背景",
    "C罗乔治娜婚礼合照", "谷爱凌否认恋情",
    "19岁男子还债300万后去世", "市民打12345投诉月光太亮影响睡觉",
    "披荆斩棘排名", "吴艳妮13秒12夺冠", "女主播希望停止榜一大哥病态折磨",
}

print("=" * 60)
print("获取资讯选题（优先创作罐头低粉爆款，回退微博分类热搜），跳过上次已用...")
print("=" * 60)

session = hnw.get_visitor_session()

categories = ["娱乐", "体育", "社会"]
per_category = 1
used_titles = set(LAST_USED)
preview = {}

# 来源1（优先）: 创作罐头低粉爆款（今日头条/文章/粉丝<1万/阅读量降序）
source_name = "创作罐头·低粉爆款"
try:
    import czgts_source
    czgts_lists = czgts_source.fetch_czgts_low_fans(categories)
    for cat in categories:
        candidates = [a for a in czgts_lists.get(cat, [])
                      if a["word"] not in used_titles and a["title"] not in used_titles]
        selected = candidates[:per_category]
        if not selected:
            raise RuntimeError(f"[{cat}] 无可用低粉爆款选题")
        preview[cat] = selected
        for h in selected:
            used_titles.add(h["word"])
    print(f"  选题来源: {source_name}")
except Exception as e:
    print(f"  创作罐头失败({str(e)[:100]})，回退微博热搜")
    source_name = "微博分类热搜"
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
print("已选资讯列表")
print("=" * 60)
idx = 0
items = []
for cat in categories:
    print(f"\n【{cat}】板块")
    print("-" * 40)
    for h in preview[cat]:
        idx += 1
        if h.get("source") == "czgts":
            print(f"  {idx}. [{cat}] {h['title'][:40]}（阅读{h['num']} 粉丝{h['fans']} 来源:低粉爆款第{h['rank']}）")
        else:
            print(f"  {idx}. [{cat}] {h['title']}（热搜排名{h['rank']}）")
        items.append((cat, h))

# 保存预览结果
with open("_preview_result.json", "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)
print(f"\n共 {idx} 条资讯，已保存预览结果到 _preview_result.json")

# 抓取微博原帖文字素材
print("\n" + "=" * 60)
print("开始抓取微博原帖文字素材...")
print("=" * 60)

all_posts = {}
for i, (cat, item) in enumerate(items):
    keyword = item["word"]
    print(f"\n[{i+1}/{len(items)}] [{cat}] 抓取原帖：{keyword}")
    posts = hnw.fetch_weibo_posts_text(session, keyword, count=8)
    print(f"  抓取到 {len(posts)} 条原帖")
    all_posts[keyword] = {
        "category": cat,
        "rank": item.get("rank", i + 1),
        "title": item["title"],
        "word": keyword,
        "posts": posts,
    }
    for j, p in enumerate(posts[:3], 1):
        print(f"  帖{j} | {p['user']}: {p['text'][:80]}...")

# 保存原帖素材
output_path = os.path.join(BASE_DIR, "_weibo_posts_raw.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(all_posts, f, ensure_ascii=False, indent=2)
print(f"\n原帖素材已保存：{output_path}")
print(f"共 {len(all_posts)} 个话题")
