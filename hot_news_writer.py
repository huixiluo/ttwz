#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微博热搜改写工具
功能：获取微博热搜 → 智谱GLM改写 → 百度图片搜索配图 → Pillow处理 → 输出HTML
用法：python hot_news_writer.py [娱乐|体育|社会]
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


# ===== 微博访客系统（获取SUB cookie）=====
def get_visitor_session():
    """模拟微博访客系统，返回带SUB cookie的session"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA_PC})

    # 触发访客系统
    session.get("https://s.weibo.com/top/summary", timeout=15)

    # 生成访客tid
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
        raise RuntimeError("访客系统: 获取tid失败")
    tid = json.loads(m.group(1))["data"]["tid"]

    # 用tid换取SUB cookie
    session.get(
        f"https://passport.weibo.com/visitor/visitor?a=incarnate&t={tid}&w=2&c=100"
        f"&gc=&cb=cross_domain&from=weibo&_rand={int(time.time() * 1000)}",
        headers={"Referer": "https://s.weibo.com/"},
        timeout=15,
    )

    if not session.cookies.get("SUB"):
        raise RuntimeError("访客系统: 未获取到SUB cookie")
    return session


# ===== 微博热搜 =====
# 分类热搜API映射（微博官方分类榜单接口）
CATEGORY_API = {
    "娱乐": "https://weibo.com/ajax/statuses/entertainment",
    "体育": "https://weibo.com/ajax/statuses/sport",
    "社会": "https://weibo.com/ajax/statuses/social",
}


def _parse_band_list(band_list, category=""):
    """解析热搜band_list，返回标准化的热搜列表"""
    hot_list = []
    rank_counter = 0
    for item in band_list:
        # 跳过广告
        if item.get("ad_type"):
            continue
        rank_counter += 1
        word = item.get("word", "").strip()
        if not word:
            continue
        hot_list.append({
            "title": word,
            "word": word,
            "rank": item.get("realpos", rank_counter),
            "num": item.get("num", 0),
            "category": item.get("category", category),
            "channel_type": item.get("channel_type", ""),
            "subject_label": item.get("subject_label", ""),
        })
    return hot_list


def get_hotsearch_list(session):
    """获取微博实时热搜总榜（通过hot_band API，含官方分类信息）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://weibo.com/",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = session.get(
        "https://weibo.com/ajax/statuses/hot_band",
        timeout=15, headers=headers
    )
    resp.raise_for_status()
    data = resp.json()
    band_list = data.get("data", {}).get("band_list", [])
    return _parse_band_list(band_list)


