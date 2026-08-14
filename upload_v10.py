#!/usr/bin/env python3
"""v10: 直接API上传 - 绕过浏览器，使用requests直接调用保存API

策略:
1. 从article/new获取pgc_id
2. 使用cookie直接调用publish API
3. 分析7050错误原因
"""
import os, re, json, time, base64, requests, urllib.parse
from PIL import Image
import io

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def calc_image_layout(total_paragraphs, num_images=5):
    if total_paragraphs < 1: return {}
    n_groups = (num_images - 1) // 2
    if n_groups <= 0: return {1: 1} if num_images >= 1 else {}
    first = 1
    def _build_positions(last):
        if last < 3: return [first]
        pos_list = [first]
        if n_groups == 1: pos_list.append(last)
        else:
            step = (last - first) / n_groups
            for k in range(1, n_groups + 1):
                if k == n_groups: raw = last
                else: raw = first + step * k
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
        if len(pos_list) < 2: return 0
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
    if not candidates: return {1: 1}
    def _score(c):
        gap, tail, pos = c
        return (0 if gap <= 3 else 1, 0 if tail <= 2 else 1, gap, tail)
    candidates.sort(key=_score)
    best_positions = candidates[0][2]
    layout = {}
    for i, p in enumerate(best_positions):
        layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))

