#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
今日头条热榜改写工具
功能：获取头条热榜 → 关键词规则分类（娱乐/体育/社会）→ DeepSeek改写 → 真人编辑润色 → 头条话题页配图（百度回退）→ Pillow处理 → 输出HTML
用法：python toutiao_hot_writer.py [娱乐|体育|社会]
"""

import os
import io
import re
import json
import base64
import time
import random
from datetime import datetime
from urllib.parse import quote

import requests
from PIL import Image, ImageEnhance, ImageFilter


# ===== 配置加载 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ===== 通用HTTP =====
UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


# ===== 头条热榜HTTP Session（无需登录，只需带Referer避免403）=====
def get_tt_session():
    """创建请求头条热榜的session，带标准头和Referer（头条部分接口无Referer会403）"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA_PC,
        "Referer": "https://www.toutiao.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return session


# ===== 头条热榜API =====
# 头条官方PC端热榜（免登录，直接GET，返回data数组）
TOUTIAO_HOT_BOARD_API = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"

# 首页兜底抓取（当热榜API返回内部异常时用）
TOUTIAO_HOME_FALLBACK = "https://www.toutiao.com/"


def _extract_image_url(raw_image):
    """从热榜条目的 Image 字段中提取真实图片URL字符串。
    头条API有时返回 dict（含url/url_list），有时返回 str，有时为空。
    """
    if not raw_image:
        return ""
    if isinstance(raw_image, str):
        return raw_image
    if isinstance(raw_image, dict):
        # 优先取 url 字段
        url = raw_image.get("url") or ""
        if isinstance(url, str) and url.startswith("http"):
            return url
        # 回退：url_list 第一项
        url_list = raw_image.get("url_list") or []
        if isinstance(url_list, list) and url_list:
            first = url_list[0]
            if isinstance(first, dict):
                u = first.get("url") or ""
                if isinstance(u, str) and u.startswith("http"):
                    return u
            elif isinstance(first, str) and first.startswith("http"):
                return first
        # 回退：用 uri 拼接（头条图床域名）
        uri = raw_image.get("uri") or ""
        if isinstance(uri, str) and uri:
            return f"https://p3-sign.toutiaoimg.com/{uri}~tplv-tt-shrink:960:540.jpeg"
    return ""


def _parse_tt_hot_list(data_list):
    """解析头条热榜 data 列表，返回标准化列表 [{title,word,rank,num,category,cluster_type,url,image}, ...]"""
    hot_list = []
    for idx, item in enumerate(data_list, 1):
        if not isinstance(item, dict):
            continue
        title = (item.get("Title") or item.get("title") or "").strip()
        if not title:
            continue
        raw_image = item.get("Image") or item.get("image") or item.get("thumbUrl") or ""
        hot_list.append({
            "title": title,
            "word": title,
            "rank": item.get("Rank") or item.get("rank") or idx,
            "num": item.get("HotValue") or item.get("hotValue") or item.get("hot") or 0,
            "category": item.get("Category") or item.get("category") or "",
            "cluster_type": str(item.get("cluster_type") or item.get("clusterType") or ""),
            "url": item.get("Url") or item.get("url") or "",
            "image": _extract_image_url(raw_image),
        })
    return hot_list


def get_toutiao_hot_board(session):
    """获取头条热榜（官方API优先，异常时回退首页DOM解析）。返回标准化 list"""
    # ---------- 1. 优先官方JSON API ----------
    try:
        resp = session.get(TOUTIAO_HOT_BOARD_API, timeout=20)
        if resp.status_code == 200:
            payload = resp.json()
            # 常见返回结构：data / result / data.data
            raw_list = None
            if isinstance(payload, dict):
                raw_list = (
                    payload.get("data")
                    or payload.get("result")
                    or (payload.get("data") or {}).get("data")
                )
            if isinstance(raw_list, list) and raw_list:
                return _parse_tt_hot_list(raw_list)
    except Exception:
        pass

    # ---------- 2. 回退：抓取头条PC首页热榜区块DOM ----------
    try:
        resp = session.get(TOUTIAO_HOME_FALLBACK, timeout=20)
        if resp.status_code == 200:
            html = resp.text
            # 从嵌入的window.__INITIAL_STATE__或脚本中的data-bt属性提取热榜条目
            titles = re.findall(r'"title"\s*:\s*"([^"]{3,80})"', html)
            urls = re.findall(r'"(?:Url|url)"\s*:\s*"(https?://[^"]+)"', html)
            hots = re.findall(r'"(?:HotValue|hotValue)"\s*:\s*(\d+)', html)
            if titles:
                data_list = []
                for i, t in enumerate(titles[:50]):
                    data_list.append({
                        "Title": t,
                        "Rank": i + 1,
                        "HotValue": int(hots[i]) if i < len(hots) else 0,
                        "Url": urls[i] if i < len(urls) else "",
                    })
                if data_list:
                    return _parse_tt_hot_list(data_list)
    except Exception:
        pass

    raise RuntimeError("头条热榜获取失败：官方API和首页回退均无数据")


