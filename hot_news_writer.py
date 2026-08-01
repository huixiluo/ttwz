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
def get_hotsearch_list(session):
    """获取微博实时热搜榜（通过s.weibo.com解析HTML）"""
    resp = session.get("https://s.weibo.com/top/summary", timeout=15)
    resp.raise_for_status()

    # 解析热搜: <a href="/weibo?q=...&band_rank=N&Refer=top">标题</a>
    pattern = re.compile(
        r'<a\s+href="(/weibo\?q=[^"]*band_rank=\d+[^"]*)"[^>]*>([^<]+)</a>'
    )
    hot_list = []
    for match in pattern.finditer(resp.text):
        link, title = match.group(1), match.group(2).strip()
        # 提取热度值
        rank_m = re.search(r'band_rank=(\d+)', link)
        rank = int(rank_m.group(1)) if rank_m else 0
        # 提取搜索词
        q_m = re.search(r'q=([^&]+)', link)
        word = quote(q_m.group(1)) if q_m else title
        hot_list.append({
            "title": title,
            "word": title,  # 用标题作为搜索词
            "rank": rank,
            "num": 0,
        })

    # 尝试提取热度数值
    hot_nums = re.findall(
        r'<td class="td-02"[^>]*>.*?<span>([\d.万]+)</span>', resp.text, re.DOTALL
    )
    for i, num in enumerate(hot_nums):
        if i < len(hot_list):
            hot_list[i]["num"] = num

    return hot_list


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
             "演技", "古装", "热播", "御廷谣", "剧照", "番剧", "动画",
             "番剧", "声优", "配音",
             # 科技娱乐/AI相关（非纯技术）
             "AI公司", "AI训练", "版权", "书籍销毁", "盗版",
             # 通用娱乐词
             "网红", "直播", "短视频", "热搜", "话题"],
    "体育": ["比赛", "联赛", "球员", "冠军", "进球", "赛季", "奥运", "世界杯",
             "NBA", "CBA", "足球", "篮球", "网球", "乒乓", "羽毛球", "游泳",
             "田径", "夺冠", "决赛", "半决赛", "教练", "俱乐部", "转会", "运动员",
             "选手", "金牌", "银牌", "铜牌", "破纪录", "欧洲杯", "亚运会",
             "全运会", "锦标赛", "巡回赛", "公开赛", "德比", "德转",
             "球衣", "球场", "场馆", "赛季", "积分", "排名赛"],
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
             "新能源", "电动车", "电池", "光伏"],
}


def classify_hot(item):
    """根据关键词判断热搜类别"""
    text = item.get("title", "") + item.get("word", "")
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return cat
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

【标题要求——非常重要：三段式爆款标题】
标题必须采用三段式结构，用逗号分隔，字数不超过25个字（含标点）。

结构形式（根据原资讯内容灵活选择）：
- 事件+细节+悬念：适合有明确事件经过的资讯，第一句概括事件，第二句补充细节，第三句制造悬念
- 现象+冲突+疑问：适合社会现象或争议话题，第一句描述现象，第二句制造冲突/反差，第三句用疑问句收尾
请结合原资讯内容，从以上两种结构中自动选择更适合的一种来生成标题。

具体说明：
1. 三段加起来总字数不超过25字（含两个逗号），每段都是语义完整的小句，不能半截话戛然而止；
2. 口语化，像朋友分享时说的话，不要书面腔；
3. 不要用"震惊！""速看！""突发！"这类低质标题党词；
4. 标题要和正文内容匹配，不能文不对题；
5. 禁止编造或暗示未经证实的事实，疑问句只能基于已公开的事实提问；
6. 标题不得偏向或点名特定人物，应从事件整体或群体角度切入，保持中立客观。

示例：
- 深夜通告刷屏了，品牌方连夜道歉，这态度你接受吗？
- 录取通知书玩出新花样，AR扫出校史，你被惊艳到了吗？

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
5. 开头不要用"近日""近日来""近日，一则..."这类套路开头，换个更有代入感的切入方式；
6. 绝对禁止使用儿话音！这是硬性要求，违反即视为不合格。任何"X儿"格式的口语化后缀都不允许，包括但不限于：事儿/点儿/地儿/哥们儿/玩意儿/劲儿/味儿/脸儿/份儿/调儿/孩儿/老头儿/聊天儿/慢慢儿/好好儿。必须用规范表达替代（这事→这件事，一点→一点，地方→地方，朋友→朋友，东西→东西，劲头→劲头，味道→味道）。写完后请自查，若出现"儿"字作为词尾后缀，必须改写。

