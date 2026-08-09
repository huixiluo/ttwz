# -*- coding: utf-8 -*-
"""用API直接批量上传文章（save=1方式）"""
import os, json, time, requests, random, re
from urllib.parse import urlencode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "toutiao_cookies.json"), "r", encoding="utf-8") as f:
    cookies_dict = json.load(f)

cookie_str = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
csrf_token = cookies_dict.get("passport_csrf_token", "")

headers = {
    "Cookie": cookie_str,
    "Content-Type": "application/x-www-form-urlencoded",
    "X-CSRFToken": csrf_token,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://mp.toutiao.com/profile_v4/graphic/publish",
    "Origin": "https://mp.toutiao.com",
    "Accept": "application/json, text/plain, */*",
}

SAVE_URL = "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0"

# 读取9篇文章manifest
with open("output/batch_manifest.json", "r", encoding="utf-8") as f:
    manifest = json.load(f)

# 已完成的标题（第1篇）
our_titles_done = ["网红揭恶毒闺蜜"]

def get_draft_count():
    try:
        resp = requests.get("https://mp.toutiao.com/mp/agw/creator_center/draft_count?type=0&app_id=1231", headers=headers, timeout=10)
        return resp.json().get("count", 0)
    except:
        return -1

def get_draft_list():
    try:
        resp = requests.get("https://mp.toutiao.com/mp/agw/creator_center/draft_list?type=0&count=50&app_id=1231", headers=headers, timeout=15)
        return resp.json().get("draft_list", [])
    except:
        return []

def upload_article(art, index, total):
    """上传单篇文章"""
    title = art["title"][:30]
    html_path = art["html_file"]

    print(f"\n[{index}/{total}] 上传: {title}")

    # 读取HTML正文
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    content_html = ""
    if body_match:
        body = body_match.group(1)
        parts = []
        for m in re.finditer(r'<p>(.*?)</p>', body, re.DOTALL):
            clean = re.sub(r"<[^>]+>", "", m.group(1))
            if clean.strip():
                parts.append(f'<p>{clean}</p>')
        content_html = "\n".join(parts)

    word_cnt = len(re.sub(r'<[^>]+>', '', content_html))
    print(f"  正文字数: {word_cnt}, 段数: {content_html.count('<p>')}")

    # 生成title_id
    title_id = f"{int(time.time()*1000)}_{random.randint(1000000000000000, 9999999999999999)}"

    # 构建请求体
    extra = {
        "content_source": "100000000402",
        "content_word_cnt": word_cnt,
        "is_multi_title": 0,
        "sub_titles": [],
        "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
        "tuwen_wtt_transfer_switch": "1"
    }

    form_data = {
        "source": "29",
        "extra": json.dumps(extra, ensure_ascii=False),
        "content": content_html,
        "title": title,
        "search_creation_info": json.dumps({"searchTopOne": 0, "abstract": "", "clue_id": ""}, ensure_ascii=False),
        "title_id": title_id,
        "mp_editor_stat": "{}",
        "is_refute_rumor": "0",
        "save": "1",  # 关键：save=1
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

    try:
        resp = requests.post(SAVE_URL, data=urlencode(form_data), headers=headers, timeout=30)
        result = resp.json()
        code = result.get("code", -1)
        pgc_id = result.get("data", {}).get("pgc_id", "0")
        message = result.get("message", "")

        if code == 0:
            print(f"  [SUCCESS] code=0, pgc_id={pgc_id}, message={message}")
            return True, pgc_id
        else:
            print(f"  [FAIL] code={code}, message={message}")
            return False, pgc_id
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False, "0"

# 开始批量上传
print(f"开始批量上传，共 {len(manifest)} 篇文章")
print(f"初始草稿数: {get_draft_count()}")

success_count = 0
results = []

for i, art in enumerate(manifest, 1):
    # 跳过已完成的第1篇
    if any(t in art["title"] for t in our_titles_done):
        print(f"\n[{i}/{len(manifest)}] 跳过已完成: {art['title'][:30]}")
        results.append({"index": i, "title": art["title"], "status": "skipped", "pgc_id": ""})
        success_count += 1
        continue

    success, pgc_id = upload_article(art, i, len(manifest))
    results.append({"index": i, "title": art["title"], "status": "success" if success else "fail", "pgc_id": pgc_id})

    if success:
        success_count += 1

    # 篇间等待3秒避免限流
    if i < len(manifest):
        time.sleep(3)

print(f"\n=== 上传完成 ===")
print(f"成功: {success_count}/{len(manifest)}")

# 等待几秒后检查草稿列表
print(f"\n等待5秒后检查草稿列表...")
time.sleep(5)

drafts = get_draft_list()
print(f"当前草稿数: {len(drafts)}")

# 验证9篇文章
print("\n=== 验证9篇文章 ===")
for r in results:
    title_prefix = r["title"][:8]
    found = False
    for d in drafts:
        ge = d.get("graphic_extra", "{}")
        try:
            ge_json = json.loads(ge) if isinstance(ge, str) else ge
            t = ge_json.get("title", "")
            if title_prefix in t:
                found = True
                print(f"  [{r['index']}] [OK] {r['title'][:30]} -> 草稿: {t[:30]}")
                break
        except:
            pass
    if not found:
        print(f"  [{r['index']}] [MISS] {r['title'][:30]}")

# 保存结果
with open("api_upload_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\n结果已保存到 api_upload_results.json")
print("DONE")