# ===== 娱乐/体育/社会 关键词分类规则 =====
CATEGORY_KEYWORDS = {
    "娱乐": ["明星", "演员", "歌手", "综艺", "剧集", "电视剧", "电影", "演唱会",
             "出道", "代言", "官宣", "粉丝", "偶像", "爱豆", "影帝", "影后",
             "红毯", "颁奖", "娱乐", "剧照", "杀青", "定档", "上映", "票房",
             "选秀", "离婚", "结婚", "恋情", "金鹰", "金鸡", "白玉兰", "春晚",
             "蜘蛛侠", "蝙蝠侠", "超人", "漫威", "DC", "超级英雄", "重启",
             "奥特曼", "变形金刚", "哈利波特",
             "演技", "古装", "热播", "番剧", "动画", "声优", "配音",
             "网红", "直播", "短视频", "话题", "大麦", "票", "巡演", "演出",
             "浪姐", "披哥", "乘风破浪", "披荆斩棘", "练习生",
             "王俊凯", "肖战", "黄晓明", "罗正", "宋威龙", "刘耀文",
             "陈伟霆", "陈瑶", "敖瑞鹏", "何与", "施南生", "赞达亚",
             "TF家族", "TF四代", "TFBOYS", "白鹿",
             "异人之下", "清明上河园", "生命树", "天才女友",
             "导演", "编剧", "翻拍", "续集", "前传", "OST", "主题曲"],
    "体育": ["比赛", "联赛", "球员", "冠军", "进球", "赛季", "奥运", "世界杯",
             "NBA", "CBA", "足球", "篮球", "网球", "乒乓", "羽毛球", "游泳",
             "田径", "夺冠", "决赛", "半决赛", "教练", "俱乐部", "转会", "运动员",
             "选手", "金牌", "银牌", "铜牌", "破纪录", "欧洲杯", "亚运会",
             "全运会", "锦标赛", "巡回赛", "公开赛", "德比", "德转",
             "球衣", "球场", "场馆", "积分", "排名赛",
             "张继科", "王楚钦", "马龙", "樊振东", "孙颖莎", "陈梦",
             "全红婵", "苏炳添", "武磊", "郑智",
             "赛事", "解说员", "中超", "国足", "男篮", "女篮",
             "世锦赛", "资格赛", "小组赛", "淘汰赛", "MVP", "比分",
             "射门", "篮板", "助攻", "绝杀", "加时", "点球", "红牌", "黄牌"],
    "社会": ["警方", "事故", "救援", "市民", "小区", "学校", "学生", "老人",
             "交通", "地铁", "高铁", "天气", "暴雨", "高温", "疫情", "医疗",
             "政策", "法规", "法院", "判决", "见义勇为", "感动", "暖心", "烈士",
             "地震", "海啸", "坍塌", "倒塌", "火灾", "爆炸", "洪水", "泥石流",
             "台风", "龙卷风", "雪灾",
             "退货", "取件码", "快递", "消费者", "维权", "投诉",
             "芯片", "半导体", "市值", "三星", "海力士", "台积电",
             "新能源", "电动车", "电池", "光伏",
             "银行", "公积金", "房价", "物价", "工资", "就业",
             "供冷", "供暖", "超市", "存包",
             "日本", "韩国", "印度", "美国", "俄罗斯", "泰国", "总理",
             "歼20", "导弹", "军演", "海军", "空军",
             "探险队", "登山", "遇难", "谋杀", "日元", "危机",
             "城管", "交警", "消防", "医生", "护士", "教师", "农民",
             "拆迁", "征地", "维权", "上访",
             "高考", "中考", "考研", "公务员", "编制",
             "车祸", "追尾", "坠楼", "溺水", "失联",
             "诈骗", "盗窃", "抢劫", "传销", "电信", "网络安全",
             "GDP", "通胀", "降息", "加息", "汇率", "A股", "股票",
             "扶贫", "乡村", "三农", "低保", "医保", "社保"],
}


def classify_tt_topic(item):
    """关键词打分 + cluster_type 兜底：将头条热榜条目分类为娱乐/体育/社会"""
    title = item.get("title", "") or item.get("word", "")
    cluster_type = item.get("cluster_type", "")
    category_tag = item.get("category", "")

    # ---- 优先：cluster_type / category_tag 强信号 ----
    ct = str(cluster_type)
    # 头条 cluster_type 参考：1=娱乐/人物, 2=财经/社会, 3=体育, 5=科技, 6=社会民生...
    # 这些编号不固定，只作为弱辅助；category_tag 若有直接中文分类则更可靠
    if category_tag:
        cat_zh = str(category_tag)
        if any(k in cat_zh for k in ["娱乐", "综艺", "明星", "影视", "电影", "剧集"]):
            return "娱乐"
        if any(k in cat_zh for k in ["体育", "足球", "篮球", "赛事", "运动", "奥运", "NBA"]):
            return "体育"
        if any(k in cat_zh for k in ["社会", "民生", "新闻", "国内", "国际", "军事", "财经"]):
            return "社会"

    # ---- 主逻辑：关键词打分，长词优先 ----
    scores = {"娱乐": 0, "体育": 0, "社会": 0}
    for cat in ["娱乐", "体育", "社会"]:
        for kw in CATEGORY_KEYWORDS[cat]:
            if kw in title:
                # 长词权重更高，避免"篮球"被"篮"之类短字先匹配（这里都是多字无问题）
                scores[cat] += len(kw)

    max_score = max(scores.values())
    if max_score > 0:
        # 取得分最高，同分按 娱乐>体育>社会 默认优先（娱乐关键词多更易得分）
        for cat in ["娱乐", "体育", "社会"]:
            if scores[cat] == max_score:
                return cat

    # ---- 兜底：全部无命中时，cluster_type→社会，其余→社会 ----
    return "社会"


def pick_tt_hot_by_category(hot_list, category, used_titles=None):
    """从头条热榜中按类别筛选，取排名最高且未用过的一条"""
    used_titles = used_titles or set()
    # 先按类别筛选
    candidates = [h for h in hot_list if classify_tt_topic(h) == category and h["word"] not in used_titles]
    if not candidates:
        # 类别筛选无果，直接取未用过的整体
        candidates = [h for h in hot_list if h["word"] not in used_titles]
    if not candidates:
        candidates = hot_list  # 最后兜底：允许重复
    candidates.sort(key=lambda x: x.get("rank", 999))
    return candidates[0]


