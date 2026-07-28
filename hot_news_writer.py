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
             # 演技/剧集相关
             "演技", "古装", "热播", "御廷谣", "赵昭仪",
             # 科技娱乐/AI相关（AI训练用书、版权争议等娱乐产业话题）
             "AI公司", "AI训练", "版权", "书籍销毁", "盗版"],
    "体育": ["比赛", "联赛", "球员", "冠军", "进球", "赛季", "奥运", "世界杯",
             "NBA", "CBA", "足球", "篮球", "网球", "乒乓", "羽毛球", "游泳",
             "田径", "夺冠", "决赛", "半决赛", "教练", "俱乐部", "转会", "运动员",
             "选手", "金牌", "银牌", "铜牌", "破纪录"],
    "社会": ["警方", "事故", "救援", "市民", "小区", "学校", "学生", "老人",
             "交通", "地铁", "高铁", "天气", "暴雨", "高温", "疫情", "医疗",
             "政策", "法规", "法院", "判决", "见义勇为", "感动", "暖心", "烈士"],
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

请根据以下微博热搜话题，撰写一篇600到1000字的文章，并配一个三段式爆款标题。

【热搜话题】{keyword}
【热搜排名】第{rank}位

【标题要求——非常重要】
1. 必须是三段式爆款标题，字数不超过25个字（含标点）；
2. 三段式结构：标题由三个短句/短语组成，用逗号分隔，形成"事件+细节+悬念"或"现象+冲突+疑问"的节奏感结构。示例："票房破十亿，口碑却两极，这片到底值不值"、"提名名单一出，老戏骨齐聚，谁能笑到最后"；
3. 每段简短有力，三段层层递进，最后一段制造悬念或抛出疑问，让人忍不住想点开看；
4. 可用数字、对比、情绪词等技巧，但不要标题党骗点击；
5. 口语化，像朋友分享时说的话，不要书面腔；
6. 不要用"震惊！""速看！""突发！"这类低质标题党词；
7. 标题要和正文内容匹配，不能文不对题；
8. 禁止编造或暗示未经证实的事实，禁止用假设性陈述误导读者（如"某某没拿奖？""某某要退出？"这类无中生有的猜测），疑问句只能基于已公开的事实提问；
9. 标题不得偏向或点名特定人物（正文没偏向某个人，标题也不要只聚焦某一个人），应从事件整体或群体角度切入，保持中立客观。

【内容要求】
1. 如果你了解该事件的背景，请基于事实进行改写；如果不确定具体细节，请围绕话题主题进行创作，但不得编造虚假信息；
2. 适当补充背景信息（如事件前因、相关背景）或延伸内容（如类似案例），提升文章深度和吸引力；
3. 优化段落结构，每段不超过150字，适当分段提升阅读体验，建议分4-5段；
4. 文章整体导向积极正能量，站在读者角度，引发共鸣，让读者看完有想评论的冲动；
5. 全文600到1000字；
6. 保持中立客观，不得偏向或拉踩特定人物，涉及多人时一视同仁地呈现。

【风格要求——非常重要，必须严格执行】
1. 必须像真人写的，坚决去除AI味。具体做到：
   - 禁止使用"首先/其次/最后/总之/综上所述/不难看出/值得一提的是"这类机械关联词；
   - 禁止使用排比句式堆砌（如"是...也是...更是..."、"不仅...而且...还..."）；
   - 禁止空洞的形容词堆砌（如"令人深思、发人深省、意义深远"）；
   - 禁止每段都用总结句收尾；
2. 多用生活化的表达，像和朋友聊天那样自然。可以适当用口语、俗语、比喻，让文字有温度；
3. 句子长短错落，不要都是长句或都是短句。偶尔用一个很短的句子制造节奏感；
4. 可以带一点个人视角和情绪，比如"说实话""老实讲""这事儿说起来"这类自然过渡；
5. 开头不要用"近日""近日来""近日，一则..."这类套路开头，换个更有代入感的切入方式。

【输出格式——必须严格按此格式】
第一行：三段式标题（不超过25字，用逗号分隔三段）
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
    # 标题字数兜底：超过25字截断
    if len(title) > 25:
        title = title[:25]

    # 正文：跳过标题和紧随的空行
    body_start = 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    article = "\n".join(lines[body_start:]).strip()
    if not article:
        article = content  # 兜底
    return title, article


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
    """生成HTML内容

    图片布局：第一段后插1张图，之后每两段插2张图。
    """
    paragraphs = [p.strip() for p in article_text.split("\n") if p.strip()]
    body_parts = []
    img_idx = 0

    def add_images(count):
        nonlocal img_idx
        for _ in range(count):
            if img_idx < len(images):
                body_parts.append(
                    f'<div class="img-wrap"><img src="data:image/jpeg;base64,{images[img_idx]}" /></div>'
                )
                img_idx += 1

    for i, para in enumerate(paragraphs):
        body_parts.append(f"<p>{para}</p>")
        para_num = i + 1
        if para_num == 1:
            # 第一段后插1张图
            add_images(1)
        elif para_num % 2 == 1:
            # 之后每两段（第3、5、7...段后）插2张图
            add_images(2)

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
    image_count = config.get("image_count", 5)
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

    print("[3/5] 百度图片搜索获取配图...")
    images = fetch_images_baidu(keyword, count=image_count)
    print(f"  成功处理 {len(images)} 张配图")

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
