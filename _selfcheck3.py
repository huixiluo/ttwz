# -*- coding: utf-8 -*-
"""上传前自检（文字维度A+B）：开头禁用模式、AI味连接词、排比堆叠、空泛形容词、
儿化音、段落长度、字数、结尾模板。全部通过则允许进入标题候选/上传环节。"""
import json
import re
import sys

BANNED_CONNECTORS = [
    "首先", "其次", "最后", "总之", "综上所述", "总而言之",
    "不难看出", "值得一提的是", "同时", "然而", "但是",
]
BANNED_OPENING = [
    r"(刷到|看到|点开)[^，。！？]{0,6}(热搜|榜单|话题)",
    r"朋友圈里|群里|评论区",
    r"热搜第[一二三四五六七八九十0-9]+位",
    r"近日来|近日",
    r"话说回来|闲来无事",
]
BANNED_ADJ = ["令人深思", "发人深省", "意义深远"]
BANNED_PARALLEL = [
    r"是.{1,12}也是.{1,12}更是", r"不仅.{1,12}而且.{1,12}还",
]
BANNED_ENDING = [
    r"评论区聊聊|评论区说说|评论区聊|欢迎留言讨论|大家怎么看呢|说说你的观点",
    r"这不仅.{1,10}更是.{1,10}的体现", r"时间会给出答案",
]

with open("_manual_articles.json", "r", encoding="utf-8") as f:
    arts = json.load(f)

all_pass = True
for i, a in enumerate(arts, 1):
    title, article = a["title"], a["article"]
    paras = [p for p in article.split("\n") if p.strip()]
    opening = paras[0]
    ending = paras[-1]
    fails = []

    # --- 维度A：开头 ---
    # A1/A5 禁用模式（检查前三段）
    head = "\n".join(paras[:3])
    for pat in BANNED_OPENING:
        m = re.search(pat, head)
        if m:
            fails.append(f"A1/A5 开头含禁用模式：{m.group(0)}")
    for w in BANNED_CONNECTORS:
        if w in head:
            fails.append(f"A5 开头含连接词：{w}")
    # A1 单句成段检查：首段至少2句（以句号/问号/感叹号/分号计）
    sent_count = len([s for s in re.split(r"[。！？；]", opening) if s.strip()])
    if sent_count < 2:
        fails.append(f"A1 首段仅{sent_count}句（须2句以上）")
    # A6 开头儿化音
    if re.search(r"[\u4e00-\u9fa5]儿[\s，。！？]", opening):
        fails.append("A6 开头疑似儿化音")

    # --- 维度B：全文 ---
    # B1 连接词/过渡词（"最后"仅在句首+逗号时视为连接词，"最后一次"为正常用法）
    for w in BANNED_CONNECTORS:
        if w == "最后":
            if re.search(r"(?:^|[。！？\n])\s*最后[，。]", article):
                fails.append("B1 含连接词：最后（句首）")
        elif w in article:
            fails.append(f"B1 含连接词：{w}")
    # B2 排比堆叠
    for pat in BANNED_PARALLEL:
        m = re.search(pat, article)
        if m:
            fails.append(f"B2 排比堆叠：{m.group(0)}")
    # B3 空泛形容词
    for w in BANNED_ADJ:
        if w in article:
            fails.append(f"B3 空泛形容词：{w}")
    # B4 结尾模板
    for pat in BANNED_ENDING:
        m = re.search(pat, ending)
        if m:
            fails.append(f"B4 结尾模板：{m.group(0)}")
    # B5 字数
    if len(article) <= 600:
        fails.append(f"B5 字数不足600（{len(article)}）")
    # B8 段落长度（平均<=150字）
    long_paras = [p for p in paras if len(p) > 200]
    if long_paras:
        fails.append(f"B8 超长段落 {len(long_paras)} 段（>200字）")
    # B9 儿化音（全篇）
    erhua_hits = re.findall(r"[\u4e00-\u9fa5]儿(?:[\s，。！？；]|$)", article)
    if erhua_hits:
        fails.append(f"B9 疑似儿化音：{erhua_hits}")
    # 标题三段式
    if not (title.count("，") == 2 and len(title) <= 30):
        fails.append(f"标题不合规（逗号{title.count('，')}个，{len(title)}字）")

    status = "PASS" if not fails else "FAIL"
    if fails:
        all_pass = False
    print(f"[{i}] {a['keyword']} -> {status}（{len(article)}字，{len(paras)}段）")
    for fl in fails:
        print(f"    - {fl}")

print()
print("=" * 60)
print("自检结果：" + ("全部通过 PASS" if all_pass else "存在未通过项 FAIL"))
sys.exit(0 if all_pass else 1)