# ===== 智谱GLM改写（提示词与微博版完全一致，仅背景词替换为头条）=====
REWRITE_PROMPT = """你是一位有十年经验的媒体编辑，文风接地气，擅长把热点写成让人想读下去的文章。

请根据以下今日头条热榜话题，撰写一篇正文必须高于600字的文章（严格硬性要求，正文字数>600），并配一个爆款标题。

【热榜话题】{keyword}
【热榜排名】第{rank}位

【标题要求——非常重要，必须严格执行】
1. 必须是三段式爆款标题，字数不超过30个字（含标点），整体语义完整，不能半截话戛然而止；
2. 三段式结构是硬性要求：标题必须由三个短句/短语组成，用中文逗号分隔，即标题中必须恰好出现两个逗号，分成三段。禁止只写一段、两段或四段。正确示例："明星哭穷上热搜，网友不买账，这届观众清醒了"（两个逗号，三段）；
3. 结合本条资讯的具体内容，从以下两种结构形式中选择更适合的一种来生成标题：
   - 结构A：事件+细节+悬念（先点明事件，再补充一个关键细节，最后用悬念收尾引发好奇）
   - 结构B：现象+冲突+疑问（先描述现象，再点出冲突点，最后用疑问句引发思考）
   选择依据：资讯本身有戏剧性细节时优先用结构A；资讯涉及争议、对立或反差时优先用结构B；
4. 三段要短促有力，每段尽量不超过10个字，节奏感强，像朋友分享时说的话，口语化，不要书面腔；
5. 制造悬念、冲突或反差，让人忍不住想点开看；可用疑问句、数字、对比、情绪词等技巧，但不要标题党骗点击；
6. 不要用"震惊！""速看！""突发！"这类低质标题党词；
7. 标题要和正文内容匹配，不能文不对题；
8. 禁止编造或暗示未经证实的事实，禁止用假设性陈述误导读者（如"某某没拿奖？""某某要退出？"这类无中生有的猜测），疑问句只能基于已公开的事实提问；
9. 标题不得偏向或点名特定人物（正文没偏向某个人，标题也不要只聚焦某一个人），应从事件整体或群体角度切入，保持中立客观；
10. 写完标题后请自查：标题是否恰好有两个逗号、分成三段？若不是，必须改写为符合三段式结构的标题。

【内容要求】
1. 如果你了解该事件的背景，请基于事实进行改写；如果不确定具体细节，请围绕话题主题进行创作，但不得编造虚假信息；
2. 适当补充背景信息（如事件前因、相关背景）或延伸内容（如类似案例），提升文章深度和吸引力；
3. 优化段落结构，每段不超过150字，适当分段提升阅读体验，建议分6-8段，至少6段；
4. 文章整体导向积极正能量，站在读者角度，引发共鸣，让读者看完有想评论的冲动；
5. 【字数硬性要求】正文字数必须高于600字（>600），这是硬性指标，宁多勿少，写到650-750字为佳；
6. 保持中立客观，不得偏向或拉踩特定人物，涉及多人时一视同仁地呈现。

【风格要求——非常重要，必须严格执行】
1. 必须像真人写的，坚决去除AI味。具体做到：
   - 严格避免使用任何形式的承接词和过渡词汇：不仅包括"首先/其次/最后/总之/综上所述/总而言之/不难看出/值得一提的是/同时"这类常见词，还包括"然而/但是"以及其他任何可能被用来引导或总结的词汇；
   - 每一段落都必须直接进入讨论主题，不得通过引入性或过渡性短语来构建内容；
   - 尤其在文章最后一部分，直接陈述观点或结论，避免使用任何可能导致总结或过渡的词汇和短语；
   - 禁止使用排比句式堆砌（如"是...也是...更是..."、"不仅...而且...还..."）；
   - 禁止空洞的形容词堆砌（如"令人深思、发人深省、意义深远"）；
   - 禁止每段都用总结句收尾；
2. 注重使用多样化的句式结构，段落之间的逻辑过渡要自然（靠内容和逻辑衔接，不靠过渡词），语言应符合目标读者群体的习惯与期待，避免生硬的术语堆砌或机械式的重复。力求让整篇文章像是与读者进行的一场真诚对话；
3. 多用生活化的表达，像和朋友聊天那样自然。可以适当用口语、俗语、比喻，让文字有温度；
4. 句子长短错落，不要都是长句或都是短句。偶尔用一个很短的句子制造节奏感；
5. 可以带一点个人视角和情绪，比如"说实话""老实讲""说起来"这类自然过渡；
6. 【开头——非常重要，必须严格执行】开头必须自然、多样、有代入感，坚决杜绝AI味和套路化：
   - 严禁使用以下固化开头模式（违反即视为不合格）：
     * "刷到/看到/点开+热搜/榜单/话题"类（如"刷到这条热搜""看到榜单上挂着""点开话题"）；
     * "朋友圈里/群里/评论区"类（如"朋友圈又炸了""群里在转"）；
     * "热搜第X位/挂在热搜"类自我引用榜单排名的表述；
     * "近日""近日来""近日，一则..."这类新闻稿套路；
     * "话说回来""闲来无事"等生硬铺垫；
     * "单句成段"式开头：第一段只有一句简短的金句/悬念/感叹独立成段（如"有人把出身当包袱藏起来，有人把它摊开在阳光下聊。"单独一段即止）。这是近期文章的固化模式，严禁再用。
   - 【开头段落结构硬性要求】第一段必须是由2句以上构成的自然段落：钩子句（细节/画面/问题/观点）放在段首，后面紧跟1-3句展开（补充背景、交代人物、推进事件），把悬念融入叙事流里，而不是孤零零甩一句话吊着。后续各段也不得频繁使用单句成段。
   - 每篇文章的开头切入方式必须不同，请从以下手法中根据内容选择最贴合的一种，且不要与近期文章重复：
     * 场景切入：用一个具体的生活场景或画面直接开场（如"下班路上刷手机，一条消息弹出来"）；
     * 细节切入：从事件中最抓人的一个细节、一句话、一个动作写起；
     * 反问切入：用一个直击人心的问题开场，引发读者思考；
     * 观点切入：先抛出一个判断或态度，再带出事件；
     * 对比切入：用今昔对比、表里对比制造反差；
     * 故事切入：像讲一个故事那样自然开场，先铺垫再点题；
     * 情绪切入：直接写出一种情绪或感受，让读者共情。
   - 开头要让人一眼觉得"这是个人在写东西"，而不是"机器在凑字数"。开头三句话内必须抓住读者，不要绕弯子铺垫；
7. 绝对禁止使用儿话音！这是硬性要求，违反即视为不合格。任何"X儿"格式的口语化后缀都不允许，包括但不限于：事儿/点儿/地儿/哥们儿/玩意儿/劲儿/味儿/脸儿/份儿/调儿/孩儿/老头儿/聊天儿/慢慢儿/好好儿。必须用规范表达替代（这事→这件事，一点→一点，地方→地方，朋友→朋友，东西→东西，劲头→劲头，味道→味道）。写完后请自查，若出现"儿"字作为词尾后缀，必须改写。

【输出格式——必须严格按此格式】
第一行：标题（不超过30字）
第二行：空行
第三行开始：文章正文，段落之间用空行分隔。
不要加"标题："等前缀，不要加任何额外说明。"""


