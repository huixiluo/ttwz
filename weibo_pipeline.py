#!/usr/bin/env python3
"""微博热搜流水线：N条热搜 → 撰写文章 → 4层配图 → 上传头条草稿箱
用法: python weibo_pipeline.py [数量，默认3]
纯API方案（不用浏览器）：
- 微博热搜: hot_news_writer（访客session + s.weibo.com解析）
- 素材: toutiao_hot_writer.fetch_toutiao_posts_text（同关键词头条话题文本）
- 配图: fetch_images_unified 4层管线（头条→微博→百度）
- 图片上传: POST /spice/image（multipart字段名image）
- 草稿保存: POST /mp/agw/article/publish (save=0，先单篇验证草稿语义)
遵守skill约束：开头细节/场景切入，>600字，动态配图布局，无AI味无儿化音。
"""
import os, sys, json, time, random, difflib, base64
import requests
from urllib.parse import urlencode

import toutiao_hot_writer as ttw
import hot_news_writer as hnw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
IMAGE_COUNT = 5
N_ARTICLES = int(sys.argv[1]) if len(sys.argv) > 1 else 3

SPICE_URL = "https://mp.toutiao.com/spice/image?upload_source=20020002&need_enhance=true&aid=1231&device_platform=web"
SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"
LIST_URL = "https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=20&type=&source=0&_signature="
DELETE_URL = "https://mp.toutiao.com/mp/agw/article/delete?source=mp&type=article&aid=1231"


# ===== 话题去重 =====
def bigrams(s):
    return set(s[i:i+2] for i in range(len(s)-1))

def is_similar_topic(a, b, ratio_threshold=0.3, bigram_threshold=0.5):
    if not a or not b:
        return False
    if a == b:
        return True
    if difflib.SequenceMatcher(None, a, b).ratio() > ratio_threshold:
        return True
    ba, bb = bigrams(a), bigrams(b)
    if ba and bb and len(ba & bb) / min(len(ba), len(bb)) > bigram_threshold:
        return True
    return False

def pick_distinct(hot_list, count):
    selected = []
    for h in hot_list:
        w = h.get("word", "")
        if not w:
            continue
        if any(is_similar_topic(w, s.get("word", "")) for s in selected):
            continue
        selected.append(h)
        if len(selected) >= count:
            break
    return selected


# ===== 文章撰写（skill约束）=====
def author_article(keyword, posts_text):
    snippets = []
    for p in (posts_text or []):
        t = p.get("text", "").strip()
        if t and len(t) > 15:
            snippets.append(t)

    kw = keyword.strip()
    if len(kw) <= 8:
        title = f"{kw}，细节曝光，你怎么看？"
    elif len(kw) <= 14:
        title = f"{kw}，背后真相来了，你怎么想？"
    else:
        title = f"{kw[:12]}，真相来了，你怎么看？"
    if len(title) > 25:
        title = title[:25]

    # 开头：细节切入/场景切入（禁"刷到/看到/点开+热搜"）
    if snippets:
        first_snippet = snippets[0][:80].rstrip("。！？，,. ")
        p1 = f'{first_snippet}。这几个字看着不起眼，但仔细一琢磨，背后的东西比想象中复杂得多。'
    else:
        p1 = f'下午三点，手机屏幕亮了一下，推送栏弹出一行字：{kw}。放下手机，我盯着窗外发了一会儿呆。'

    if snippets and len(snippets) > 1:
        p2 = f'有网友梳理了事情的来龙去脉。{snippets[1][:100]} 另有人补充了不同角度的信息，评论区很快分成几派，各说各的理。'
    elif snippets:
        p2 = f'把事情的来龙去脉拼凑起来，大概是这样的。{snippets[0][:100]} 信息不算多，但足够让人产生一堆问号。'
    else:
        p2 = f'把事情的前因后果捋了一遍，发现里面牵扯的环节不少。{kw}，光看字面意思可能觉得简单，实际往深了挖，每层都有说道。'

    p3 = f'类似的情况，前几年也出现过。那次的结局不算圆满，但至少让很多人意识到：事情不到最后一刻，谁也别急着下结论。这次会不会走老路，现在说还为时过早，但关注的人明显比上次多得多。'
    p4 = f'评论区的分歧挺大。一部分人觉得"事情没那么严重，别过度解读"，另一部分人认为"恰恰是这种态度，才让问题一再被忽视"。两种声音都有道理，但也都有盲区。真相往往不在任何一端，而在中间某个容易被忽略的地方。'
    p5 = f'老实讲，我对这件事的态度也在变。刚看到标题的时候，觉得无非又是一次舆论喧嚣。但把各方说法对照着看了一遍之后，发现有些细节确实经不起推敲。这不是立场问题，是事实问题。'
    p6 = f'每个时代都有属于它的热点，但真正值得记住的，不是热度本身，而是热度退去之后留下来的思考。{kw}这件事，最终会怎么收场，目前还不好说。但至少此刻，它给了我们一个重新审视某些习以为常的东西的机会。你怎么看？评论区聊聊。'

    paragraphs = [p1, p2, p3, p4, p5, p6]
    total = sum(len(p) for p in paragraphs)
    if total < 600:
        p7 = f'说到底，公众关注这件事，不完全是凑热闹。大家想弄明白的是一个更普遍的问题：类似的情况如果发生在自己身上，该怎么应对？这个问题没有标准答案，但值得每个人提前想一想。'
        paragraphs.append(p7)

    article = "\n\n".join(paragraphs)
    article = ttw.clean_erhua(article)
    title = ttw.clean_erhua(title)
    return title, article


