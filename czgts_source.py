# -*- coding: utf-8 -*-
"""创作罐头（czgts.cn）低粉爆款资讯源

对应页面: https://www.czgts.cn/v1/hots/popular（热门素材 → 低粉爆款）
底层接口: POST /muse/content/api/v1/hots/search
固定筛选:
- 媒体平台 = 今日头条
- 内容类型 = 文章
- 粉丝量 < 1万（postType=3 低粉爆款语义，服务端强制）
- 发布时间 = 1天内（startTime/endTime 传 "YYYY-MM-DD HH:MM:SS" 字符串；
  页面 UI 选项"1天内"即 24 小时窗口，对应 candidate 接口 publishTimeLimits 毫秒区间拆成两字段）
- 按阅读(播放)量从高到低（sortBy=1）
内容领域: 娱乐 / 体育（按用户要求 2026-09-03 起去掉时政社会领域，不再抓取社会类）

无需账号登录。早期版本以为接口需要浏览器上下文携带 ttwid cookie，用
DrissionPage 在页面内 fetch；实测纯 requests 直调同样放行（无 cookie
也返回 code=0），故改为 requests 实现，不再依赖 DrissionPage/lxml。
"""
import json
import time
from datetime import datetime, timedelta

import requests

SEARCH_API = "/muse/content/api/v1/hots/search"
BASE_URL = "https://www.czgts.cn"
HOME_URL = BASE_URL + "/v1/home"
UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _time_window(within_hours):
    """返回 startTime/endTime 字符串（"YYYY-MM-DD HH:MM:SS"）；None/0 表示不限发布时间

    服务端只认该格式的字符串：传毫秒/秒时间戳（无论数字还是字符串）要么报 997 要么匹配 0 条。
    """
    if not within_hours:
        return None, None
    end = datetime.now()
    start = end - timedelta(hours=within_hours)
    fmt = "%Y-%m-%d %H:%M:%S"
    return start.strftime(fmt), end.strftime(fmt)

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


def _get_session():
    """模块级 requests 会话：带浏览器 UA 与站内 Referer/Origin"""
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA_PC,
            "Accept": "application/json, text/plain, */*",
            "Referer": BASE_URL + "/v1/hots/popular",
            "Origin": BASE_URL,
        })
        _SESSION = s
    return _SESSION


_SESSION = None


def _fetch_one(session, czgts_cat, limit, within_hours=24):
    start_time, end_time = _time_window(within_hours)
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
        "startTime": start_time,          # 发布时间窗口（"1天内"=24h）
        "endTime": end_time,
    }
    resp = session.post(BASE_URL + SEARCH_API + "?appVersion=",
                        json=payload, timeout=30)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"hots/search 响应非JSON: {resp.text[:200]}")
    if not isinstance(data, dict) or data.get("code") != 0:
        raise RuntimeError(f"hots/search 失败: {str(data)[:200]}")
    return data.get("list") or []


def fetch_czgts_low_fans(categories=("娱乐", "体育"), per_category_limit=30,
                         page=None, headless=False, within_hours=24):
    """抓取创作罐头低粉爆款文章（今日头条/文章/粉丝<1万/发布时间1天内/阅读量降序）

    Args:
        categories: 内部分类列表，取值 娱乐/体育
        per_category_limit: 每个领域拉取条数（按阅读量降序截取）
        page: 已废弃，保留仅为兼容旧调用方签名（原 DrissionPage 页面对象）
        headless: 已废弃，保留仅为兼容旧调用方签名
        within_hours: 发布时间窗口（小时）。24=页面上"1天内"选项；None/0=不限发布时间

    Returns:
        dict {内部分类: [条目...]}，条目按阅读量从高到低
    """
    session = _get_session()
    result = {}
    for cat in categories:
        czgts_cat = CZGTS_CATEGORY.get(cat, cat)
        items = []
        for attempt in range(3):
            try:
                raw = _fetch_one(session, czgts_cat, per_category_limit, within_hours)
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
    return result


if __name__ == "__main__":
    data = fetch_czgts_low_fans()
    for cat, items in data.items():
        print(f"\n【{cat}】top3:")
        for it in items[:3]:
            print(f"  {it['publishTime']} read={it['num']} fans={it['fans']} | {it['title'][:36]}")
            print(f"    搜索词: {it['word']}  url: {it['url']}")
