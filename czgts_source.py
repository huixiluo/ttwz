# -*- coding: utf-8 -*-
"""创作罐头（czgts.cn）低粉爆款资讯源

对应页面: https://www.czgts.cn/v1/hots/popular（热门素材 → 低粉爆款）
底层接口: POST /muse/content/api/v1/hots/search
固定筛选:
- 媒体平台 = 今日头条
- 内容类型 = 文章
- 粉丝量 < 1万（postType=3 低粉爆款语义，服务端强制）
- 按阅读(播放)量从高到低（sortBy=1）
内容领域: 娱乐 / 体育 / 时政社会（"时政社会"对外映射为"社会"）

无需账号登录，但接口需要浏览器上下文携带 ttwid cookie，
因此通过 DrissionPage 打开 czgts 首页后在页面内 fetch。
"""
import json
import time

SEARCH_API = "/muse/content/api/v1/hots/search"
HOME_URL = "https://www.czgts.cn/v1/home"

# 内部分类(娱乐/体育/社会) <-> 创作罐头领域
CZGTS_CATEGORY = {"娱乐": "娱乐", "体育": "体育", "社会": "时政社会"}
INTERNAL_CATEGORY = {v: k for k, v in CZGTS_CATEGORY.items()}


def _make_word(article):
    """把文章转成微博素材搜索词：keywords 优先，空则截标题"""
    kws = [k.strip() for k in (article.get("keywords") or []) if k.strip()]
    if kws:
        return " ".join(kws[:2])
    title = (article.get("title") or "").strip()
    return title[:16]


def _normalize(article, category, rank):
    """转成与既有 hot_list 兼容的条目结构"""
    return {
        "word": _make_word(article),
        "title": article.get("title", ""),
        "rank": rank,
        "num": int(float(article.get("readCnt") or 0)),  # 阅读量即热度
        "url": article.get("url", ""),
        "image": "",
        "category": category,             # 内部分类: 娱乐/体育/社会
        "czgts_category": article.get("category", ""),  # 原始领域(时政社会等)
        "fans": article.get("fans", ""),
        "readCnt": article.get("readCnt", ""),
        "commentCnt": article.get("commentCnt", ""),
        "diggCnt": article.get("diggCnt", ""),
        "keywords": article.get("keywords", []),
        "authorName": article.get("authorName", ""),
        "publishTime": article.get("publishTime", ""),
        "gid": article.get("gid", ""),
        "source": "czgts",
    }


def _fetch_one(page, czgts_cat, limit):
    payload = {
        "limit": limit,
        "offset": 0,
        "postType": 3,                    # LowFollowerViral 低粉爆款
        "platforms": ["今日头条"],
        "categories": [czgts_cat],
        "articleGenres": ["文章"],
        "fansLimits": "0_10000",          # 粉丝量严格低于1万
        "sortBy": 1,                      # ReadCnt 阅读(播放)量降序
        "searchWord": "",
        "searchId": "",
    }
    js = (
        "return fetch('%s?appVersion=', {method:'POST',"
        "headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify(%s)}).then(r=>r.json())"
        % (SEARCH_API, json.dumps(payload, ensure_ascii=False))
    )
    data = page.run_js(js)
    if not isinstance(data, dict) or data.get("code") != 0:
        raise RuntimeError(f"hots/search 失败: {str(data)[:200]}")
    return data.get("list") or []


def fetch_czgts_low_fans(categories=("娱乐", "体育", "社会"), per_category_limit=30,
                         page=None, headless=False):
    """抓取创作罐头低粉爆款文章（今日头条/文章/粉丝<1万/阅读量降序）

    Args:
        categories: 内部分类列表，取值 娱乐/体育/社会
        per_category_limit: 每个领域拉取条数（按阅读量降序截取）
        page: 可复用的 DrissionPage（须已打开任意 czgts.cn 页面）；None 则内部新开
        headless: 内部新开浏览器时是否无头

    Returns:
        dict {内部分类: [条目...]}，条目按阅读量从高到低
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    own = page is None
    if own:
        co = ChromiumOptions()
        co.auto_port()
        co.set_argument("--disable-gpu")
        co.set_argument("--no-sandbox")
        if headless:
            co.headless()
        page = ChromiumPage(co)
        page.get(HOME_URL)
        time.sleep(8)

    result = {}
    try:
        for cat in categories:
            czgts_cat = CZGTS_CATEGORY.get(cat, cat)
            items = []
            for attempt in range(3):
                try:
                    raw = _fetch_one(page, czgts_cat, per_category_limit)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    print(f"  [czgts] {czgts_cat} 第{attempt+1}次失败({str(e)[:80]})，重试...")
                    time.sleep(3)
            for i, a in enumerate(raw):
                items.append(_normalize(a, cat, i + 1))
            result[cat] = items
            print(f"  [czgts] {czgts_cat}({cat}) 获取 {len(items)} 条低粉爆款文章")
    finally:
        if own:
            page.quit()
    return result


if __name__ == "__main__":
    data = fetch_czgts_low_fans()
    for cat, items in data.items():
        print(f"\n【{cat}】top3:")
        for it in items[:3]:
            print(f"  read={it['num']} fans={it['fans']} | {it['title'][:36]}")
            print(f"    搜索词: {it['word']}  url: {it['url']}")