def extract_html_content(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs = []
    images = []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if body_match:
        body = body_match.group(1)
        for m in re.finditer(
            r'(<p>(.*?)</p>)|'
            r'(<div\s+class="img-wrap">\s*<img[^>]*src="(data:image/[^"]*;base64,[^"]*)"[^>]*>.*?</div>)',
            body, re.DOTALL
        ):
            if m.group(1):
                clean = re.sub(r"<[^>]+>", "", m.group(2))
                if clean.strip():
                    paragraphs.append(clean.strip())
            elif m.group(4):
                images.append(m.group(4))
    return paragraphs, images

def compress_image(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except:
        return None

def build_html_content(paragraphs, image_urls, image_layout):
    """构建头条编辑器格式的HTML内容"""
    parts = []
    img_idx = 0
    
    for p_idx, para_text in enumerate(paragraphs):
        para_num = p_idx + 1
        # 段落
        parts.append(f"<p>{para_text}</p>")
        
        # 检查是否需要在此段落后插入图片
        imgs_needed = image_layout.get(para_num, 0)
        for _ in range(imgs_needed):
            if img_idx < len(image_urls) and image_urls[img_idx]:
                url = image_urls[img_idx]
                parts.append(
                    f'<div class="pgc-img">'
                    f'<img src="{url}" icUri="{url}" catchErrorUrl="" link="" '
                    f'caption="图片来源于网络" ic="false" naturalHeight="0" naturalWidth="0" '
                    f'srcType="" captionLenErr="false" needCheck="false"/>'
                    f'</div>'
                )
                img_idx += 1
    
    return "".join(parts)

def main():
    print("=" * 60)
    print("v10: API直接上传")
    print("=" * 60)
    
    # 加载cookies
    with open(COOKIE_FILE) as f:
        cookies = json.load(f)
    
    with open(MANIFEST_FILE) as f:
        manifest = json.load(f)
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Origin": "https://mp.toutiao.com",
        "Referer": "https://mp.toutiao.com/",
        "Accept": "application/json, text/plain, */*",
    })
    for name, value in cookies.items():
        session.cookies.set(name, str(value), domain=".toutiao.com", path="/")
    
    csrf = cookies.get('passport_csrf_token', '')
    
    # 只处理第一篇
    art = manifest[0]
    title = art["title"]
    html_path = art["html_file"]
    
    print(f"\n文章: {title}")
    
    paragraphs, images_base64 = extract_html_content(html_path)
    print(f"  内容: {len(paragraphs)}段, {len(images_base64)}张图")
    
    img_bytes_list = []
    for img in images_base64:
        compressed = compress_image(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"  压缩: {len(img_bytes_list)}张有效")
    
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  布局: {image_layout}")
    
    # Step 1: 获取pgc_id
    print("\n[1] 获取pgc_id...")
    resp = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
        "article_type": 0, "format": "json", "compat": 1, "column_no": "",
    })
    new_data = resp.json()
    print(f"  article/new: {json.dumps(new_data, ensure_ascii=False)[:500]}")
    
    pgc_id = new_data.get('data', {}).get('pgc', {}).get('id', '') or \
             new_data.get('data', {}).get('media', {}).get('id', '')
    print(f"  pgc_id: {pgc_id}")
    
    # Step 2: 上传图片 (我们需要先上传图片获取URL)
    # 图片上传需要multipart/form-data到图片上传端点
    print("\n[2] 上传图片...")
    image_urls = []
    
    for img_idx, img_bytes in enumerate(img_bytes_list):
        # 尝试上传图片
        files = {'file': (f'img_{img_idx}.jpg', img_bytes, 'image/jpeg')}
        try:
            upload_resp = session.post(
                "https://mp.toutiao.com/mp/agw/article/upload_image",
                files=files,
                params={"source": "mp", "type": "article"},
            )
            upload_data = upload_resp.json()
            print(f"  图片{img_idx+1}: {json.dumps(upload_data, ensure_ascii=False)[:200]}")
            if upload_data.get('code') == 0:
                img_url = upload_data.get('data', {}).get('url', '') or \
                          upload_data.get('data', {}).get('web_url', '')
                if img_url:
                    image_urls.append(img_url)
                    continue
        except Exception as e:
            print(f"  图片{img_idx+1}: upload失败 ({e})")
        
        image_urls.append("")
    
    valid_urls = [u for u in image_urls if u]
    print(f"  有效URL: {len(valid_urls)}/{len(img_bytes_list)}")
    
    if not valid_urls:
        print("  [ERROR] 没有成功上传的图片")
        # 尝试备用方案
        print("  尝试备用上传端点...")
        for img_idx, img_bytes in enumerate(img_bytes_list):
            files = {'upfile': (f'img_{img_idx}.jpg', img_bytes, 'image/jpeg')}
            try:
                upload_resp = session.post(
                    "https://mp.toutiao.com/mp/agw/ugc/image/upload",
                    files=files,
                )
                print(f"  ugc/upload 图片{img_idx+1}: {upload_resp.text[:200]}")
            except Exception as e:
                print(f"  ugc/upload 图片{img_idx+1}: {e}")
    
    valid_urls = [u for u in image_urls if u]
    
    # Step 3: 构建并保存
    if valid_urls:
        print("\n[3] 构建HTML并保存...")
        html_content = build_html_content(paragraphs, valid_urls, image_layout)
        print(f"  HTML长度: {len(html_content)}")
        
        extra = {
            "content_source": 100000000402,
            "content_word_cnt": len("".join(paragraphs)),
            "is_multi_title": 0,
            "sub_titles": [],
            "gd_ext": {
                "entrance": "",
                "from_page": "publisher_mp",
                "enter_from": "PC",
                "device_platform": "mp",
                "is_message": 0
            },
            "tuwen_wtt_trans_flag": "0"
        }
        
        form_data = {
            "source": "29",
            "article_type": "0",
            "pgc_id": str(pgc_id) if pgc_id else "0",
            "title": title,
            "content": html_content,
            "extra": json.dumps(extra, ensure_ascii=False),
        }
        
        print(f"  form_data keys: {list(form_data.keys())}")
        print(f"  pgc_id: {form_data['pgc_id']}")
        print(f"  title: {form_data['title'][:30]}")
        
        # 尝试不带pgc_id
        for pgc_val in [str(pgc_id) if pgc_id else "", "0", ""]:
            trial_data = dict(form_data)
            trial_data["pgc_id"] = pgc_val
            
            print(f"\n  尝试 pgc_id='{pgc_val}':")
            resp = session.post(
                "https://mp.toutiao.com/mp/agw/article/publish",
                params={"source": "mp", "type": "article", "aid": "1231"},
                data=trial_data,
                headers={"Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrf}
            )
            result = resp.json()
            print(f"    响应: code={result.get('code')}, msg={result.get('message','')}")
            
            if result.get('code') == 0:
                print(f"    [SUCCESS]!")
                break
    
    # Step 4: 检查草稿箱
    print("\n[4] 检查草稿箱...")
    resp = session.get("https://mp.toutiao.com/mp/agw/creator_center/draft_list", params={
        "type": 2, "count": 5, "app_id": 1231
    })
    data = resp.json()
    if data.get('code') == 0:
        for draft in data.get('draft_list', [])[:5]:
            print(f"  - {draft.get('title','')[:40]}")

if __name__ == "__main__":
    main()