#!/usr/bin/env python3
"""v24: 直接调用 save_ugc_draft API 保存草稿

策略：
1. 浏览器打开发布页，上传图片获取URL
2. 构建HTML内容（文字+图片URL）
3. 通过浏览器 fetch 调用 save_ugc_draft API
"""
import os, re, json, time, base64, asyncio, io, sys
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

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
        while len(pos_list) > 1 and (total_paragraphs - pos_list[-1] < 1): pos_list.pop()
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
    for i, p in enumerate(best_positions): layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))

def extract_html_text_and_images(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs, images = [], []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body = body_match.group(1) if body_match else html
    for m in re.finditer(r'<p>([^<]+)</p>', body):
        text = m.group(1).strip()
        if text: paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', body):
        images.append(m.group(1))
    return paragraphs, images

def compress_image_to_bytes(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
        w, h = img.size
        if w > max_width: img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except: return None

async def run():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章", flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=UA
        )
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])

        print("验证登录...", flush=True)
        page = await context.new_page()
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期", flush=True)
            await browser.close()
            return
        print("[OK] 登录有效", flush=True)
        await page.close()

        # 先打开发布页获取msToken和csrf
        page = await context.new_page()
        await page.goto(f"{PUBLISH_URL}?_t={int(time.time()*1000)}", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 关闭弹窗
        await page.evaluate("""
            () => { document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => { if (m && m.parentNode) m.parentNode.removeChild(m); }); }
        """)
        await asyncio.sleep(0.5)
        for btn_text in ["关闭", "不恢复", "知道了", "确定"]:
            try:
                btn = page.locator("text=" + btn_text).first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    await asyncio.sleep(0.3)
            except: pass

        # 等待编辑器就绪
        for _ in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); return ed && ed.getBoundingClientRect().width > 0; }
            """)
            if ready: break

        # 捕获msToken
        ms_token = [None]
        async def on_response(response):
            if 'article/publish' in response.url:
                import re as _re
                m = _re.search(r'msToken=([^&]+)', response.url)
                if m and not ms_token[0]:
                    ms_token[0] = m.group(1)
                    print(f"  msToken: {ms_token[0][:20]}...", flush=True)
        page.on('response', on_response)

        # 触发一次自动保存来获取msToken
        try:
            title_el = page.locator('textarea[placeholder*="文章标题"]').first
            await title_el.click(timeout=3000)
            await asyncio.sleep(0.3)
            await title_el.press('Space')
            await asyncio.sleep(0.3)
            await title_el.press('Backspace')
            await asyncio.sleep(0.5)
            await title_el.blur()
        except: pass
        await asyncio.sleep(5)

        success = 0
        for art_idx, art in enumerate(articles):
            i = art_idx + 1
            title = art["title"]
            html_path = art["html_file"]

            print(f"\n{'='*60}", flush=True)
            print(f"[{i}/{len(articles)}] {title}", flush=True)
            print(f"{'='*60}", flush=True)

            paragraphs, images = extract_html_text_and_images(html_path)
            img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
            image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
            print(f"  内容: {len(paragraphs)}段, {len(img_bytes_list)}张图 | 布局: {image_layout}", flush=True)

            # 上传图片获取URL
            print(f"  [1] 上传图片...", flush=True)
            await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.focus(); document.execCommand('selectAll'); document.execCommand('delete'); } }
            """)
            await asyncio.sleep(0.5)

            image_urls = []
            for img_idx, img_bytes in enumerate(img_bytes_list):
                b64 = base64.b64encode(img_bytes).decode('ascii')
                await page.evaluate("""
                    (b64) => {
                        const ed = document.querySelector('.ProseMirror');
                        if (!ed) return;
                        ed.focus();
                        const bs = atob(b64);
                        const ab = new ArrayBuffer(bs.length);
                        const ia = new Uint8Array(ab);
                        for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                        const blob = new Blob([ab], {type: 'image/jpeg'});
                        const file = new File([blob], 'img.jpg', {type: 'image/jpeg'});
                        const ev = new ClipboardEvent('paste', {bubbles: true, cancelable: true});
                        Object.defineProperty(ev, 'clipboardData', {
                            value: {files: [file], items: [], types: ['Files'],
                                getData: function() { return ''; }, setData: function() {}, clearData: function() {}}
                        });
                        ed.dispatchEvent(ev);
                    }
                """, b64)

                url = ""
                for _ in range(30):
                    await asyncio.sleep(0.5)
                    url = await page.evaluate("""
                        () => { const imgs = document.querySelectorAll('.ProseMirror img'); return imgs.length ? imgs[imgs.length-1].src : ''; }
                    """)
                    if url and not url.startswith('blob:') and not url.startswith('data:'): break

                print(f"    图{img_idx+1}: {'OK' if url else 'FAIL'}", flush=True)
                image_urls.append(url)

            valid_urls = [u for u in image_urls if u]
            print(f"  上传结果: {len(valid_urls)}/{len(img_bytes_list)}张", flush=True)

            # 构建HTML内容
            print(f"  [2] 构建HTML内容...", flush=True)
            html_content = ""
            url_idx = 0
            for para_idx, para_text in enumerate(paragraphs):
                para_num = para_idx + 1
                html_content += f"<p>{para_text}</p>"
                if para_num in image_layout:
                    num_imgs = image_layout[para_num]
                    for _ in range(num_imgs):
                        if url_idx < len(valid_urls):
                            html_content += f'<p><img src="{valid_urls[url_idx]}" alt="图片来源于网络"></p>'
                            url_idx += 1

            print(f"  HTML: {len(html_content)}字符", flush=True)

            # 通过API保存
            print(f"  [3] API保存...", flush=True)
            csrf = cookies.get('passport_csrf_token', '')

            result = await page.evaluate(f"""
                async () => {{
                    const body = {{
                        title: {json.dumps(title)},
                        content: {json.dumps(html_content)},
                        draft_type: 1,
                        article_type: 0,
                        abstract: {json.dumps(paragraphs[0][:100] if paragraphs else '')},
                        is_draft: true,
                        source: 'mp'
                    }};
                    try {{
                        const resp = await fetch('/mp/agw/draft/save_ugc_draft', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                'X-CSRFToken': {json.dumps(csrf)}
                            }},
                            body: JSON.stringify(body)
                        }});
                        const data = await resp.json();
                        return JSON.stringify(data);
                    }} catch(e) {{
                        return 'error: ' + e.message;
                    }}
                }}
            """)
            print(f"  响应: {result[:300]}", flush=True)

            try:
                result_data = json.loads(result)
                if result_data.get('code') == 0:
                    print(f"  [OK] 保存成功!", flush=True)
                    success += 1
                else:
                    print(f"  [FAIL] code={result_data.get('code')}, msg={result_data.get('message')}", flush=True)
            except:
                print(f"  [FAIL] 解析失败: {result[:200]}", flush=True)

            await asyncio.sleep(2)

        await page.close()
        await browser.close()

    print(f"\n上传完成: {success}/{len(articles)} 篇成功", flush=True)

if __name__ == "__main__":
    asyncio.run(run())