def get_hotsearch_by_category(session, category):
    """获取微博分类热搜榜（文娱/体育/社会各50条）
    category: "娱乐" | "体育" | "社会"
    """
    api_url = CATEGORY_API.get(category)
    if not api_url:
        raise ValueError(f"不支持的分类: {category}，可选: {list(CATEGORY_API.keys())}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://weibo.com/",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = session.get(api_url, timeout=15, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    band_list = data.get("data", {}).get("band_list", [])
    return _parse_band_list(band_list, category=category)


# 类别关键词规则
CATEGORY_KEYWORDS = {
    "娱乐": ["明星", "演员", "歌手", "综艺", "剧集", "电视剧", "电影", "演唱会",
             "出道", "代言", "官宣", "粉丝", "偶像", "爱豆", "影帝", "影后",
             "红毯", "颁奖", "娱乐", "剧照", "杀青", "定档", "上映", "票房",
             "选秀", "离婚", "结婚", "恋情", "金鹰", "金鸡", "白玉兰", "春晚",
             # 影视角色/IP
             "蜘蛛侠", "蝙蝠侠", "超人", "漫威", "DC", "超级英雄", "重启",
             "奥特曼", "变形金刚", "哈利波特",
             # 演技/剧集相关
             "演技", "古装", "热播", "御廷谣", "番剧", "动画",
             "声优", "配音",
             # 科技娱乐/AI相关（非纯技术）
             "AI公司", "AI训练", "版权", "书籍销毁", "盗版",
             # 通用娱乐词
             "网红", "直播", "短视频", "热搜", "话题",
             # 票务/演出
             "大麦", "票", "座位图", "巡演", "演出",
             # 综艺/选秀节目
             "浪姐", "披哥", "乘风破浪", "披荆斩棘", "选秀", "练习生",
             # 常见明星名字（按需扩充）
             "王俊凯", "肖战", "黄晓明", "罗正", "宋威龙", "刘耀文",
             "陈伟霆", "陈瑶", "敖瑞鹏", "何与", "施南生", "赞达亚",
             "TF家族", "TF四代", "TFBOYS", "闵塔鲨", "白鹿",
             # 剧集/影视名
             "异人之下", "清明上河园", "生命树", "天才女友"],
    "体育": ["比赛", "联赛", "球员", "冠军", "进球", "赛季", "奥运", "世界杯",
             "NBA", "CBA", "足球", "篮球", "网球", "乒乓", "羽毛球", "游泳",
             "田径", "夺冠", "决赛", "半决赛", "教练", "俱乐部", "转会", "运动员",
             "选手", "金牌", "银牌", "铜牌", "破纪录", "欧洲杯", "亚运会",
             "全运会", "锦标赛", "巡回赛", "公开赛", "德比", "德转",
             "球衣", "球场", "场馆", "积分", "排名赛",
             # 运动员名字
             "张继科", "王楚钦", "马龙", "樊振东", "孙颖莎", "陈梦",
             "全红婵", "苏炳添", "武磊", "郑智",
             # 赛事/体育相关
             "赛事", "解说员", "赛事方", "中超", "国足", "男篮", "女篮",
             "世锦赛", "资格赛", "小组赛", "淘汰赛"],
    "社会": ["警方", "事故", "救援", "市民", "小区", "学校", "学生", "老人",
             "交通", "地铁", "高铁", "天气", "暴雨", "高温", "疫情", "医疗",
             "政策", "法规", "法院", "判决", "见义勇为", "感动", "暖心", "烈士",
             # 灾害
             "地震", "海啸", "坍塌", "倒塌", "火灾", "爆炸", "洪水", "泥石流",
             "台风", "龙卷风", "雪灾",
             # 社会事件
             "退货", "取件码", "快递", "消费者", "维权", "投诉",
             # 科技/产业（非娱乐）
             "芯片", "半导体", "市值", "三星", "海力士", "台积电",
             "新能源", "电动车", "电池", "光伏",
             # 民生/经济
             "银行", "公积金", "房价", "物价", "工资", "就业",
             "供冷", "供暖", "超市", "存包",
             # 国际
             "日本", "韩国", "印度", "美国", "俄罗斯", "泰国", "总理",
             # 军事
             "歼20", "导弹", "军演", "海军", "空军",
             # 其他社会
             "探险队", "登山", "遇难", "谋杀", "日元", "危机"],
}


def classify_hot(item):
    """根据微博API返回的category和channel_type字段判断热搜类别"""
    cat = item.get("category", "")
    ch = item.get("channel_type", "")
    # 娱乐：channel_type为Entertainment，或category属于娱乐子类
    if ch == "Entertainment" or cat in ("艺人", "演出", "综艺", "剧集", "电影", "网红", "艺人,游戏"):
        return "娱乐"
    # 体育：category为体育
    if cat == "体育":
        return "体育"
    # 其他归为社会（民生新闻、情感、财经、互联网、国内时政、军事、海外新闻等）
    return "社会"


def pick_hot_by_category(hot_list, category):
    """按类别筛选热搜，取排名最高的一条"""
    candidates = [h for h in hot_list if classify_hot(h) == category]
    if not candidates:
        candidates = hot_list
    candidates.sort(key=lambda x: x.get("rank", 999))
    return candidates[0]


# ===== 智谱GLM改写 =====
REWRITE_PROMPT = """你是一位有十年经验的媒体编辑，文风接地气，擅长把热点写成让人想读下去的文章。

请根据以下微博热搜话题，撰写一篇约600字的文章，并配一个爆款标题。

【热搜话题】{keyword}
【热搜排名】第{rank}位

【标题要求——非常重要，必须严格执行】
1. 必须是三段式爆款标题，字数不超过25个字（含标点），整体语义完整，不能半截话戛然而止；
2. 三段式结构是硬性要求：标题必须由三个短句/短语组成，用中文逗号分隔，即标题中必须恰好出现两个逗号，分成三段。禁止只写一段、两段或四段。正确示例："明星哭穷上热搜，网友不买账，这届观众清醒了"（两个逗号，三段）；
3. 结合本条资讯的具体内容，从以下两种结构形式中选择更适合的一种来生成标题：
   - 结构A：事件+细节+悬念（先点明事件，再补充一个关键细节，最后用悬念收尾引发好奇）
   - 结构B：现象+冲突+疑问（先描述现象，再点出冲突点，最后用疑问句引发思考）
   选择依据：资讯本身有戏剧性细节时优先用结构A；资讯涉及争议、对立或反差时优先用结构B；
4. 三段要短促有力，每段尽量不超过8个字，节奏感强，像朋友分享时说的话，口语化，不要书面腔；
5. 制造悬念、冲突或反差，让人忍不住想点开看；可用疑问句、数字、对比、情绪词等技巧，但不要标题党骗点击；
6. 不要用"震惊！""速看！""突发！"这类低质标题党词；
7. 标题要和正文内容匹配，不能文不对题；
8. 禁止编造或暗示未经证实的事实，禁止用假设性陈述误导读者（如"某某没拿奖？""某某要退出？"这类无中生有的猜测），疑问句只能基于已公开的事实提问；
9. 标题不得偏向或点名特定人物（正文没偏向某个人，标题也不要只聚焦某一个人），应从事件整体或群体角度切入，保持中立客观；
10. 写完标题后请自查：标题是否恰好有两个逗号、分成三段？若不是，必须改写为符合三段式结构的标题。

【内容要求】
1. 如果你了解该事件的背景，请基于事实进行改写；如果不确定具体细节，请围绕话题主题进行创作，但不得编造虚假信息；
2. 适当补充背景信息（如事件前因、相关背景）或延伸内容（如类似案例），提升文章深度和吸引力；
3. 优化段落结构，每段不超过150字，适当分段提升阅读体验，建议分5-6段，至少5段；
4. 文章整体导向积极正能量，站在读者角度，引发共鸣，让读者看完有想评论的冲动；
5. 全文约600字；
6. 保持中立客观，不得偏向或拉踩特定人物，涉及多人时一视同仁地呈现。

【风格要求——非常重要，必须严格执行】
1. 必须像真人写的，坚决去除AI味。具体做到：
   - 禁止使用"首先/其次/最后/总之/综上所述/不难看出/值得一提的是"这类机械关联词；
   - 禁止使用排比句式堆砌（如"是...也是...更是..."、"不仅...而且...还..."）；
   - 禁止空洞的形容词堆砌（如"令人深思、发人深省、意义深远"）；
   - 禁止每段都用总结句收尾；
2. 多用生活化的表达，像和朋友聊天那样自然。可以适当用口语、俗语、比喻，让文字有温度；
3. 句子长短错落，不要都是长句或都是短句。偶尔用一个很短的句子制造节奏感；
4. 可以带一点个人视角和情绪，比如"说实话""老实讲""说起来"这类自然过渡；
5. 【开头——非常重要，必须严格执行】开头必须自然、多样、有代入感，坚决杜绝AI味和套路化：
   - 严禁使用以下固化开头模式（违反即视为不合格）：
     * "刷到/看到/点开+热搜/榜单/话题"类（如"刷到这条热搜""看到榜单上挂着""点开话题"）；
     * "朋友圈里/群里/评论区"类（如"朋友圈又炸了""群里在转"）；
     * "热搜第X位/挂在热搜"类自我引用榜单排名的表述；
     * "近日""近日来""近日，一则..."这类新闻稿套路；
     * "话说回来""闲来无事"等生硬铺垫。
   - 每篇文章的开头切入方式必须不同，请从以下手法中根据内容选择最贴合的一种，且不要与近期文章重复：
     * 场景切入：用一个具体的生活场景或画面直接开场（如"下班路上刷手机，一条消息弹出来"）；
     * 细节切入：从事件中最抓人的一个细节、一句话、一个动作写起；
     * 反问切入：用一个直击人心的问题开场，引发读者思考；
     * 观点切入：先抛出一个判断或态度，再带出事件；
     * 对比切入：用今昔对比、表里对比制造反差；
     * 故事切入：像讲一个故事那样自然开场，先铺垫再点题；
     * 情绪切入：直接写出一种情绪或感受，让读者共情。
   - 开头要让人一眼觉得"这是个人在写东西"，而不是"机器在凑字数"。开头三句话内必须抓住读者，不要绕弯子铺垫；
6. 绝对禁止使用儿话音！这是硬性要求，违反即视为不合格。任何"X儿"格式的口语化后缀都不允许，包括但不限于：事儿/点儿/地儿/哥们儿/玩意儿/劲儿/味儿/脸儿/份儿/调儿/孩儿/老头儿/聊天儿/慢慢儿/好好儿。必须用规范表达替代（这事→这件事，一点→一点，地方→地方，朋友→朋友，东西→东西，劲头→劲头，味道→味道）。写完后请自查，若出现"儿"字作为词尾后缀，必须改写。

【输出格式——必须严格按此格式】
第一行：标题（不超过25字）
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
    # 标题字数兜底：超过25字时智能截断，保证三段式结构尽量完整
    if len(title) > 25:
        comma_positions = [i for i, c in enumerate(title) if c in '，,']
        truncate_at = 25
        for i in range(25, 17, -1):
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
        # 不合规，重试一次
        print(f"  [标题校验] 第{attempt+1}次生成的标题非三段式：{title}，重试...")
        time.sleep(1)

    # # 后处理：清除儿话音（双保险，DeepSeek未必严格遵守prompt）
    article = clean_erhua(article)
    title = clean_erhua(title)
    return title, article


# ===== 真人文字校准编辑 =====
POLISH_PROMPT = """你是一位真人文字校准编辑。请对以下文章正文进行行文改写。

【改写原则——必须严格执行】
1. 保留全部原文事实、核心观点，不得篡改、删减、编造任何事实信息；
2. 删掉以下内容（发现即删除或改写）：
   - 空洞客套话（如"希望xxx""愿xxx""让我们一起xxx"）；
   - 机械连接词（首先/其次/最后/总之/综上所述/不难看出/值得一提的是）；
   - 华丽排比句（是...也是...更是.../不仅...而且...还...）；
   - 重复的结果性表述（同一段落里反复说同一个意思）；
   - 教科书式的升华总结（如"这不仅是xxx，更是xxx的体现""值得我们每个人深思"）；
3. 调节句子长短节奏，让长短句错落有致，逻辑转折自然不生硬；
4. 允许有轻微不完美，还原普通人真实输出的语感，不要写得像范文或满分作文；
5. 禁止堆砌网络热梗、禁止强行口语化、禁止编造故事或细节；
6. 不要套用别的模板风格，保持原文的整体基调和段落结构，只做行文层面的打磨。

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


# ===== 微博原帖图片搜索 =====
def fetch_images_from_weibo(session, keyword, count=3):
    """从微博搜索结果中提取原帖图片（使用weibo.com AJAX搜索API），返回base64列表"""
    from urllib.parse import quote as url_quote
    images = []
    search_url = (
        f"https://weibo.com/ajax/statuses/search"
        f"?q={url_quote(keyword)}"
    )
    try:
        resp = session.get(search_url, headers={
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
                img_url = (
                    info.get("large", {}).get("url")
                    or info.get("largest", {}).get("url")
                    or info.get("original", {}).get("url")
                    or ""
                )
                if not img_url:
                    continue
                try:
                    img_resp = session.get(img_url, headers={
                        "User-Agent": UA_PC,
                        "Referer": "https://weibo.com/",
                    }, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 2000:
                        b64 = process_image(img_resp.content)
                        images.append(b64)
                        if len(images) >= count:
                            return images
                except Exception:
                    continue
                time.sleep(0.3)
    except Exception:
        pass
    return images


# ===== 百度图片搜索 =====
def fetch_images_baidu(keyword, count=3):
    """通过百度图片搜索获取配图，返回base64列表"""
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
        "rn": 20,
    }
    resp = requests.get(url, params=params, headers={"User-Agent": UA_PC}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("data", [])

    images = []
    for item in items:
        if not isinstance(item, dict):
            continue
        img_url = item.get("thumbURL") or item.get("middleURL") or item.get("hoverURL")
        if not img_url or not img_url.startswith("http"):
            continue
        try:
            img_resp = requests.get(img_url, headers={"User-Agent": UA_PC}, timeout=15)
            if img_resp.status_code == 200 and len(img_resp.content) > 2000:
                b64 = process_image(img_resp.content)
                images.append(b64)
                if len(images) >= count:
                    break
        except Exception:
            continue
        time.sleep(0.3)
    return images


# ===== 图片处理 =====
def process_image(img_bytes):
    """裁剪+滤镜处理图片，返回base64字符串"""
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 居中裁剪为 16:9
    w, h = img.size
    target_ratio = 16 / 9
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    # 限制最大宽度，保持清晰
    if img.width > 800:
        ratio = 800 / img.width
        img = img.resize((800, int(img.height * ratio)), Image.LANCZOS)

    # 滤镜：增强对比度+锐度+色彩饱和度
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Sharpness(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.08)
    # 轻微锐化提升清晰度
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=80, threshold=2))

    # 转base64
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
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
<div class="footer">本文基于微博热搜改写，配图经二次处理</div>
</body>
</html>"""


def build_html(title, article_text, images):
    """生成HTML内容，图片布局：第1段后1张、第3段后2张、第5段后2张"""
    paragraphs = [p.strip() for p in article_text.split("\n") if p.strip()]
    body_parts = []
    img_idx = 0
    # 图片布局规则：{段落号: 图片数量}
    image_layout = {1: 1, 3: 2, 5: 2}
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

    print(f"[1/5] 获取微博热搜（类别：{category}）...")
    session = get_visitor_session()
    hot_list = get_hotsearch_list(session)
    print(f"  共获取 {len(hot_list)} 条热搜")
    if not hot_list:
        raise RuntimeError("未获取到热搜数据")
    hot = pick_hot_by_category(hot_list, category)
    keyword = hot["word"]
    print(f"  选中：{hot['title']}（排名 {hot['rank']}）")

    print(f"[2/5] DeepSeek改写文章...")
    title, article = rewrite_article(keyword, hot["rank"], api_key, model, api_url)
    print(f"  标题：{title}（{len(title)}字）")
    print(f"  正文：共 {len(article)} 字")

    print("[3/5] 获取配图（优先微博原帖素材）...")
    images = fetch_images_from_weibo(session, keyword, count=image_count)
    source = "微博原帖"
    if len(images) < image_count:
        remaining = image_count - len(images)
        fallback = fetch_images_baidu(keyword, count=remaining)
        images.extend(fallback)
        if fallback:
            source = f"微博原帖({len(images)-len(fallback)}张) + 百度({len(fallback)}张)"
    print(f"  成功处理 {len(images)} 张配图（来源：{source}）")

    print("[4/5] 生成HTML...")
    html = build_html(title, article, images)

    print("[5/5] 保存文件...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"hot_{category}_{timestamp}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已保存：{filepath}")
    return filepath


if __name__ == "__main__":
    import sys
    category = sys.argv[1] if len(sys.argv) > 1 else "娱乐"
    main(category)