def _is_three_part_title(title):
    """校验标题是否为严格三段式（恰好两个逗号分三段）"""
    comma_count = title.count('，') + title.count(',')
    return comma_count == 2


def _parse_llm_output(content, keyword):
    """解析LLM输出：第一行为标题，空行后为正文"""
    lines = content.split("\n")
    title = lines[0].strip() if lines else keyword
    # 去掉标题前缀（如"标题："）
    title = re.sub(r'^(标题[:：]\s*)', '', title)
    # 标题字数兜底：超过30字时智能截断，保证三段式结构尽量完整
    if len(title) > 30:
        comma_positions = [i for i, c in enumerate(title) if c in '，,']
        truncate_at = 30
        for i in range(30, 22, -1):
            if i < len(title) and title[i-1] in '，,。！？、；：;:!?':
                truncate_at = i
                break
        if comma_positions:
            last_comma_before = max([p for p in comma_positions if p < truncate_at], default=-1)
            if last_comma_before >= 0 and (truncate_at - last_comma_before) <= 3:
                truncate_at = last_comma_before + 1
        title = title[:truncate_at].rstrip('，,。！？、；：;:!?')

    # 正文：跳过标题和紧随的空行
    body_start = 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    article = "\n".join(lines[body_start:]).strip()
    if not article:
        article = content  # 兜底
    return title, article


def rewrite_article(keyword, rank, api_key, model, api_url=None):
    """调用LLM改写文章（DeepSeek兼容OpenAI格式），返回 (标题, 正文)
    标题严格校验三段式（两个逗号分三段），不符合则重试一次。
    """
    url = api_url or "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = REWRITE_PROMPT.format(keyword=keyword, rank=rank)

    title, article = None, None
    for attempt in range(2):  # 最多2次：首次 + 三段式不合规重试1次
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 1500,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        title, article = _parse_llm_output(content, keyword)

        if _is_three_part_title(title):
            break  # 三段式合规，直接采用
        print(f"  [标题校验] 第{attempt+1}次生成的标题非三段式：{title}，重试...")
        time.sleep(1)

    article = clean_erhua(article)
    title = clean_erhua(title)
    return title, article


# ===== 真人文字校准编辑 =====
POLISH_PROMPT = """你是一位真人文字校准编辑。请对以下文章正文进行行文改写。

【改写原则——必须严格执行】
1. 保留全部原文事实、核心观点，不得篡改、删减、编造任何事实信息；
2. 删掉以下内容（发现即删除或改写）：
   - 空洞客套话（如"希望xxx""愿xxx""让我们一起xxx"）；
   - 机械连接词（首先/其次/最后/总之/综上所述/总而言之/不难看出/值得一提的是/同时）；
   - 过渡承接词（然而/但是，以及其他任何可能被用来引导或总结的词汇）；
   - 华丽排比句（是...也是...更是.../不仅...而且...还...）；
   - 重复的结果性表述（同一段落里反复说同一个意思）；
   - 教科书式的升华总结（如"这不仅是xxx，更是xxx的体现""值得我们每个人深思"）；
3. 调节句子长短节奏，让长短句错落有致；句式结构多样化，段落之间靠内容和逻辑自然衔接，不靠过渡词；语言符合目标读者群体的习惯与期待，避免生硬的术语堆砌或机械式的重复，让文章像是与读者进行的一场真诚对话；
4. 每一段落直接进入讨论主题，删掉引入性、过渡性的开头短语；文章最后一部分直接陈述观点或结论，不得出现任何可能导致总结或过渡的词汇和短语；
5. 允许有轻微不完美，还原普通人真实输出的语感，不要写得像范文或满分作文；
6. 禁止堆砌网络热梗、禁止强行口语化、禁止编造故事或细节；
7. 不要套用别的模板风格，保持原文的整体基调和段落结构，只做行文层面的打磨；
8. 【字数硬性要求】改写后正文字数必须高于600字（>600）。可适度精简，但不得低于600字；若删减后会低于600字，请补充适当内容维持字数。

【输入文章正文】
{article}

【输出要求】
直接输出改写后的正文，不要加任何说明、不要加标题、不要加"改写后"等前缀。段落之间用空行分隔。"""


def polish_article(article, api_key, model, api_url=None):
    """对文章正文进行真人文字校准编辑，返回改写后的正文"""
    url = api_url or "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = POLISH_PROMPT.format(article=article)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1500,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    polished = data["choices"][0]["message"]["content"].strip()
    if not polished:
        polished = article  # 兜底：返回原文
    polished = clean_erhua(polished)
    return polished


