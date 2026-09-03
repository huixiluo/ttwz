#!/usr/bin/env python3 -*-
"""创作罐头选题 → 确认 → 素材 → 撰写 → 自检 → 配图 → 标题候选 → 上传草稿箱

分阶段执行，含两道强制人工确认关卡（参照 skill 规则）：

关卡1（选题确认）: topics 列出候选后必须停下，用户 confirm 后才能进入后续阶段
关卡2（标题挑选）: generate 产出文章后必须走 title_candidates.py 生成候选并由用户
                   挑选 apply，upload 阶段检测到候选流程未走完会拒绝上传

用法:
  python batch_n_tt_pipeline.py topics [每类条数]  # [1] 抓创作罐头选题，每类列出3条候选（默认）
  python batch_n_tt_pipeline.py confirm 1,4,7     # [关卡1] 用户按序号确认选题（all=全部）
  python batch_n_tt_pipeline.py material        # [2] 打开原文页提取真实素材（浏览器）
  python batch_n_tt_pipeline.py generate        # [4] 校验 _pipeline_articles.json →
                                                 #     自检 → 配图 → HTML/封面/manifest
  python batch_n_tt_pipeline.py upload          # [6] 上传草稿箱（校验标题已挑选，真实保存验证）

撰写规则（编辑直写模式，无 DeepSeek）：
- 文章由助手基于 material 阶段提取的真实原文撰写，写入 _pipeline_articles.json
  （list 格式，自带 category/keyword/title/article，keyword 与选题搜索词一致）
- generate 阶段做代码级自检：三段式标题(20-30字/每段≤10字，填满事件+人物+悬念)、正文650-750字、6-8段、每段≤150字、
  开头禁模板(刷到热搜/近日/单句成段)、结尾禁"评论区聊聊"等互动尾巴、
  禁连接词(然而/但是/首先/总之...)、禁排比堆叠、儿化音清洗、开头/结尾批内不重复
- 平台合规自检（依据头条「首发激励计划」规则，baike 242/566）：
  P-标题: 禁夸张悬念式标题词（真相来了/你怎么看/看完惊呆等，平台认定为套路模板化发文）
  P-原创: 与素材原文的10字连续重合率≤25%（防洗稿/大篇幅引用，平台认定为非原创）
  P-罗列: 禁信息罗列式段落（顿号枚举≥4项且无完整句，平台认定为低成本创作）
  P-批标题: 批内标题禁共用相同句段（平台认定的固定化格式发文）
- 撰写纪律：须有个人观点/分析段落（非纯事件复述）；事实细节只取素材内信息，禁捏造；
  选题源已限1天内发布（满足平台"首发时效"要求）
- 任一项不过关 → 打印失败明细并退出，不产出 manifest，不进入上传
- 上传保存以服务端响应为准（XHR 捕获 article/publish 返回 code==0），
  并在浏览器关闭后用 draft_list API 复核，不再无条件报成功
"""
import os, re, json, time, base64, sys, difflib
from DrissionPage import ChromiumPage, ChromiumOptions
import requests

import toutiao_hot_writer as ttw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
STATE_FILE = os.path.join(BASE_DIR, "_pipeline_state.json")
MATERIAL_MD = os.path.join(BASE_DIR, "_pipeline_material.md")
ARTICLES_FILE = os.path.join(BASE_DIR, "_pipeline_articles.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
MANIFEST_FILE = os.path.join(OUTPUT_DIR, "batch_manifest_tt.json")
CANDIDATES_FILE = os.path.join(OUTPUT_DIR, "title_candidates.json")
IMAGE_COUNT = 5


def dlog(msg):
    print(f"  [{time.strftime('%H:%M:%S')}] {msg}")


def print_usage():
    print(__doc__)


def load_state():
    if not os.path.exists(STATE_FILE):
        raise FileNotFoundError("未找到 _pipeline_state.json，请先运行: python batch_n_tt_pipeline.py topics")
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ===== 话题去重 =====
def bigrams(s):
    return set(s[i:i+2] for i in range(len(s)-1))


def is_similar_topic(a, b, ratio_threshold=0.3, bigram_threshold=0.5):
    if not a or not b:
        return False
    if a == b:
        return True
    seq = difflib.SequenceMatcher(None, a, b)
    if seq.ratio() > ratio_threshold:
        return True
    ba, bb = bigrams(a), bigrams(b)
    if ba and bb:
        overlap = len(ba & bb) / min(len(ba), len(bb))
        if overlap > bigram_threshold:
            return True
    return False


def pick_distinct(hot_list, count):
    selected = []
    for item in hot_list:
        if len(selected) >= count:
            break
        if any(is_similar_topic(item.get("word", ""), s.get("word", "")) for s in selected):
            continue
        selected.append(item)
    return selected


# ===== 浏览器 =====
def open_page():
    co = ChromiumOptions()
    chrome_path = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
    if os.path.exists(chrome_path):
        co.set_browser_path(chrome_path)
        co.headless()
    else:
        # Windows本地用可见Edge：头条风控会拒绝headless浏览器的保存请求(7050保存失败)
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_path):
            co.set_browser_path(edge_path)
    co.auto_port()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    page = ChromiumPage(co)
    page.get("https://mp.toutiao.com")
    time.sleep(2)
    cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
    for name, value in cookies.items():
        try:
            page.set.cookies({"name": name, "value": str(value), "domain": ".toutiao.com", "path": "/"})
        except Exception:
            pass
    page.get("https://mp.toutiao.com")
    time.sleep(3)
    print(f"  登录: {page.url}")
    return page


