#!/usr/bin/env python3
"""纯API流水线：头条热榜N条 → 撰写 → 图片上传 → 保存草稿箱
用法: python api_pipeline_3.py [数量，默认3]
所有操作走API（无浏览器）：
- 热榜/素材/配图: toutiao_hot_writer
- 图片上传: POST /spice/image (multipart field=image)
- 草稿保存: POST /mp/agw/article/publish (save=1)
"""
import os, sys, json, time, random, difflib, io, base64
import requests
from urllib.parse import urlencode

import toutiao_hot_writer as ttw
from batch_n_tt_pipeline import author_article, pick_distinct

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
IMAGE_COUNT = 5
N_ARTICLES = int(sys.argv[1]) if len(sys.argv) > 1 else 3

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)
cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf_token = cookies_dict.get("passport_csrf_token", "")

BASE_HEADERS = {
    "Cookie": cookie_str,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://mp.toutiao.com",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Accept": "application/json, text/plain, */*",
    "X-CSRFToken": csrf_token,
}

SPICE_URL = "https://mp.toutiao.com/spice/image?upload_source=20020002&need_enhance=true&aid=1231&device_platform=web"
SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"
LIST_URL = "https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=50&type=&source=0&_signature="


def b64_to_bytes(b64_data):
    if not b64_data:
        return None
    b64 = b64_data.split(",", 1)[1] if b64_data.startswith("data:image/") else b64_data
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def upload_image(img_bytes):
    """上传图片字节到头条图床，返回(image_url, image_uri)"""
    resp = requests.post(
        SPICE_URL,
        files={"image": ("img.jpg", img_bytes, "image/jpeg")},
        headers={k: v for k, v in BASE_HEADERS.items() if k != "X-CSRFToken"},
        timeout=60,
    )
    r = resp.json()
    if r.get("code") == 0:
        d = r.get("data") or {}
        return d.get("image_url", ""), d.get("image_uri", "")
    print(f"    图片上传失败: {r.get('message')}")
    return "", ""


def save_draft(title, content_html, word_cnt):
    """保存草稿（save=1），返回(code, pgc_id, message)"""
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
        "save": "1",
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
        **BASE_HEADERS, "Content-Type": "application/x-www-form-urlencoded",
    }, timeout=60)
    r = resp.json()
    return r.get("code", -1), (r.get("data") or {}).get("pgc_id", "0"), r.get("message", "")


def verify_drafts(titles):
    """验证标题是否出现在草稿列表"""
    resp = requests.get(LIST_URL, headers=BASE_HEADERS, timeout=30)
    arts = (resp.json().get("data") or {}).get("articles") or []
    result = {}
    for t in titles:
        prefix = t[:6]
        found = any(t and prefix in (a.get("title") or "") and a.get("is_draft") for a in arts)
        result[t] = found
    return result


def main():
    print("=" * 60)
    print(f"纯API流水线: {N_ARTICLES}条热榜 → 文章 → 草稿箱")
    print("=" * 60)

    print("\n[1] 获取头条热榜...")
    session = ttw.get_tt_session()
    hot_list = ttw.get_toutiao_hot_board(session)
    print(f"  共 {len(hot_list)} 条")

    topics = pick_distinct(hot_list, N_ARTICLES)
    print(f"  去重后选中 {len(topics)} 条:")
    for t in topics:
        print(f"    [{t['rank']}] {t['word']}")

    results = []
    for i, hot in enumerate(topics, 1):
        kw = hot["word"]
        print(f"\n{'='*50}")
        print(f"[文章 {i}/{len(topics)}] {kw}")

        print("[2] 抓取话题素材...")
        try:
            posts = ttw.fetch_toutiao_posts_text(session, kw, topic_url=hot.get("url", ""), count=8)
        except Exception as e:
            print(f"  抓取失败: {e}")
            posts = []
        print(f"  {len(posts)} 条素材")

        print("[3] 撰写文章...")
        title, article = author_article(kw, posts)
        paragraphs = [p.strip() for p in article.split("\n") if p.strip()]
        word_cnt = sum(len(p) for p in paragraphs)
        print(f"  标题: {title}")
        print(f"  正文: {word_cnt}字, {len(paragraphs)}段")

        print("[4] 获取配图（4层管线）...")
        try:
            images, source = ttw.fetch_images_unified(
                session, kw,
                topic_image_url=hot.get("image", ""),
                topic_url=hot.get("url", ""),
                count=IMAGE_COUNT,
            )
        except Exception as e:
            print(f"  获取失败: {e}")
            images, source = [], "无"
        print(f"  {len(images)} 张（来源: {source}）")

        print("[5] 上传图片到头条图床...")
        img_urls = []
        for j, b64 in enumerate(images):
            data = b64_to_bytes(b64)
            if not data:
                continue
            url, uri = upload_image(data)
            if url:
                img_urls.append(url)
                print(f"    图片{len(img_urls)}: OK")
            time.sleep(0.5)
        print(f"  共上传 {len(img_urls)} 张")

        print("[6] 构建内容并保存草稿...")
        layout = ttw._calc_image_layout(len(paragraphs), len(img_urls))
        print(f"  布局: {layout}")

        content_parts = []
        ui = 0
        for pi, para in enumerate(paragraphs):
            content_parts.append(f"<p>{para}</p>")
            n = layout.get(pi + 1, 0)
            for _ in range(n):
                if ui < len(img_urls):
                    content_parts.append(f'<img src="{img_urls[ui]}">')
                    ui += 1
        content_html = "\n".join(content_parts)

        code, pgc_id, msg = save_draft(title, content_html, word_cnt)
        ok = code == 0
        print(f"  {'[成功]' if ok else '[失败]'} code={code} pgc_id={pgc_id} {msg}")
        results.append({"title": title, "ok": ok, "pgc_id": pgc_id, "chars": word_cnt, "imgs": len(img_urls), "layout": str(layout)})
        time.sleep(2)

    print("\n[7] 验证草稿箱...")
    time.sleep(3)
    verify = verify_drafts([r["title"] for r in results])
    n_ok = 0
    for r in results:
        r["in_draft"] = verify.get(r["title"], False)
        if r["in_draft"]:
            n_ok += 1
        print(f"  {'[OK]  ' if r['in_draft'] else '[MISS]'} {r['title'][:30]}（{r['chars']}字/{r['imgs']}图）")

    print("\n" + "=" * 60)
    print(f"完成: {n_ok}/{len(results)} 篇已入草稿箱")
    print("=" * 60)

    with open(os.path.join(BASE_DIR, "api_pipeline_result.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