# ===== 爆款标题候选生成（基于最终文章正文，生成10个供人工挑选）=====
TITLE_CANDIDATES_PROMPT = """你是一位深谙传播规律的爆款标题编辑。请根据以下最终文章正文，生成10个引人注目、吸引点击的「标题党」风格的标题。

【硬性要求——必须严格执行】
1. 每个标题都必须是三段式结构：由三个短句/短语组成，用中文逗号分隔，恰好两个逗号分成三段。正确示例："明星哭穷上热搜，网友不买账，这届观众清醒了"；
2. 每个标题字数不超过30个字（含标点符号）；
3. 确保标题能够吸引读者的兴趣，并准确反映文章或内容的关键亮点，不编造、不歪曲文章内容；
4. 注重创意、新颖性和吸引力，10个标题的角度、句式、切入点要有明显差异，不要同质化；
5. 可用疑问句、数字、对比、悬念、情绪词等技巧制造冲突感，但禁止"震惊！""速看！"这类低质标题党词；
6. 标题保持中立客观，不得偏向或点名特定人物，疑问句只能基于文章已陈述的事实提问。

【文章正文】
{article}

【输出格式——必须严格按此格式】
直接输出10行，每行一个标题，按1-10编号，格式如：
1、标题一
2、标题二
……
10、标题十
不要加任何其他说明。"""


def generate_title_candidates(article, api_key, model, api_url=None, count=10):
    """根据最终文章正文生成10个爆款候选标题（LLM模式）。
    只保留合规标题（三段式且<=30字），返回标题列表。
    """
    url = api_url or "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = TITLE_CANDIDATES_PROMPT.format(article=article)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 900,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()

    candidates = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 去掉编号前缀（1、 1. 1）等）和"标题："前缀
        m = re.match(r"^\d+\s*[、.．)）]?\s*(.+)$", line)
        title = m.group(1).strip() if m else line
        title = re.sub(r"^(标题\d*[:：]\s*)", "", title)
        title = clean_erhua(title).strip()
        if not title or title in candidates:
            continue
        # 校验：三段式 + 不超30字
        if not _is_three_part_title(title) or len(title) > 30:
            print(f"  [候选过滤] 不合规候选已剔除：{title}")
            continue
        candidates.append(title)
    return candidates[:count]


# 儿话音替换表（覆盖常见口语后缀，"儿"作为词尾后缀）
_ERHUA_MAP = {
    "这事儿": "这件事", "那事儿": "那件事",
    "哥们儿": "朋友", "玩意儿": "东西", "老头儿": "老头",
    "聊天儿": "聊天", "好玩儿": "好玩", "没事儿": "没事",
    "差点儿": "差点", "早点儿": "早点", "晚点儿": "晚点",
    "快点儿": "快点", "慢点儿": "慢点",
    "一会儿": "一会", "一阵儿": "一阵",
    "哪儿": "哪里", "这儿": "这里", "那儿": "那里",
    "事儿": "事", "劲儿": "劲头", "味儿": "味道",
    "点儿": "点", "地儿": "地方", "脸儿": "脸庞",
    "份儿": "份", "调儿": "调子", "孩儿": "孩子",
}


def clean_erhua(text):
    """清除儿话音：按替换表替换，再用正则兜底处理剩余的"X儿"词尾"""
    if not text:
        return text
    # 1. 按替换表精确替换（长串优先，避免短串先匹配破坏长串）
    for k in sorted(_ERHUA_MAP.keys(), key=len, reverse=True):
        text = text.replace(k, _ERHUA_MAP[k])
    # 2. 正则兜底：删除"汉字+儿"中作为后缀的"儿"字
    #    排除"儿"作为词首的合法词（儿女/儿童/儿子/儿科/儿歌/儿时/儿媳/儿郎等）
    import re as _re
    text = _re.sub(r'([\u4e00-\u9fa5])儿(?!女|童|子|科|歌|时|媳|郎|孙)', r'\1', text)
    return text