# ===== [1] 选题 =====
# 按用户要求 2026-09-03 起只抓娱乐/体育，不再获取时政社会类话题
FETCH_CATEGORIES = ("娱乐", "体育")


def fetch_topics(per_category=3):
    session = ttw.get_tt_session()
    topics = []
    try:
        import czgts_source
        czgts_lists = czgts_source.fetch_czgts_low_fans()
        for cat in FETCH_CATEGORIES:
            picked = pick_distinct(czgts_lists.get(cat) or [], per_category)
            topics.extend(picked)
        if not topics:
            raise RuntimeError("创作罐头无可用选题")
        print("  选题来源: 创作罐头·低粉爆款（今日头条/文章/粉丝<1万/发布时间1天内/阅读量降序）")
        print("  类别: 娱乐/体育（时政社会类不抓取）")
    except Exception as e:
        print(f"  创作罐头失败({str(e)[:100]})，回退头条热榜")
        hot_list = ttw.get_toutiao_hot_board(session)
        print(f"  共获取 {len(hot_list)} 条热榜")
        for cat in FETCH_CATEGORIES:
            cat_items = [t for t in hot_list if ttw.classify_tt_topic(t) == cat]
            topics.extend(pick_distinct(cat_items, per_category))
    return topics


def cmd_topics(per_category=3):
    print("=" * 60)
    print(f"[1] 获取资讯选题（创作罐头低粉爆款，每类 {per_category} 条候选）")
    print("=" * 60)
    topics = fetch_topics(per_category)
    current_cat = None
    print(f"\n候选选题共 {len(topics)} 条（每类{per_category}条，等待确认，确认前不会写文章）:")
    for i, t in enumerate(topics, 1):
        cat = t.get("czgts_category") or ttw.classify_tt_topic(t)
        if cat != current_cat:
            current_cat = cat
            print(f"\n  —— {cat} ——")
        if t.get("source") == "czgts":
            print(f"  [{i}] {t['word']}（阅读{t.get('num', '?')} 粉丝{t.get('fans', '?')}）")
            print(f"       原文: {t['title'][:44]}")
            print(f"       发布: {t.get('publishTime', '?')}")
        else:
            print(f"  [{i}] {t['word']}（热度{t.get('num', '?')}）")
    save_state({"stage": "topics", "topics": topics, "confirmed": [], "material": {}})
    print("\n>>> 关卡1：每类挑选（可换条/去掉，一般每类选1条）")
    print("    确认方式: python batch_n_tt_pipeline.py confirm 1,4,7（按序号）")
    print("    确认后:   python batch_n_tt_pipeline.py material")


def cmd_confirm(sel):
    state = load_state()
    if state.get("stage") != "topics":
        raise RuntimeError("当前状态不是待确认选题，请先运行 topics")
    topics = state["topics"]
    if sel.strip().lower() == "all":
        idx = list(range(1, len(topics) + 1))
    else:
        idx = [int(x) for x in re.split(r"[，,\s]+", sel.strip()) if x]
    for i in idx:
        if not (1 <= i <= len(topics)):
            raise ValueError(f"选题序号越界: {i}（共 {len(topics)} 条）")
    confirmed = [topics[i - 1] for i in idx]
    state["confirmed"] = confirmed
    state["stage"] = "confirmed"
    save_state(state)
    print(f"已确认 {len(confirmed)} 条选题:")
    for t in confirmed:
        print(f"  [{t.get('czgts_category') or ttw.classify_tt_topic(t)}] {t['word']}")
    print("\n下一步: python batch_n_tt_pipeline.py material")


