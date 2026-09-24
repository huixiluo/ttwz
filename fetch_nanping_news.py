# -*- coding: utf-8 -*-
"""从微博热榜（体育分类 + 总榜）筛选男乒相关话题，并抓取话题原帖文字作为资讯素材"""
import json
import re
import hot_news_writer as hnw

# 男乒相关关键词：队伍 + 现役/近期热点男队员名单
NANPING_KEYWORDS = [
    "男乒", "国乒", "乒乓球", "乒乓",
    # 男队队员
    "王楚钦", "樊振东", "马龙", "梁靖崑", "林诗栋", "林高远",
    "周启豪", "向鹏", "袁励岑", "徐瑛彬", "薛飞", "陈垣宇",
    "黄友政", "温瑞博",
]
# 女队关键词（出现则排除，避免误匹配"乒乓球"类女队话题）
WOMEN_EXCLUDE = [
    "孙颖莎", "王曼昱", "王艺迪", "陈幸同", "蒯曼", "陈梦",
    "伊藤美诚", "张本美和", "早田希娜", "平野美宇", "女乒", "女团",
]


def is_nanping(word):
    hit = any(k in word for k in NANPING_KEYWORDS)
    if not hit:
        return False
    # 命中女队关键词的排除（如"王艺迪3比1伊藤美诚"属于女乒）
    if any(k in word for k in WOMEN_EXCLUDE):
        return False
    return True


def main():
    session = hnw.get_visitor_session()
    print("访客session获取成功\n")

    # 1) 体育分类热搜 + 总榜，合并去重
    sport_list = hnw.get_hotsearch_by_category(session, "体育")
    try:
        all_list = hnw.get_hotsearch_list(session)
    except Exception as e:
        print(f"(总榜获取失败: {e}，仅用体育分类榜)")
        all_list = []

    print(f"体育分类热搜: {len(sport_list)} 条 | 总榜: {len(all_list)} 条")

    merged, seen = [], set()
    for h in sport_list + all_list:
        if h["word"] not in seen:
            seen.add(h["word"])
            merged.append(h)

    # 2) 筛选男乒相关话题
    matches = [h for h in merged if is_nanping(h["word"])]
    print(f"\n男乒相关话题: {len(matches)} 条")
    print("=" * 60)
    for h in matches:
        src = "体育榜" if h in sport_list else "总榜"
        hot_val = h.get("num", 0)
        heat = f" 热度{hot_val}" if hot_val else ""
        print(f"  [{src} 排名{h['rank']}] {h['word']}{heat}")
    print("=" * 60)

    if not matches:
        print("热榜中没有男乒相关话题。")
        return

    # 3) 抓取每个话题的原帖文字（资讯正文素材）
    result = []
    for h in matches:
        word = h["word"]
        posts = hnw.fetch_weibo_posts_text(session, word, count=8)
        result.append({
            "topic": word,
            "rank": h["rank"],
            "category": h.get("category", ""),
            "heat": h.get("num", 0),
            "posts": posts,
        })
        print(f"\n话题【{word}】抓到 {len(posts)} 条原帖")
        for p in posts[:3]:
            preview = p["text"][:60].replace("\n", " ")
            print(f"  - {p['user']}: {preview}...")

    with open("_nanping_news.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到 _nanping_news.json（共 {len(result)} 个话题）")


if __name__ == "__main__":
    main()