# ===== 头条话题页文本抓取（替代微博原帖搜索）=====
def fetch_toutiao_posts_text(session, keyword, topic_url="", count=8):
    """从头条话题详情页中提取正文摘要和热评文字，作为改写素材返回。
    返回 list[dict]，每项含 text/user/created_at。
    """
    posts = []
    # ---- 优先：若给了话题详情Url，直接请求话题页提取摘要/评论 ----
    if topic_url:
        try:
            resp = session.get(topic_url, timeout=20)
            if resp.status_code == 200:
                html = resp.text
                # 提取嵌入JSON中的article abstract / title / comment content
                # 方法1：从JSON块抓 title / abstract / content 字段
                abstracts = re.findall(r'"(?:abstract|content|summary)"\s*:\s*"([^"]{20,500})"', html)
                comments = re.findall(r'"(?:comment_text|text|content)"\s*:\s*"([^"]{15,500})"', html)
                all_texts = list(dict.fromkeys(abstracts + comments))  # 去重保序
                for i, t in enumerate(all_texts):
                    t = t.strip()
                    if len(t) < 15:
                        continue
                    posts.append({
                        "text": t,
                        "user": "头条网友" if i >= len(abstracts) else "资讯摘要",
                        "created_at": "",
                    })
                    if len(posts) >= count:
                        return posts
        except Exception:
            pass

    # ---- 回退：用头条搜索接口抓相关文章摘要 ----
    try:
        search_url = (
            f"https://www.toutiao.com/api/search/content/"
            f"?keyword={quote(keyword)}&count=20&format=json"
        )
        resp = session.get(search_url, headers={
            "User-Agent": UA_PC,
            "Referer": "https://www.toutiao.com/search/",
        }, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            for it in items:
                if not isinstance(it, dict):
                    continue
                text = (
                    it.get("abstract") or it.get("content") or it.get("summary") or ""
                ).strip()
                title = (it.get("title") or "").strip()
                if len(text) < 15 and len(title) < 8:
                    continue
                merged = (title + "。" + text) if title and text and title not in text else (text or title)
                clean = re.sub(r'<[^>]+>', '', merged).strip()
                if len(clean) < 15:
                    continue
                posts.append({
                    "text": clean[:600],
                    "user": it.get("media_name") or it.get("source") or "头条资讯",
                    "created_at": it.get("datetime") or "",
                })
                if len(posts) >= count:
                    break
    except Exception:
        pass

    return posts


# ===== 微博话题配图（从微博搜索话题原帖图片）=====
def get_weibo_session():
    """模拟微博访客系统，返回带SUB cookie的session（免登录）"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA_PC})
    try:
        session.get("https://s.weibo.com/top/summary", timeout=15)
        fp = json.dumps({"os": "2", "browser": "Chrome120,0,0,0",
                         "fonts": "undefined", "screenInfo": "1920*1080*24", "plugins": ""})
        resp = session.post(
            "https://passport.weibo.com/visitor/genvisitor",
            data={"cb": "gen_callback", "fp": fp},
            headers={"Referer": "https://s.weibo.com/"},
            timeout=15,
        )
        m = re.search(r'gen_callback\((.*)\)', resp.text, re.DOTALL)
        if not m:
            raise RuntimeError("微博访客系统: 获取tid失败")
        tid = json.loads(m.group(1))["data"]["tid"]
        session.get(
            f"https://passport.weibo.com/visitor/visitor?a=incarnate&t={tid}&w=2&c=100"
            f"&gc=&cb=cross_domain&from=weibo&_rand={int(time.time() * 1000)}",
            headers={"Referer": "https://s.weibo.com/"},
            timeout=15,
        )
        if not session.cookies.get("SUB"):
            raise RuntimeError("微博访客系统: 未获取到SUB cookie")
    except RuntimeError:
        raise
    except Exception:
        pass
    return session


def fetch_images_from_weibo(weibo_session, keyword, count=3):
    """从微博话题原帖提取配图。用话题标签(#关键词#)搜索，确保只取话题原帖图片。
    返回base64列表。数量不足时由调用方百度补足。"""
    images = []
    topic_query = f"#{keyword}#"
    search_url = (
        f"https://weibo.com/ajax/statuses/search"
        f"?q={quote(topic_query)}"
    )
    try:
        resp = weibo_session.get(search_url, headers={
            "User-Agent": UA_PC,
            "Referer": "https://weibo.com/",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        statuses = data.get("statuses", [])
        for s in statuses:
            pic_infos = s.get("pic_infos", {})
            if not pic_infos:
                continue
            for pid, info in pic_infos.items():
                # 优先原图（高清）-> largest -> large
                img_url = (
                    info.get("original", {}).get("url")
                    or info.get("largest", {}).get("url")
                    or info.get("large", {}).get("url")
                    or ""
                )
                if not img_url:
                    continue
                try:
                    img_resp = weibo_session.get(img_url, headers={
                        "User-Agent": UA_PC,
                        "Referer": "https://weibo.com/",
                    }, timeout=20)
                    if img_resp.status_code == 200 and len(img_resp.content) > 8000:
                        b64 = process_image(img_resp.content)
                        if b64:
                            images.append(b64)
                            if len(images) >= count:
                                return images
                except Exception:
                    continue
                time.sleep(0.3)
    except Exception:
        pass
    return images


# ===== 头条话题页图片提取 =====
def fetch_images_from_toutiao(session, keyword, topic_image_url="", topic_url="", count=3):
    """优先取热榜API返回的话题缩略图，再从话题详情页抓正文中的图片；
    数量不足时由调用方继续从微博/百度补足。返回base64列表。"""
    images = []
    # 1) 热榜API直接给的缩略图
    if topic_image_url and isinstance(topic_image_url, str) and topic_image_url.startswith("http"):
        try:
            img_resp = session.get(topic_image_url, headers={
                "User-Agent": UA_PC,
                "Referer": "https://www.toutiao.com/",
            }, timeout=20)
            if img_resp.status_code == 200 and len(img_resp.content) > 8000:
                b64 = process_image(img_resp.content)
                if b64:
                    images.append(b64)
        except Exception:
            pass

    # 2) 话题详情页中的图片：从嵌入<script> JSON里提取 image_list / image / img URLs
    if topic_url and len(images) < count:
        try:
            resp = session.get(topic_url, timeout=20)
            if resp.status_code == 200:
                html = resp.text
                # 头条详情页JSON里常见图片字段：匹配 https://...toutiaoimg.com/...
                img_urls = re.findall(r'(https?://[^\s"<>]+toutiaoimg\.com/[^\s"<>]+\.(?:jpe?g|png|webp))', html, re.IGNORECASE)
                img_urls = list(dict.fromkeys(img_urls))  # 去重保序
                for img_url in img_urls:
                    try:
                        img_resp = session.get(img_url, headers={
                            "User-Agent": UA_PC,
                            "Referer": "https://www.toutiao.com/",
                        }, timeout=20)
                        if img_resp.status_code == 200 and len(img_resp.content) > 8000:
                            b64 = process_image(img_resp.content)
                            if b64:
                                images.append(b64)
                                if len(images) >= count:
                                    return images
                    except Exception:
                        continue
                    time.sleep(0.3)
        except Exception:
            pass

    return images


# ===== 配图去重（dHash 感知哈希，纯 PIL 实现，不依赖 numpy）=====
def _dhash(img, hash_size=16):
    """差异哈希：比较相邻像素亮度，返回 hash_size*(hash_size-1) 位字符串。"""
    img = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    pixels = list(img.getdata())
    bits = []
    for row in range(hash_size):
        base = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[base + col]
            right = pixels[base + col + 1]
            bits.append('1' if left < right else '0')
    return ''.join(bits)


def _hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)


def _dedupe_images(images, threshold=15):
    """对 base64 图片列表做视觉去重，保留每张图首次出现的版本。
    threshold 越小判定越严格；默认 15，海明距离 <15 视为同一张图。
    无法解码的图片原样保留（不阻塞管线）。
    """
    kept = []
    kept_hashes = []
    for b64 in images:
        try:
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            h = _dhash(img)
        except Exception:
            kept.append(b64)
            continue
        if any(_hamming(h, kh) < threshold for kh in kept_hashes):
            continue
        kept.append(b64)
        kept_hashes.append(h)
    return kept


def _is_dup_with(images, b64, threshold=15):
    """判断 b64 是否与 images 列表中任一图视觉重复。"""
    try:
        h = _dhash(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB"))
    except Exception:
        return False
    for other in images:
        try:
            oh = _dhash(Image.open(io.BytesIO(base64.b64decode(other))).convert("RGB"))
        except Exception:
            continue
        if _hamming(h, oh) < threshold:
            return True
    return False


def fetch_images_unified(tt_session, keyword, topic_image_url="", topic_url="", count=5):
    """统一配图管线（4层优先级 + 全链路去重）：
    1. 头条热榜缩略图
    2. 头条话题详情页正文图片
    3. 微博话题原帖配图（#关键词# 搜索）
    4. 百度图片搜索（最终回退）
    每层图片先做 dHash 视觉去重，且跨层不再收录与已选图片重复的图，
    最终凑够 count 张互不重复的配图。返回 (images_list, source_desc)。
    """
    images = []
    source_parts = []

    def _append_unique(new_imgs, tag):
        """把 new_imgs 中与 images 不重复的图追加进来，返回实际追加数。"""
        added = 0
        for b64 in new_imgs:
            if len(images) >= count:
                break
            if _is_dup_with(images, b64):
                continue
            images.append(b64)
            added += 1
        if added:
            source_parts.append(f"{tag}({added}张)")

    # 1+2: 头条（先层内去重，再收录）
    try:
        tt_imgs = fetch_images_from_toutiao(tt_session, keyword, topic_image_url, topic_url, count)
        tt_imgs = _dedupe_images(tt_imgs)
        if tt_imgs:
            _append_unique(tt_imgs, "头条")
    except Exception as e:
        print(f"  [头条配图跳过] {e}")

    # 3: 微博（不足时，抓取 count*2 以便去重后有富余）
    if len(images) < count:
        try:
            print("  获取微博访客session...")
            wb_session = get_weibo_session()
            wb_imgs = fetch_images_from_weibo(wb_session, keyword, count=count * 2)
            wb_imgs = _dedupe_images(wb_imgs)
            if wb_imgs:
                _append_unique(wb_imgs, "微博")
        except Exception as e:
            print(f"  [微博配图跳过] {e}")

    # 4: 百度（仍不足时，同样抓 count*2 以便去重后有富余）
    if len(images) < count:
        try:
            bd_imgs = fetch_images_baidu(keyword, count=count * 2)
            bd_imgs = _dedupe_images(bd_imgs)
            if bd_imgs:
                _append_unique(bd_imgs, "百度")
        except Exception as e:
            print(f"  [百度配图跳过] {e}")

    # 最终兜底去重、截断到 count
    images = _dedupe_images(images)[:count]
    source = " + ".join(source_parts) if source_parts else "无"
    return images, source


# ===== 百度图片搜索 =====
def fetch_images_baidu(keyword, count=3):
    """通过百度图片搜索获取高清配图，优先原图，过滤低清小图，返回base64列表"""
    url = "https://image.baidu.com/search/acjson"
    params = {
        "tn": "resultjson_com",
        "ipn": "rj",
        "fp": "result",
        "word": keyword,
        "queryWord": keyword,
        "cl": "2",
        "lm": "-1",
        "ie": "utf-8",
        "oe": "utf-8",
        "face": "0",
        "istype": "2",
        "nc": "1",
        "pn": 0,
        "rn": 30,
    }
    resp = requests.get(url, params=params, headers={"User-Agent": UA_PC}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("data", [])

    images = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # objURL常被加密为乱码无法直接下载，优先使用可用的真实URL
        img_url = (
            item.get("middleURL")
            or item.get("thumbURL")
            or item.get("hoverURL")
            or item.get("objURL")
            or item.get("originalURL")
        )
        if not img_url or not img_url.startswith("http"):
            continue
        try:
            img_resp = requests.get(img_url, headers={"User-Agent": UA_PC}, timeout=20)
            if img_resp.status_code == 200 and len(img_resp.content) > 8000:
                b64 = process_image(img_resp.content)
                if b64:
                    images.append(b64)
                    if len(images) >= count:
                        break
        except Exception:
            continue
        time.sleep(0.3)
    return images


# ===== 图片处理 =====
def process_image(img_bytes):
    """滤镜处理图片（保留原尺寸，不裁剪），返回base64字符串。过滤过小的图片（人物不清晰）"""
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 最小尺寸过滤：宽<500或高<300的图片跳过（人物不清晰）
    w, h = img.size
    if w < 500 or h < 300:
        return None

    # 限制最大宽度为1200（提升清晰度，过大则等比缩小）
    if img.width > 1200:
        ratio = 1200 / img.width
        img = img.resize((1200, int(img.height * ratio)), Image.LANCZOS)

    # 滤镜：增强对比度+锐度+色彩饱和度（提升人物清晰度）
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Sharpness(img).enhance(1.30)
    img = ImageEnhance.Color(img).enhance(1.08)
    # 锐化提升清晰度（增强人物面部细节）
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=90, threshold=2))

    # 转base64（提高JPEG质量到92，保留更多细节）
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ===== HTML生成 =====
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    max-width: 680px;
    margin: 0 auto;
    padding: 30px 20px 60px;
    color: #333;
    line-height: 1.85;
    background: #fafafa;
  }}
  h1 {{
    font-size: 24px;
    color: #1a1a1a;
    text-align: center;
    margin-bottom: 8px;
    line-height: 1.4;
  }}
  .meta {{
    text-align: center;
    color: #999;
    font-size: 13px;
    margin-bottom: 30px;
  }}
  p {{
    font-size: 16px;
    margin: 0 0 18px;
    text-align: justify;
  }}
  .img-wrap {{
    margin: 24px 0;
    text-align: center;
  }}
  .img-wrap img {{
    max-width: 100%;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.1);
  }}
  .img-caption {{
    font-size: 12px;
    color: #999;
    text-align: center;
    margin-top: 6px;
    margin-bottom: 0;
  }}
  .footer {{
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #eee;
    color: #bbb;
    font-size: 12px;
    text-align: center;
  }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">{date} &middot; 热点改写</div>
{body}
<div class="footer">本文基于今日头条热榜改写，配图经二次处理</div>
</body>
</html>"""


def _calc_image_layout(total_paragraphs, num_images=5):
    """动态计算图片布局（5张图上限）——均匀分布，避免中间大片文字空档。
    返回 dict: {段落号: 图片数量}
    """
    if total_paragraphs < 1:
        return {}

    n_groups = (num_images - 1) // 2  # 5张图→2组，3张→1组，3张以下→0组
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}

    first = 1

    def _build_positions(last):
        if last < 3:
            return [first]
        pos_list = [first]
        if n_groups == 1:
            pos_list.append(last)
        else:
            step = (last - first) / n_groups
            for k in range(1, n_groups + 1):
                if k == n_groups:
                    raw = last
                else:
                    raw = first + step * k
                pos = int(round(raw))
                min_pos = pos_list[-1] + 2
                remaining_after = n_groups - k
                max_pos = last - 2 * remaining_after
                pos = max(min_pos, min(max_pos, pos))
                pos_list.append(pos)
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1):
            pos_list.pop()
        return pos_list

    def _max_gap(pos_list):
        if len(pos_list) < 2:
            return 0
        return max(pos_list[i+1] - pos_list[i] - 1 for i in range(len(pos_list) - 1))

    candidates = []
    for tail_target in [2, 3]:
        last_cand = total_paragraphs - tail_target
        if last_cand >= 3:
            positions = _build_positions(last_cand)
            if len(positions) >= 2:
                actual_tail = total_paragraphs - positions[-1]
                gap = _max_gap(positions)
                candidates.append((gap, actual_tail, positions))

    if not candidates:
        return {1: 1}

    def _score(c):
        gap, tail, pos = c
        return (0 if gap <= 3 else 1, 0 if tail <= 2 else 1, gap, tail)

    candidates.sort(key=_score)
    best_positions = candidates[0][2]

    layout = {}
    for i, p in enumerate(best_positions):
        layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))