# ===== [2] 素材（真实原文，替代旧模板撰写路径） =====
def fetch_material_from_article(page, url):
    """打开原文页提取正文段落文字（选择器逻辑与配图原文层一致）"""
    if not url or not str(url).startswith("http"):
        return None
    try:
        page.get(url)
    except Exception:
        return None
    time.sleep(4)
    try:
        page.run_js("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(1)
    except Exception:
        pass
    js = """
    return (function(){
        var sels = ['article', '.article-content', '.syl-article-base', '.tt-article'];
        var scope = null, best = 0;
        for (var i = 0; i < sels.length; i++) {
            var el = document.querySelector(sels[i]);
            if (el) { var t = (el.innerText || '').length; if (t > best) { best = t; scope = el; } }
        }
        if (!scope) scope = document.body;
        var h1 = document.querySelector('h1');
        var paras = [];
        scope.querySelectorAll('p').forEach(function(p){
            var s = (p.innerText || '').trim().replace(/\\s+/g, ' ');
            if (s.length > 12 && s.length < 500 && paras.indexOf(s) === -1) paras.push(s);
        });
        return JSON.stringify({title: h1 ? h1.innerText.trim() : '', paras: paras.slice(0, 40)});
    })();
    """
    try:
        raw = page.run_js(js)
        data = json.loads(raw) if raw else {}
    except Exception:
        return None
    paras = [p for p in data.get("paras", []) if p]
    text = "\n".join(paras)[:3500]
    if len(text) < 100:
        return None
    return {"title": data.get("title", ""), "text": text, "para_count": len(paras)}


def cmd_material():
    state = load_state()
    if not state.get("confirmed"):
        raise RuntimeError("选题未确认，请先运行 confirm")
    print("=" * 60)
    print("[2] 提取原文素材（浏览器打开原文页）")
    print("=" * 60)
    page = open_page()
    material = state.get("material", {})
    confirmed = state["confirmed"]
    md_lines = ["# 原文素材（供撰写参考）\n"]
    try:
        for i, t in enumerate(confirmed):
            kw = t["word"]
            print(f"\n[{i+1}/{len(confirmed)}] {kw}")
            print(f"  原文链接: {t.get('url', '')[:70]}")
            m = fetch_material_from_article(page, t.get("url", ""))
            if m:
                material[kw] = m
                print(f"  素材: {m['para_count']} 段, {len(m['text'])} 字")
                print(f"  原文标题: {m['title'][:40]}")
                if len(m["text"]) < 500:
                    print(f"  [提示] 素材偏薄（{len(m['text'])}字 < 500），撰写时注意事实边界")
                md_lines.append(f"\n## [{i+1}] {kw}\n\n原文标题: {m['title']}\n原文链接: {t.get('url', '')}\n\n{m['text']}\n")
            else:
                print("  素材: 提取失败（正文太短或页面未渲染）")
                md_lines.append(f"\n## [{i+1}] {kw}\n\n（素材提取失败）\n")
    finally:
        page.quit()
    state["material"] = material
    state["stage"] = "material"
    save_state(state)
    with open(MATERIAL_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    ok = sum(1 for t in confirmed if material.get(t["word"]))
    print(f"\n素材就绪: {ok}/{len(confirmed)} 条选题有真实原文素材")
    print(f"素材全文: {MATERIAL_MD}")
    print("\n下一步: 助手基于素材撰写 _pipeline_articles.json，然后运行 generate")


# ===== [4] 自检 + 配图 + HTML/manifest =====
BANNED_CONNECTORS = ["首先", "其次", "最后", "总之", "综上所述", "总而言之",
                     "不难看出", "值得一提的是", "同时", "然而", "但是",
                     "话说回来", "闲来无事", "近日"]
ENDING_BANNED = ["评论区", "留言", "欢迎讨论", "怎么看呢", "说说你的",
                 "总的来说", "时间会给出答案", "大家怎么看"]
OPENING_PATTERNS = [
    r"(刷到|看到|点开)[^。]{0,8}(热搜|榜单|话题)",
    r"^(朋友圈里|群里)",
    r"热搜第",
    r"^近日",
]
PARALLEL_PATTERNS = [r"不仅.{2,20}更是", r"是.{2,15}也是.{2,15}更是", r"不仅.{2,20}而且.{2,20}还"]

# 头条「首发激励计划」：套路模板化发文禁"夸张悬念式标题"等固定化格式
TITLE_CLICKBAIT = ["真相来了", "你怎么看", "你怎么想", "怎么回事", "看完惊呆", "惊呆了",
                   "太吓人", "不敢相信", "网友炸锅", "全网沸腾", "惊人一幕", "太离谱",
                   "细思极恐", "大揭秘", "内幕曝光", "太不可思议", "全网震惊"]
SHINGLE_LEN = 10          # 洗稿检测的连续字串长度
SHINGLE_MAX_RATIO = 0.25  # 与素材重合率上限（超过即大篇幅引用/洗稿风险）


def _shingle_ratio(article, material):
    """正文与素材的 n 字连续重合率（标点空白归一后），防洗稿/大篇幅引用"""
    norm = lambda s: re.sub(r"[\s，。！？、；：""''（）,.:;!?\"'()\-—…《》]", "", s or "")
    a, m = norm(article), norm(material)
    if len(a) < SHINGLE_LEN or len(m) < SHINGLE_LEN:
        return 0.0
    m_set = {m[i:i + SHINGLE_LEN] for i in range(len(m) - SHINGLE_LEN + 1)}
    hits = sum(1 for i in range(len(a) - SHINGLE_LEN + 1) if a[i:i + SHINGLE_LEN] in m_set)
    return hits / (len(a) - SHINGLE_LEN + 1)


def check_title(title):
    fails = []
    if not ttw._is_three_part_title(title):
        fails.append("A-标题: 非三段式（须恰好两个逗号）")
    if len(title) > 30:
        fails.append(f"A-标题: 超30字（{len(title)}字）")
    if len(title) < 20:
        fails.append(f"A-标题: 不足20字（{len(title)}字），需填满事件+人物+悬念三要素")
    segs = [s for s in title.split("，") if s.strip()]
    if any(len(s) > 10 for s in segs):
        fails.append(f"A-标题: 某段超10字 {[len(s) for s in segs]}")
    for w in TITLE_CLICKBAIT:
        if w in title:
            fails.append(f"P-标题: 夸张悬念式标题词「{w}」（平台认定套路模板化发文）")
    return fails


def check_article(idx, title, article, material_text=""):
    """代码级自检（开头A/润色B/平台合规P维度），返回失败明细列表"""
    fails = check_title(title)
    text = article.strip()
    chars = len(re.sub(r"\s", "", text))
    if chars < 650:
        fails.append(f"B-字数: 正文{chars}字，低于650字下限（要求650-750）")
    if chars > 750:
        fails.append(f"B-字数: 正文{chars}字，超750字上限（要求650-750）")
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not (6 <= len(paras) <= 8):
        fails.append(f"B-段落: {len(paras)}段，须6-8段")
    # 开头检查
    first = paras[0] if paras else ""
    for pat in OPENING_PATTERNS:
        if re.search(pat, first):
            fails.append(f"A-开头: 命中禁用模式 {pat}")
    for w in BANNED_CONNECTORS:
        if w in first:
            fails.append(f"A-开头: 含连接词「{w}」")
    sent_ends = len(re.findall(r"[。！？]", first))
    if sent_ends < 2:
        fails.append("A-开头: 首段不足2句（单句成段式开头）")
    # 全文检查
    for w in BANNED_CONNECTORS:
        if w in text:
            fails.append(f"B-文风: 含禁用连接词「{w}」")
    for pat in PARALLEL_PATTERNS:
        if re.search(pat, text):
            fails.append(f"B-文风: 排比堆叠 {pat}")
    for w in ["令人深思", "发人深省", "意义深远"]:
        if w in text:
            fails.append(f"B-文风: 空洞形容词「{w}」")
    # 结尾检查
    last = paras[-1] if paras else ""
    for w in ENDING_BANNED:
        if w in last:
            fails.append(f"B-结尾: 命中禁用模板「{w}」")
    if "评论区" in text[-80:]:
        fails.append("B-结尾: 结尾出现「评论区」互动尾巴")
    if re.search(r"[。！？]$", last) is None:
        fails.append("B-结尾: 末段未以句号收束")
    # 段落长度
    long_paras = [i + 1 for i, p in enumerate(paras) if len(p) > 150]
    if long_paras:
        fails.append(f"B-段落: 第{long_paras}段超150字")
    # 儿化音
    cleaned = ttw.clean_erhua(text)
    if cleaned != text:
        fails.append("B-儿化音: clean_erhua 后有变化（应提交前自行清洗）")
    # 平台合规：洗稿/大篇幅引用（与素材10字重合率）
    if material_text:
        ratio = _shingle_ratio(text, material_text)
        if ratio > SHINGLE_MAX_RATIO:
            fails.append(f"P-原创: 与素材重合率 {ratio:.0%} > {SHINGLE_MAX_RATIO:.0%}"
                         "（洗稿/大篇幅引用风险，平台认定非原创）")
    # 平台合规：信息罗列式段落（顿号枚举≥4项且无完整句）
    for i, p in enumerate(paras, 1):
        if p.count("、") >= 4 and len(re.findall(r"[。！？]", p)) <= 1:
            fails.append(f"P-罗列: 第{i}段为信息罗列（平台认定低成本创作）")
            break
    return fails


def check_batch(articles):
    """批级检查：开头/结尾批内不重复、开放提问式结尾全批最多1次"""
    fails = []
    opens = [a["article"].strip().split("\n")[0][:12] for a in articles]
    ends = [a["article"].strip().split("\n")[-1][-12:] for a in articles]
    for i in range(len(articles) - 1):
        if opens[i] == opens[i + 1]:
            fails.append(f"批-开头: 第{i+1}与第{i+2}篇开头雷同「{opens[i]}」")
        if ends[i] == ends[i + 1]:
            fails.append(f"批-结尾: 第{i+1}与第{i+2}篇结尾雷同「{ends[i]}」")
    qs = sum(1 for a in articles if a["article"].strip().split("\n")[-1].rstrip().endswith("？"))
    if qs > 1:
        fails.append(f"批-结尾: 开放提问式结尾出现{qs}次（全批最多1次）")
    # 平台合规：批内标题禁共用句段（固定化格式发文）
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            seg_i = {s.strip() for s in articles[i]["title"].split("，") if s.strip()}
            seg_j = {s.strip() for s in articles[j]["title"].split("，") if s.strip()}
            common = seg_i & seg_j
            if common:
                fails.append(f"批-标题: 第{i+1}与第{j+1}篇共用句段「{'、'.join(common)}」"
                             "（平台认定套路模板化发文）")
    return fails


def save_cover_images(images_b64, prefix):
    cover_dir = os.path.join(OUTPUT_DIR, "covers")
    os.makedirs(cover_dir, exist_ok=True)
    covers = []
    for i, b64 in enumerate(images_b64[:3]):
        raw = b64.split(",", 1)[1] if b64.startswith("data:") else b64
        fpath = os.path.join(cover_dir, f"{prefix}_cover_{i+1}.jpg")
        with open(fpath, "wb") as f:
            f.write(base64.b64decode(raw))
        covers.append(fpath)
    return covers


def cmd_generate():
    state = load_state()
    if not state.get("confirmed"):
        raise RuntimeError("选题未确认，请先运行 confirm")
    if not os.path.exists(ARTICLES_FILE):
        raise FileNotFoundError(
            f"未找到 {ARTICLES_FILE}。编辑直写模式：请助手基于 {MATERIAL_MD} 撰写，"
            "格式 [{category, keyword, title, article}]，keyword 与选题搜索词一致")
    with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    kw_map = {t["word"]: t for t in state["confirmed"]}
    for a in articles:
        if a.get("keyword") not in kw_map:
            raise KeyError(f"文章 keyword「{a.get('keyword')}」不在已确认选题中")

    print("=" * 60)
    print("[4] 自检（标题/开头/文风/结尾/字数/段落/儿化音/平台合规）")
    print("=" * 60)
    material_text = ""
    if os.path.exists(MATERIAL_MD):
        with open(MATERIAL_MD, "r", encoding="utf-8") as f:
            material_text = f.read()
    all_fail = False
    for i, a in enumerate(articles, 1):
        a["title"] = ttw.clean_erhua(a["title"])
        a["article"] = ttw.clean_erhua(a["article"])
        fails = check_article(i, a["title"], a["article"], material_text)
        overlap = _shingle_ratio(a["article"], material_text)
        if fails:
            all_fail = True
            print(f"\n[{i}] {a['title'][:30]} —— 未过关:")
            for f_ in fails:
                print(f"    × {f_}")
        else:
            print(f"[{i}] {a['title'][:30]} —— 通过 ({len(re.sub(r'(?m)^$', '', a['article'].strip()))}字, 素材重合率{overlap:.0%})")
    batch_fails = check_batch(articles)
    for f_ in batch_fails:
        all_fail = True
        print(f"    × {f_}")
    if all_fail:
        print("\n>>> 自检未通过，未生成任何产物。请修订 _pipeline_articles.json 后重跑 generate")
        sys.exit(1)
    print("全部通过。")

    print("\n[5] 获取配图（原文优先，5层管线）并生成 HTML/封面/manifest")
    session = ttw.get_tt_session()
    page = open_page()
    manifest = []
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        for i, a in enumerate(articles, 1):
            kw = a["keyword"]
            topic = kw_map[kw]
            print(f"\n[{i}/{len(articles)}] [{a['category']}] {kw}")
            try:
                images, source = ttw.fetch_images_unified(
                    session, kw,
                    topic_image_url=topic.get("image", ""),
                    topic_url=topic.get("url", ""),
                    count=IMAGE_COUNT,
                    page=page,
                )
            except Exception as e:
                print(f"  配图获取失败: {e}")
                images, source = [], "无"
            print(f"  配图: {len(images)}张（{source}）")
            if len(images) < 3:
                print("  [警告] 配图不足3张，跳过此篇（自检C未过）")
                continue
            html = ttw.build_html(a["title"], a["article"], images)
            prefix = f"tt_{a['category']}_{i}_{timestamp}"
            filepath = os.path.join(OUTPUT_DIR, f"tt_hot_{prefix}.html")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            covers = save_cover_images(images, prefix)
            print(f"  HTML: {filepath}")
            print(f"  封面: {len(covers)}张 → covers/")
            manifest.append({
                "category": a["category"],
                "keyword": kw,
                "title": a["title"],
                "article": a["article"],
                "html_file": filepath,
                "cover_files": covers,
                "word_count": len(a["article"]),
                "image_count": len(images),
                "image_source": source,
            })
    finally:
        page.quit()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    state["stage"] = "generated"
    save_state(state)
    print("\n" + "=" * 60)
    print(f"生成完成: {len(manifest)}/{len(articles)} 篇，manifest → {MANIFEST_FILE}")
    print("=" * 60)
    for m in manifest:
        print(f"  {m['category']} | {m['title']}（{m['word_count']}字, {m['image_count']}图, {m['image_source']}）")
    print("\n>>> 关卡2：标题候选挑选（上传前必经）")
    print("    1) 助手撰写 _manual_title_candidates.json（每篇10个候选，keyword对应）")
    print("    2) python title_candidates.py          # 列出候选，暂停等待挑选")
    print("    3) python title_candidates.py apply 1:3 2:1 3:0   # 应用用户挑选")
    print("    4) python batch_n_tt_pipeline.py upload")


# ===== [6] 上传 =====
def save_b64_to_file(b64_data, prefix, idx):
    if not b64_data:
        return None
    b64 = b64_data.split(',', 1)[1] if b64_data.startswith('data:image/') else b64_data
    tmp_dir = os.path.join(BASE_DIR, "output", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    fpath = os.path.join(tmp_dir, f"{prefix}_img_{idx}.jpg")
    try:
        with open(fpath, "wb") as f:
            f.write(base64.b64decode(b64))
        return fpath
    except Exception:
        return None


def upload_image_via_paste(page, fpath, tag):
    with open(fpath, "rb") as f:
        raw_b64 = base64.b64encode(f.read()).decode('ascii')

    page.run_js("""
        var editor = document.querySelector('.ProseMirror');
        if (editor) { editor.innerHTML = '<p></p>'; editor.dispatchEvent(new Event('input', {bubbles: true})); }
    """)
    time.sleep(0.3)
    page.run_js("var e=document.querySelector('.ProseMirror'); if(e) e.focus();")
    time.sleep(0.3)

    page.run_js(f"""
        var editor = document.querySelector('.ProseMirror');
        if (!editor) return;
        editor.focus();
        var b64 = {json.dumps(raw_b64)};
        var byteString = atob(b64);
        var ab = new ArrayBuffer(byteString.length);
        var ia = new Uint8Array(ab);
        for (var i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
        var blob = new Blob([ab], {{type: 'image/jpeg'}});
        var file = new File([blob], '{tag}.jpg', {{type: 'image/jpeg'}});
        var pasteEvent = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
        var fakeData = {{
            files: [file], items: [], types: ['Files'],
            getData: function() {{ return ''; }},
            setData: function() {{}}, clearData: function() {{}}
        }};
        Object.defineProperty(pasteEvent, 'clipboardData', {{value: fakeData, writable: false, configurable: true}});
        editor.dispatchEvent(pasteEvent);
    """)

    for _ in range(30):
        time.sleep(1)
        imgs_now = page.run_js("return document.querySelectorAll('.ProseMirror img').length;") or 0
        if imgs_now > 0:
            break
    else:
        return ""

    page.run_js("""
        var editor = document.querySelector('.ProseMirror');
        if (!editor) return;
        var imgs = editor.querySelectorAll('img');
        for (var i = imgs.length - 1; i > 0; i--) imgs[i].parentNode.removeChild(imgs[i]);
    """)
    time.sleep(1)

    img_url = ""
    for _ in range(30):
        img_url = page.run_js("return document.querySelector('.ProseMirror img') ? document.querySelector('.ProseMirror img').src : '';") or ""
        if img_url and not img_url.startswith('blob:'):
            break
        time.sleep(1)
    if img_url.startswith('blob:'):
        img_url = ""
    return img_url


def wait_for_save(page, timeout=30):
    for i in range(timeout):
        time.sleep(1)
        s = page.run_js("""
            var body = document.body.innerText;
            if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
            return 'idle';
        """)
        if s and 'SAVED' in str(s):
            return True
    return False


def trigger_save(page):
    title_el = page.ele('tag:textarea@placeholder:文章标题', timeout=5)
    if not title_el:
        return False
    title_el.click()
    time.sleep(0.3)
    title_el.input(" ")
    time.sleep(0.3)
    page.run_js("""
        var el = document.querySelector('textarea[placeholder*="文章标题"]');
        if (el) {
            el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.blur();
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }
    """)
    time.sleep(0.5)
    return True


SAVE_HOOK_JS = """
window._saveLog = [];
(function(){
  var oo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m, u){ this._u = u; return oo.apply(this, arguments); };
  var os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(b){
    var xhr = this, url = String(this._u || '');
    if (url.indexOf('article/publish') !== -1) {
      var rec = {u: url, resp: ''};
      window._saveLog.push(rec);
      xhr.addEventListener('load', function(){
        try { rec.resp = xhr.status + ' ' + String(xhr.responseText).substring(0, 200); }
        catch (e) { rec.resp = 'status' + xhr.status; }
      });
    }
    return os.apply(this, arguments);
  };
})();
"""


def save_confirmed_by_server(page):
    """以服务端 article/publish 响应为准判断保存是否成功（页面提示会说谎）"""
    try:
        log = page.run_js("return JSON.stringify(window._saveLog || []);", timeout=10)
    except Exception:
        return False, "读取保存响应失败"
    for rec in json.loads(log or "[]"):
        resp = str(rec.get("resp", ""))
        if '"code":0' in resp and "保存成功" in resp:
            return True, resp[:80]
    return False, (json.dumps(json.loads(log or "[]"), ensure_ascii=False)[:160] if log else "无保存请求")


PM_JS = """return (function(){
function findView(){
    var editor=document.querySelector('.ProseMirror');
    if(!editor)return null;
    var desc=editor.pmViewDesc;
    while(desc){if(desc.view&&desc.view.state)return desc.view;desc=desc.parent;}
    function sf(fiber,v){
        if(!fiber||v.has(fiber)||v.size>500)return null;
        v.add(fiber);
        if(fiber.stateNode&&fiber.stateNode.view&&fiber.stateNode.view.state)return fiber.stateNode.view;
        if(fiber.memoizedProps&&fiber.memoizedProps.view&&fiber.memoizedProps.view.state)return fiber.memoizedProps.view;
        if(fiber.memoizedState){var s=fiber.memoizedState;while(s){if(s.memoizedState&&s.memoizedState.view&&s.memoizedState.view.state)return s.memoizedState.view;s=s.next;}}
        var r=sf(fiber.child,v);if(r)return r;
        return sf(fiber.sibling,v);
    }
    var el=editor;
    for(var i=0;i<15&&el;i++){
        var fk=Object.keys(el).find(function(k){return k.indexOf('__reactFiber')===0||k.indexOf('__reactInternalInstance')===0;});
        if(fk){var v=new Set();var r=sf(el[fk],v);if(r)return r;}
        el=el.parentElement;
    }
    return null;
}
var view=findView();
if(!view)return JSON.stringify({status:'no_view'});
var schema=view.state.schema;
var nts=Object.keys(schema.nodes);
var pn=null,im=null,dn=null;
nts.forEach(function(k){
    if(k==='paragraph'||k==='para')pn=k;
    if(k==='doc')dn=k;
    if(k==='image'||k==='imageUpload'||k==='media'||k==='img')im=k;
});
if(!im)nts.forEach(function(k){if(k.toLowerCase().indexOf('image')>=0||k.toLowerCase().indexOf('media')>=0)im=k;});
if(!pn)nts.forEach(function(k){if(k.toLowerCase().indexOf('para')>=0)pn=k;});
if(!dn)nts.forEach(function(k){if(k==='doc'||k==='document'||k==='article')dn=k;});
if(!pn||!dn)return JSON.stringify({status:'no_types',nodes:nts});
var urlAttr='src';var imAttrs={};
if(im){var imSpec=schema.nodes[im];if(imSpec&&imSpec.spec&&imSpec.spec.attrs){Object.keys(imSpec.spec.attrs).forEach(function(an){var a=imSpec.spec.attrs[an];if(an==='src'||an==='url'||an==='href')urlAttr=an;imAttrs[an]=a&&a.default!==undefined?a.default:'[no-default]';});}}
var data=window._pmData;var content=[];var ui=0;
var hasDataAttr=imAttrs&&Object.keys(imAttrs).indexOf('data')>=0;
for(var i=0;i<data.tp.length;i++){
    if(data.tp[i])content.push({type:pn,content:[{type:'text',text:data.tp[i]}]});
    var t=i+1;
    if(data.il[t]){for(var j=0;j<data.il[t];j++){if(ui<data.iu.length&&data.iu[ui]){var imgUrl=data.iu[ui];var attrs={};if(hasDataAttr){attrs.data={url:imgUrl,icUri:imgUrl,catchErrorUrl:"",link:"",caption:"图片来源于网络",ic:false,naturalHeight:0,naturalWidth:0,srcType:"",captionLenErr:false,needCheck:false};}else{attrs[urlAttr]=imgUrl;attrs.alt='图片来源于网络';}content.push({type:im,attrs:attrs});ui++;}}}
}
try{
    var doc=schema.nodeFromJSON({type:dn,content:content});
    view.dispatch(view.state.tr.replaceWith(0,view.state.doc.content.size,doc.content));
    var ic=0;view.state.doc.descendants(function(node){if(node.type.name===im)ic++;return true;});
    return JSON.stringify({status:'ok',imgs:ic,chars:view.state.doc.textContent.length});
}catch(e){return JSON.stringify({status:'error',error:e.message});}
})()"""


def upload_to_draft(page, title, text_parts, image_urls, image_layout, art_tag="a"):
    dlog(f"文章: {title}")
    dlog(f"正文: {len(text_parts)}段, {sum(len(t) for t in text_parts)}字")
    dlog(f"图片: {len([u for u in image_urls if u])}张, 布局: {image_layout}")

    page.get(f"{PUBLISH_URL}?_t={int(time.time() * 1000)}")
    time.sleep(6)

    for i in range(15):
        if page.run_js("return document.querySelectorAll('.ProseMirror').length;"):
            break
        time.sleep(1)
    else:
        dlog("编辑器加载超时")
        return False, "编辑器加载超时"

    try:
        page.run_js(SAVE_HOOK_JS)
    except Exception:
        pass

    for text in ["不恢复", "关闭"]:
        try:
            btn = page.ele(f"text:{text}", timeout=2)
            if btn:
                btn.click()
                time.sleep(1)
        except Exception:
            pass
    page.run_js("""
        var mask = document.querySelector('.byte-drawer-mask');
        if (mask) { mask.click(); mask.remove(); }
        var drawer = document.querySelector('.ai-assistant-drawer');
        if (drawer) drawer.remove();
    """)
    time.sleep(1)

    title_json = json.dumps(title)
    page.run_js(f"""
        var el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                 document.querySelector('textarea[placeholder*="请输入文章标题"]');
        if (!el) return;
        el.focus();
        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeSetter.call(el, {title_json});
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        el.blur();
    """)
    time.sleep(3)

    valid_urls = []
    if image_urls:
        dlog(f"上传{len(image_urls)}张图片...")
        for img_idx, img_b64 in enumerate(image_urls):
            if not img_b64:
                valid_urls.append("")
                continue
            dlog(f"  图片{img_idx+1}/{len(image_urls)}: 上传中...")
            fpath = save_b64_to_file(img_b64, art_tag, img_idx)
            if not fpath:
                dlog(f"  图片{img_idx+1}: 保存失败")
                valid_urls.append("")
                continue
            img_url = upload_image_via_paste(page, fpath, f"{art_tag}_{img_idx+1}")
            if img_url and not img_url.startswith('blob:'):
                valid_urls.append(img_url)
                dlog(f"  图片{img_idx+1}: OK")
            else:
                dlog(f"  图片{img_idx+1}: 上传失败")
                valid_urls.append("")
            time.sleep(0.5)
        dlog(f"图片上传完成: {len([u for u in valid_urls if u])}/{len(image_urls)}张")

    dlog("设置正文内容（文字+图片）...")
    data_json = json.dumps({"tp": text_parts, "iu": valid_urls, "il": image_layout}, ensure_ascii=False)
    page.run_js("window._pmData=" + data_json + ";")
    pm_result = page.run_js(PM_JS)
    try:
        pm_data = json.loads(pm_result) if pm_result else {}
    except Exception:
        pm_data = {}

    if pm_data.get('status') == 'ok':
        dlog(f"正文+图片设置成功: {pm_data.get('chars', 0)}字, {pm_data.get('imgs', 0)}张图")
    else:
        dlog(f"PM API失败({str(pm_result)[:100]})，键盘输入回退...")
        editor_el = page.ele('.ProseMirror', timeout=3)
        if editor_el:
            editor_el.click()
            time.sleep(0.3)
            for j, para in enumerate(text_parts):
                if j > 0:
                    page.actions.key_down('Enter').key_up('Enter')
                    time.sleep(0.2)
                page.actions.type(para)
                time.sleep(0.3)

    time.sleep(2)
    trigger_save(page)
    ok, detail = save_confirmed_by_server(page)
    if not ok:
        dlog("保存未确认，再触发一次...")
        trigger_save(page)
        wait_for_save(page, timeout=15)
        ok, detail = save_confirmed_by_server(page)
    if ok:
        dlog(f"服务端确认保存成功: {detail}")
    else:
        dlog(f"保存失败（服务端未确认）: {detail}")
    return ok, detail


def extract_images_from_html(path):
    """从 HTML 提取 base64 图片（顺序即文中顺序）"""
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    return re.findall(r'data:image/jpeg;base64,([A-Za-z0-9+/=]+)', html)


def verify_drafts_api(titles):
    """浏览器关闭后用 draft_list API 复核（权威验证）"""
    cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
    headers = {
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://mp.toutiao.com/profile_v4/manage/draft",
    }
    r = requests.get("https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=0&count=20&app_id=1231",
                     headers=headers, timeout=20)
    drafts = (r.json() or {}).get("draft_list") or []
    results = []
    for t in titles:
        hit = any(t[:8] in (d.get("title") or "") for d in drafts)
        results.append((t, hit))
        print(f"  {'[OK]  ' if hit else '[MISS]'} {t[:32]}")
    return results


def cmd_upload():
    if not os.path.exists(MANIFEST_FILE):
        raise FileNotFoundError(f"未找到 {MANIFEST_FILE}，请先运行 generate")
    if not os.path.exists(CANDIDATES_FILE):
        raise RuntimeError(
            "未完成标题候选流程（关卡2）。请先: python title_candidates.py 列出候选并让用户挑选，"
            "再 python title_candidates.py apply ... 应用，然后才能上传")
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    print("=" * 60)
    print(f"[6] 上传草稿箱（{len(manifest)} 篇）")
    print("=" * 60)
    page = open_page()
    results = []
    try:
        for i, m in enumerate(manifest, 1):
            print(f"\n[{i}/{len(manifest)}] {m['title'][:40]}")
            text_parts = [p.strip() for p in m["article"].split("\n") if p.strip()]
            images = extract_images_from_html(m["html_file"])
            if len(images) != IMAGE_COUNT:
                print(f"  [警告] HTML中提取到{len(images)}张图（应为{IMAGE_COUNT}）")
            image_layout = ttw._calc_image_layout(len(text_parts), len(images))
            ok, detail = upload_to_draft(page, m["title"], text_parts, images, image_layout, f"a{i}")
            results.append({"title": m["title"], "ok": ok, "detail": detail})
            print(f"  >>> {'成功' if ok else '失败'}")
            time.sleep(3)
    finally:
        page.quit()

    print("\n[7] 草稿箱复核（draft_list API）")
    api_results = verify_drafts_api([r["title"] for r in results])
    n_ok = sum(1 for _, hit in api_results if hit)
    print("\n" + "=" * 60)
    print(f"完成: {n_ok}/{len(results)} 篇确认在草稿箱（以API复核为准）")
    print("=" * 60)


def main():
    args = sys.argv[1:]
    if not args:
        print_usage()
        return
    cmd = args[0]
    if cmd == "topics":
        cmd_topics(int(args[1]) if len(args) > 1 else 3)
    elif cmd == "confirm":
        if len(args) < 2:
            raise ValueError("用法: python batch_n_tt_pipeline.py confirm 1,2,3（或 all）")
        cmd_confirm(args[1])
    elif cmd == "material":
        cmd_material()
    elif cmd == "generate":
        cmd_generate()
    elif cmd == "upload":
        cmd_upload()
    elif cmd.isdigit():
        cmd_topics(int(cmd))
    else:
        print(f"未知子命令: {cmd}")
        print_usage()


if __name__ == "__main__":
    main()
