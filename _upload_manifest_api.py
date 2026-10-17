# -*- coding: utf-8 -*-
"""从 batch_manifest.json 上传3篇文章到头条草稿箱（纯API）：
解析HTML（段落+图片按布局顺序）-> 图片上传头条图床 -> 保存草稿(coverType=3+3封面) -> 验证"""
import os
import re
import json
import time
import random
import requests
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST = os.path.join(BASE_DIR, "output", "batch_manifest.json")

with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)
cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf_token = cookies_dict.get("passport_csrf_token", "")

BASE_HEADERS = {
    "Cookie": cookie_str,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://mp.toutiao.com",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Accept": "application/json, text/plain, */*",
    "X-CSRFToken": csrf_token,
}
SPICE_URL = "https://mp.toutiao.com/spice/image?upload_source=20020002&need_enhance=true&aid=1231&device_platform=web"
SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"
LIST_URL = "https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=50&type=&source=0&_signature="


def parse_html_body(html_path):
    """按文档顺序提取正文：段落文本与base64图片，返回 (blocks, word_cnt)
    blocks: [("p", text) | ("img", b64)]"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    body = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
    content = body.group(1) if body else html
    blocks = []
    # 纯 <p>（无属性）为正文段落；<img src="data:..."> 为配图（img-caption 的 p 带 class 不匹配）
    pat = re.compile(r"<p>(.*?)</p>|<img\s+src=\"data:image/jpeg;base64,([^\"]+)\"", re.DOTALL)
    for m in pat.finditer(content):
        if m.group(1) is not None:
            text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if text:
                blocks.append(("p", text))
        elif m.group(2):
            blocks.append(("img", m.group(2)))
    word_cnt = sum(len(t) for k, t in blocks if k == "p")
    return blocks, word_cnt


def upload_image(img_b64):
    import base64
    img_bytes = base64.b64decode(img_b64)
    resp = requests.post(
        SPICE_URL,
        files={"image": ("img.jpg", img_bytes, "image/jpeg")},
        headers={k: v for k, v in BASE_HEADERS.items() if k != "X-CSRFToken"},
        timeout=60,
    )
    r = resp.json()
    if r.get("code") == 0:
        d = r.get("data") or {}
        return d.get("image_url", "")
    print(f"    图片上传失败: {r.get('message')}")
    return ""


def save_draft(title, content_html, word_cnt, cover_urls):
    extra = {
        "content_source": "100000000402",
        "content_word_cnt": word_cnt,
        "is_multi_title": 0,
        "sub_titles": [],
        "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC",
                   "device_platform": "mp", "is_message": 0},
        "tuwen_wtt_transfer_switch": "1",
    }
    form_data = {
        "source": "29",
        "extra": json.dumps(extra, ensure_ascii=False),
        "content": content_html,
        "title": title,
        "search_creation_info": json.dumps({"searchTopOne": 0, "abstract": "", "clue_id": ""}, ensure_ascii=False),
        "title_id": f"{int(time.time()*1000)}_{random.randint(10**15, 10**16-1)}",
        "mp_editor_stat": "{}",
        "is_refute_rumor": "0",
        "save": "1",
        "entrance": "",
        "timer_status": "0",
        "timer_time": "",
        "educluecard": "",
        "draft_form_data": json.dumps({"coverType": 3}, ensure_ascii=False),
        "pgc_feed_covers": json.dumps(cover_urls, ensure_ascii=False),
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


def main():
    with open(MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    print(f"共 {len(manifest)} 篇文章待上传", flush=True)

    results = []
    for i, art in enumerate(manifest, 1):
        title = art["title"]
        print(f"\n[{i}/{len(manifest)}] {title}", flush=True)
        blocks, word_cnt = parse_html_body(art["html_file"])
        n_para = sum(1 for k, _ in blocks if k == "p")
        n_img = sum(1 for k, _ in blocks if k == "img")
        print(f"  正文: {word_cnt}字 / {n_para}段, 配图: {n_img}张", flush=True)
        assert n_img >= 3, "配图不足3张"

        # 上传图片 -> URL，保持顺序
        img_urls = []
        for k, v in blocks:
            if k != "img":
                continue
            url = upload_image(v)
            if url:
                img_urls.append(url)
                print(f"    图{len(img_urls)}: OK", flush=True)
            time.sleep(0.5)
        print(f"  图床上传成功: {len(img_urls)}张", flush=True)
        assert len(img_urls) >= 3, "图床上传不足3张"

        # 构建content（保持布局顺序），封面取前3张
        ui = 0
        parts = []
        for k, v in blocks:
            if k == "p":
                parts.append(f"<p>{v}</p>")
            else:
                if ui < len(img_urls):
                    parts.append(f'<img src="{img_urls[ui]}">')
                    ui += 1
        content_html = "\n".join(parts)
        covers = img_urls[:3]

        code, pgc_id, msg = save_draft(title, content_html, word_cnt, covers)
        ok = code == 0
        print(f"  {'[成功]' if ok else '[失败]'} code={code} pgc_id={pgc_id} {msg}", flush=True)
        results.append({"index": i, "title": title, "ok": ok, "pgc_id": pgc_id,
                        "chars": word_cnt, "imgs": len(img_urls)})
        if i < len(manifest):
            time.sleep(3)

    # 验证草稿列表
    print("\n[验证] 查询草稿列表...", flush=True)
    time.sleep(5)
    resp = requests.get(LIST_URL, headers=BASE_HEADERS, timeout=30)
    arts = (resp.json().get("data") or {}).get("articles") or []
    n_ok = 0
    for r in results:
        prefix = r["title"][:6]
        found = any(prefix in (a.get("title") or "") and a.get("is_draft") for a in arts)
        r["in_draft"] = found
        if found:
            n_ok += 1
        print(f"  {'[OK]  ' if found else '[MISS]'} {r['title']}（{r['chars']}字/{r['imgs']}图）", flush=True)

    with open(os.path.join(BASE_DIR, "api_upload_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n完成: 上传成功 {sum(1 for r in results if r['ok'])}/{len(results)}，"
          f"草稿箱验证 {n_ok}/{len(results)}", flush=True)


if __name__ == "__main__":
    main()
