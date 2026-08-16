# -*- coding: utf-8 -*-
"""获取1条热门资讯并抓取微博原帖文字素材"""
import os, json
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LAST_USED = {
    "周杰伦疑似回应私生子", "橹穆", "伊藤美诚 苍蝇拍打法", "吴梦洁伤愈回归女排",
    "梅姨真实姓名首曝光", "台风", "TFBOYS发文祝出道十三周年快乐", "周杰伦 私生子",
    "王艺迪3比1伊藤美诚", "王艺迪 止藤片", "戴手链美甲给宝宝打针护士已停职",
    "李亚鹏向地铁吐血女孩捐99999元", "西村力大吧发长文回应", "西村力 Mina", "苍兰诀",
    "Mina轻生前求西村力粉丝别网暴自己", "日本女网红自杀更多细节曝光",
    "租房柜中发现遗像租客吓哭连夜搬离", "韩国足协7场比赛性贿赂20名裁判",
    "罗德里加盟皇马几乎告吹", "U17国足三战全胜", "暑期档 撤档", "白鹿柳智敏 蛇塑",
    "张本智和说面对国乒年轻选手压力消失了", "陈幸同4比0大藤沙月",
    "白海豚已闭眼", "小心这种手机壳正在偷拍你的隐私",
    "富婆带资进组硬加60多场吻戏", "松岛辉空4比3张禹珍", "名创优品一次性内裤颜面尽失",
    "阿根廷队长父亲去世", "王橹杰 张元英", "茜拉自曝父亲出轨自己闺蜜",
    "田曦薇化的妆被质疑", "曼联vs巴黎圣日耳曼", "韩乔生谈阿根廷队长父亲去世",
    "阿森纳官宣吉马良斯加盟", "女孩遭性侵被不雅视频威胁多次轻生",
    "柬埔寨一园区围殴中国人致1死3伤", "河南三支一扶成绩全部作废公平吗",
    "陈思诚在家里气哭了", "瑞典大满贯 男单32强", "泰国 电诈园区",
}

import random
cat = random.choice(["娱乐", "体育", "社会"])

session = hnw.get_visitor_session()
hot_list = hnw.get_hotsearch_by_category(session, cat)
print(f"[{cat}] 分类热搜共 {len(hot_list)} 条")
candidates = [h for h in hot_list if h["word"] not in LAST_USED]
hot = candidates[0]
keyword = hot["word"]
print(f"选中：{hot['title']}（排名{hot['rank']}）")

posts = hnw.fetch_weibo_posts_text(session, keyword, count=8)
print(f"抓取到 {len(posts)} 条原帖")
for j, p in enumerate(posts[:3], 1):
    print(f"  帖{j} | {p['user']}: {p['text'][:80]}...")

data = {"category": cat, "keyword": keyword, "posts": posts}
with open(os.path.join(BASE_DIR, "_weibo_posts_1.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"\n素材已保存")