def build_html(title, article_text, images):
    """生成HTML内容，动态图片布局"""
    paragraphs = [p.strip() for p in article_text.split("\n") if p.strip()]
    body_parts = []
    img_idx = 0
    image_layout = _calc_image_layout(len(paragraphs), len(images))
    for i, para in enumerate(paragraphs):
        body_parts.append(f"<p>{para}</p>")
        para_num = i + 1
        if para_num in image_layout:
            for _ in range(image_layout[para_num]):
                if img_idx < len(images):
                    body_parts.append(
                        f'<div class="img-wrap"><img src="data:image/jpeg;base64,{images[img_idx]}" /><p class="img-caption">图片来源于网络</p></div>'
                    )
                    img_idx += 1
    # 剩余图片追加到文章末尾
    while img_idx < len(images):
        body_parts.append(
            f'<div class="img-wrap"><img src="data:image/jpeg;base64,{images[img_idx]}" /><p class="img-caption">图片来源于网络</p></div>'
        )
        img_idx += 1
    body = "\n".join(body_parts)
    date_str = datetime.now().strftime("%Y年%m月%d日")
    return HTML_TEMPLATE.format(title=title, date=date_str, body=body)


# ===== 主流程 =====
def main(category="娱乐"):
    config = load_config()
    api_key = config["api_key"]
    model = config.get("model", "deepseek-chat")
    api_url = config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
    output_dir = os.path.join(BASE_DIR, config.get("output_dir", "./output"))
    image_count = config.get("image_count", 3)
    os.makedirs(output_dir, exist_ok=True)

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise RuntimeError("请在 config.json 中填写API Key")

    print(f"[1/5] 获取今日头条热榜（类别：{category}）...")
    session = get_tt_session()
    hot_list = get_toutiao_hot_board(session)
    print(f"  共获取 {len(hot_list)} 条热榜")
    if not hot_list:
        raise RuntimeError("未获取到热榜数据")
    hot = pick_tt_hot_by_category(hot_list, category)
    keyword = hot["word"]
    print(f"  选中：{hot['title']}（排名 {hot['rank']}，分类 {classify_tt_topic(hot)}）")

    print(f"[2/5] DeepSeek改写文章...")
    title, article = rewrite_article(keyword, hot["rank"], api_key, model, api_url)
    print(f"  标题：{title}（{len(title)}字）")
    print(f"  正文：共 {len(article)} 字")

    print("[3/5] 获取配图（头条 → 微博 → 百度）...")
    images, source = fetch_images_unified(
        session, keyword,
        topic_image_url=hot.get("image", ""),
        topic_url=hot.get("url", ""),
        count=image_count
    )
    print(f"  成功处理 {len(images)} 张配图（来源：{source}）")

    print("[4/5] 生成HTML...")
    html = build_html(title, article, images)

    print("[5/5] 保存文件...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tt_hot_{category}_{timestamp}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已保存：{filepath}")
    return filepath


if __name__ == "__main__":
    import sys
    category = sys.argv[1] if len(sys.argv) > 1 else "娱乐"
    main(category)