【输出格式——必须严格按此格式】
第一行：三段式标题，用逗号分隔（不超过25字）
第二行：空行
第三行开始：文章正文，段落之间用空行分隔。
不要加"标题："等前缀，不要加任何额外说明。"""


def rewrite_article(keyword, rank, api_key, model, api_url=None):
    """调用LLM改写文章（DeepSeek兼容OpenAI格式），返回 (标题, 正文)"""
    url = api_url or "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = REWRITE_PROMPT.format(keyword=keyword, rank=rank)
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

    # 解析标题和正文：第一行为标题，空行后为正文
    lines = content.split("\n")
    title = lines[0].strip() if lines else keyword
    # 去掉标题前缀（如"标题："）
    title = re.sub(r'^(标题[:：]\s*)', '', title)
    # 标题字数兜底：超过25字时，在标点处智能截断，保证语义完整
    if len(title) > 25:
        # 在第18-25字之间找最后一个标点符号进行截断
        truncate_at = 25
        for i in range(25, 17, -1):
            if i < len(title) and title[i-1] in '，。！？、；：,.;:!?':
                truncate_at = i
                break
        title = title[:truncate_at]

    # 正文：跳过标题和紧随的空行
    body_start = 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    article = "\n".join(lines[body_start:]).strip()
    if not article:
        article = content  # 兜底
    # 后处理：清除儿话音（双保险，DeepSeek未必严格遵守prompt）
    article = clean_erhua(article)
    title = clean_erhua(title)
    return title, article


# 儿话音替换表（覆盖常见口语后缀，"儿"作为词尾时替换）
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
    line-height: 1.6;
    letter-spacing: 0.5px;
  }}
  h1 .seg {{
    display: inline;
  }}
  h1 .seg.seg-1 {{
    color: #1a1a1a;
    font-weight: 700;
  }}
  h1 .seg.seg-2 {{
    color: #444;
    font-weight: 500;
  }}
  h1 .seg.seg-3 {{
    color: #d4380d;
    font-weight: 600;
  }}
  h1 .sep {{
    color: #bbb;
    margin: 0 2px;
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
<h1>{title_html}</h1>
<div class="meta">{date} &middot; 热点改写</div>
{body}
<div class="footer">本文基于微博热搜改写，配图经二次处理</div>
</body>
</html>"""


def build_html(title, article_text, images):
    """生成HTML内容，图片布局：第1段后1张、第3段后2张、第5段后2张"""
    # 将三段式标题拆分为独立段落，分别渲染
    title_segs = [s.strip() for s in title.split("，")]
    if len(title_segs) >= 3:
        title_html = (
            f'<span class="seg seg-1">{title_segs[0]}</span>'
            f'<span class="sep">，</span>'
            f'<span class="seg seg-2">{title_segs[1]}</span>'
            f'<span class="sep">，</span>'
            f'<span class="seg seg-3">{title_segs[2]}</span>'
        )
    else:
        title_html = title
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
    return HTML_TEMPLATE.format(title=title, title_html=title_html, date=date_str, body=body)


# ===== 主流程 =====
def generate_one(session, hot_list, category, config):
    """生成单篇文章，返回文件路径"""
    api_key = config["api_key"]
    model = config.get("model", "deepseek-chat")
    api_url = config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
    output_dir = os.path.join(BASE_DIR, config.get("output_dir", "./output"))
    image_count = config.get("image_count", 3)
    os.makedirs(output_dir, exist_ok=True)

    hot = pick_hot_by_category(hot_list, category)
    keyword = hot["word"]
    print(f"  选中：{hot['title']}（排名 {hot['rank']}）")

    print(f"  [2/5] DeepSeek改写文章...")
    title, article = rewrite_article(keyword, hot["rank"], api_key, model, api_url)
    print(f"  标题：{title}（{len(title)}字）")
    print(f"  正文：共 {len(article)} 字")

    print(f"  [3/5] 获取配图（优先微博原帖素材）...")
    images = fetch_images_from_weibo(session, keyword, count=image_count)
    source = "微博原帖"
    if len(images) < image_count:
        remaining = image_count - len(images)
        fallback = fetch_images_baidu(keyword, count=remaining)
        images.extend(fallback)
        if fallback:
            source = f"微博原帖({len(images)-len(fallback)}张) + 百度({len(fallback)}张)"
    print(f"  成功处理 {len(images)} 张配图（来源：{source}）")

    print(f"  [4/5] 生成HTML...")
    html = build_html(title, article, images)

    print(f"  [5/5] 保存文件...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"hot_{category}_{timestamp}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已保存：{filepath}")
    return filepath


def main(category="娱乐", count=1):
    config = load_config()
    api_key = config["api_key"]

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise RuntimeError("请在 config.json 中填写API Key")

    # 确定类别列表：如果指定了具体类别，全部用该类别；否则按类别均匀分配
    ALL_CATEGORIES = ["娱乐", "社会", "体育"]
    if category in ALL_CATEGORIES:
        categories = [category] * count
    else:
        # 按轮次均匀分配：娱乐→社会→体育→娱乐→...
        categories = [ALL_CATEGORIES[i % 3] for i in range(count)]

    print(f"共需生成 {count} 篇文章，类别分配：{' → '.join(categories)}")
    print(f"[1/5] 获取微博热搜...")
    session = get_visitor_session()
    hot_list = get_hotsearch_list(session)
    print(f"  共获取 {len(hot_list)} 条热搜")
    if not hot_list:
        raise RuntimeError("未获取到热搜数据")

    results = []
    for i, cat in enumerate(categories):
        print(f"\n{'='*50}")
        print(f"第 {i+1}/{count} 篇（类别：{cat}）")
        print(f"{'='*50}")
        filepath = generate_one(session, hot_list, cat, config)
        results.append(filepath)
        if i < count - 1:
            time.sleep(2)  # 避免API限流

    print(f"\n全部完成！共生成 {len(results)} 篇文章：")
    for fp in results:
        print(f"  {fp}")
    return results[0] if len(results) == 1 else results


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    # 解析参数：支持 "python hot_news_writer.py [类别|数量] [数量]"
    category = "娱乐"
    count = 1

    if args:
        first = args[0]
        if first.isdigit():
            count = int(first)
        else:
            category = first
            if len(args) > 1 and args[1].isdigit():
                count = int(args[1])

    main(category, count)