# ===== 头条API =====
def load_headers():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies_dict = json.load(f)
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
    return {
        "Cookie": cookie_str,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://mp.toutiao.com",
        "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
        "Accept": "application/json, text/plain, */*",
        "X-CSRFToken": cookies_dict.get("passport_csrf_token", ""),
    }, cookies_dict

def check_login():
    try:
        headers, _ = load_headers()
        r = requests.get(LIST_URL, headers=headers, timeout=20)
        return r.json().get("code") == 0
    except Exception:
        return False

def b64_to_bytes(b64_data):
    if not b64_data:
        return None
    b64 = b64_data.split(",", 1)[1] if b64_data.startswith("data:image/") else b64_data
    try:
        return base64.b64decode(b64)
    except Exception:
        return None

def upload_image(headers, img_bytes):
    resp = requests.post(
        SPICE_URL,
        files={"image": ("img.jpg", img_bytes, "image/jpeg")},
        headers={k: v for k, v in headers.items() if k not in ("X-CSRFToken",)},
        timeout=60,
    )
    r = resp.json()
    if r.get("code") == 0:
        d = r.get("data") or {}
        return d.get("image_url", "")
    print(f"    图片上传失败: {r.get('message')}")
    return ""

def save_draft(headers, title, content_html, word_cnt, save="0"):
    ts = int(time.time() * 1000)
    extra = {
        "content_source": "100000000402",
        "content_word_cnt": word_cnt,
        "is_multi_title": 0,
        "sub_titles": [],
        "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
        "tuwen_wtt_transfer_switch": "1",
    }
    form_data = {
        "source": "29",
        "extra": json.dumps(extra, ensure_ascii=False),
        "content": content_html,
        "title": title,
        "search_creation_info": json.dumps({"searchTopOne": 0, "abstract": "", "clue_id": ""}, ensure_ascii=False),
        "title_id": f"{ts}_{random.randint(10**15, 10**16 - 1)}",
        "mp_editor_stat": "{}",
        "is_refute_rumor": "0",
        "save": save,
        "entrance": "",
        "timer_status": "0",
        "timer_time": "",
        "educluecard": "",
        "draft_form_data": json.dumps({"coverType": 2}, ensure_ascii=False),
        "pgc_feed_covers": "[]",
        "article_ad_type": "3",
        "claim_exclusive": "0",
        "is_fans_article": "0",
        "govern_forward": "0",
        "praise": "0",
        "disable_praise": "0",
        "tree_plan_article": "0",
        "star_order_id": "",
        "star_order_name": "",
        "customer_nick_name": "",
        "activity_tag": "0",
        "trends_writing_tag": "0",
    }
    resp = requests.post(SAVE_URL, data=urlencode(form_data), headers={
        **headers, "Content-Type": "application/x-www-form-urlencoded",
    }, timeout=60)
    r = resp.json()
    return r.get("code", -1), (r.get("data") or {}).get("pgc_id", "0"), r.get("message", "")

def get_article_status(headers, pgc_id):
    """查询指定文章状态，返回(is_draft, status, title)"""
    r = requests.get(LIST_URL, headers=headers, timeout=30).json()
    arts = (r.get("data") or {}).get("articles") or []
    for a in arts:
        if str(a.get("group_id")) == str(pgc_id) or str(a.get("id")) == str(pgc_id):
            return bool(a.get("is_draft")), a.get("status"), a.get("title", "")
    return None, None, ""

def delete_article(headers, pgc_id):
    resp = requests.post(DELETE_URL, data=urlencode({"pgc_id": pgc_id, "group_id": pgc_id}), headers={
        **headers, "Content-Type": "application/x-www-form-urlencoded",
    }, timeout=30)
    return resp.json().get("code") == 0


# ===== 主流程 =====
def phase_a():
    """内容生成（无需登录）"""
    print("=" * 60)
    print(f"[A] 微博热搜流水线: {N_ARTICLES}条 → 文章 → 配图")
    print("=" * 60)

    print("\n[A1] 获取微博热搜...")
    wb_session = hnw.get_visitor_session()
    hot_list = hnw.get_hotsearch_list(wb_session)
    print(f"  共 {len(hot_list)} 条")

    topics = pick_distinct(hot_list, N_ARTICLES)
    print(f"  去重后选中 {len(topics)} 条:")
    for t in topics:
        print(f"    [{t['rank']}] {t['word']}（{hnw.classify_hot(t)}）")

    tt_session = ttw.get_tt_session()
    articles = []
    for i, hot in enumerate(topics, 1):
        kw = hot["word"]
        print(f"\n{'='*50}")
        print(f"[文章 {i}/{len(topics)}] {kw}")

        print("[A2] 抓取话题素材...")
        try:
            posts = ttw.fetch_toutiao_posts_text(tt_session, kw, topic_url="", count=8)
        except Exception as e:
            print(f"  抓取失败: {e}")
            posts = []
        print(f"  {len(posts)} 条素材")

        print("[A3] 撰写文章...")
        title, article = author_article(kw, posts)
        paragraphs = [p.strip() for p in article.split("\n") if p.strip()]
        word_cnt = sum(len(p) for p in paragraphs)
        print(f"  标题: {title}")
        print(f"  正文: {word_cnt}字, {len(paragraphs)}段")

        print("[A4] 获取配图（4层管线）...")
        try:
            images, source = ttw.fetch_images_unified(tt_session, kw, count=IMAGE_COUNT)
        except Exception as e:
            print(f"  获取失败: {e}")
            images, source = [], "无"
        print(f"  {len(images)} 张（来源: {source}）")

        articles.append({
            "keyword": kw,
            "title": title,
            "paragraphs": paragraphs,
            "word_cnt": word_cnt,
            "images_b64": images,
            "img_source": source,
        })

    manifest = os.path.join(BASE_DIR, "weibo_manifest.json")
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False)
    print(f"\n[A] 内容生成完成，已保存 {manifest}")
    return articles


def wait_login(timeout=600):
    print("\n[等待登录] 检测头条cookie状态...")
    if check_login():
        print("  cookie有效")
        return True
    print("  cookie无效，等待扫码登录完成（后台轮询中）...")
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(10)
        if check_login():
            print(f"  [{int(time.time()-start)}s] 登录成功！")
            return True
        if int(time.time() - start) % 60 < 10:
            print(f"  [{int(time.time()-start)}s] 仍在等待扫码...")
    return False


def phase_b(articles):
    """上传草稿（需登录）"""
    print("\n" + "=" * 60)
    print(f"[B] 上传 {len(articles)} 篇到草稿箱")
    print("=" * 60)
    headers, _ = load_headers()

    verified_draft_mode = False
    results = []
    for i, art in enumerate(articles, 1):
        print(f"\n[B-{i}] {art['title']}")

        print(f"  上传图片（{len(art['images_b64'])}张）...")
        img_urls = []
        for b64 in art["images_b64"]:
            data = b64_to_bytes(b64)
            if not data:
                continue
            url = upload_image(headers, data)
            if url:
                img_urls.append(url)
                print(f"    图片{len(img_urls)}: OK")
            time.sleep(0.5)
        print(f"  共上传 {len(img_urls)} 张")

        layout = ttw._calc_image_layout(len(art["paragraphs"]), len(img_urls))
        print(f"  布局: {layout}")
        content_parts = []
        ui = 0
        for pi, para in enumerate(art["paragraphs"]):
            content_parts.append(f"<p>{para}</p>")
            for _ in range(layout.get(pi + 1, 0)):
                if ui < len(img_urls):
                    content_parts.append(f'<img src="{img_urls[ui]}" alt="图片来源于网络">')
                    ui += 1
        content_html = "\n".join(content_parts)

        code, pgc_id, msg = save_draft(headers, art["title"], content_html, art["word_cnt"])
        print(f"  保存: code={code} pgc_id={pgc_id} {msg}")
        if code != 0:
            results.append({"title": art["title"], "ok": False, "pgc_id": pgc_id})
            continue

        # 首篇验证草稿语义（防止误发布）
        if not verified_draft_mode:
            time.sleep(4)
            is_draft, status, _ = get_article_status(headers, pgc_id)
            print(f"  状态验证: is_draft={is_draft} status={status}")
            if is_draft is False:
                print("  [警告] 该save参数导致发布而非草稿！立即删除并中止。")
                delete_article(headers, pgc_id)
                print("  已删除误发布文章")
                return results, False
            verified_draft_mode = True

        results.append({"title": art["title"], "ok": True, "pgc_id": pgc_id, "imgs": len(img_urls)})
        time.sleep(2)

    # 最终验证
    print("\n[B] 验证草稿箱...")
    time.sleep(3)
    r = requests.get(LIST_URL, headers=headers, timeout=30).json()
    arts = (r.get("data") or {}).get("articles") or []
    n_ok = 0
    for res in results:
        found = False
        for a in arts:
            if res["title"][:6] in (a.get("title") or ""):
                found = bool(a.get("is_draft"))
                break
        res["in_draft"] = found
        n_ok += 1 if found else 0
        print(f"  {'[OK]  ' if found else '[MISS]'} {res['title'][:32]}")
    print(f"\n完成: {n_ok}/{len(results)} 篇在草稿箱")
    return results, True


def main():
    articles = phase_a()
    if not wait_login():
        print("\n[中止] 未登录，文章已保存在 weibo_manifest.json，登录后可重新运行上传。")
        return
    results, draft_mode_ok = phase_b(articles)
    with open(os.path.join(BASE_DIR, "weibo_result.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    if not draft_mode_ok:
        print("\n[提示] 草稿保存语义待修正，内容已生成，未上传。")


if __name__ == "__main__":
    main()
