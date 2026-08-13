#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""方案：Playwright上传图片 + 捕获pgc_id + API保存草稿"""
import os, re, json, time, base64, asyncio, io, requests
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"

def extract_html_text_and_images(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs, images = [], []
    for m in re.finditer(r'<p>([^<]+)</p>', html):
        text = m.group(1).strip()
        if text: paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', html):
        images.append(m.group(1))
    return paragraphs, images

def compress_image_to_bytes(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img_data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_data))
        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except: return None

async def upload_images_get_urls(page, img_bytes_list):
    """上传图片并获取CDN URL"""
    image_urls = []
    for img_bytes in img_bytes_list:
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) { e.innerHTML = '<p></p>'; e.dispatchEvent(new Event('input', {bubbles: true})); } }")
        await asyncio.sleep(0.3)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.3)
        b64_str = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return;
                editor.focus();
                const b64 = "{b64_str}";
                const byteString = atob(b64);
                const ab = new ArrayBuffer(byteString.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
                const blob = new Blob([ab], {{type: 'image/jpeg'}});
                const file = new File([blob], 'img.jpg', {{type: 'image/jpeg'}});
                const de = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                const fd = {{files: [file], items: [], types: ['Files'], getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}};
                Object.defineProperty(de, 'clipboardData', {{value: fd, writable: false, configurable: true}});
                editor.dispatchEvent(de);
            }}
        """)
        for _ in range(30):
            await asyncio.sleep(1)
            if await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length > 0"): break
        for _ in range(60):
            await asyncio.sleep(1)
            url = await page.evaluate("() => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }")
            if url and not url.startswith('blob:') and not url.startswith('data:'):
                image_urls.append(url)
                break
        await asyncio.sleep(1)
    return image_urls

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传\n{'='*60}")

    # API session
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://mp.toutiao.com/",
        "Origin": "https://mp.toutiao.com",
    })
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".toutiao.com", path="/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        cookie_list = [{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 拦截网络请求，捕获 pgc_id
        pgc_id_captured = []
        
        async def handle_response(response):
            if "/mp/agw/article/new" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    pgc_id = data.get("data", {}).get("pgc_id", "")
                    if pgc_id:
                        pgc_id_captured.append(pgc_id)
                        print(f"  [捕获] pgc_id: {pgc_id}")
                except: pass
            # 也捕获可能的 save API 返回
            if "/mp/agw/article/publish" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    print(f"  [API响应] {json.dumps(data, ensure_ascii=False)[:200]}")
                except: pass

        page.on("response", handle_response)

        # 验证登录
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录状态有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            title = art["title"]
            html_path = art["html_file"]
            paragraphs, images = extract_html_text_and_images(html_path)
            
            print(f"[{i}/{len(articles)}] {title}")
            print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

            img_bytes_list = [compress_image_to_bytes(img) for img in images if compress_image_to_bytes(img)]
            print(f"  压缩: {len(img_bytes_list)}张")

            # 导航到发布页面
            pgc_id_captured.clear()
            await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)

            # 关闭弹窗
            try:
                for btn_text in ["关闭", "不恢复", "取消"]:
                    btn = page.locator(f"button:has-text('{btn_text}')").first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await asyncio.sleep(1)
                # 关闭 drawer
                mask = page.locator(".byte-drawer-mask").first
                if await mask.is_visible(timeout=2000):
                    await page.evaluate("() => { const m = document.querySelector('.byte-drawer-mask'); if(m) m.remove(); }")
            except: pass

            try:
                await page.wait_for_selector(".ProseMirror", timeout=15000)
            except:
                print("  [ERROR] 编辑器未就绪")
                continue

            # 填标题
            title_el = page.locator('textarea[placeholder*="文章标题"]').first
            await title_el.fill(title)
            await asyncio.sleep(2)

            # 上传图片
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            print(f"  图片URL: {len(image_urls)}个")

            # 清除编辑器
            editor = page.locator(".ProseMirror").first
            await editor.click()
            await asyncio.sleep(0.3)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.3)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.5)

            # 构建HTML内容
            content_parts = []
            img_idx, n_imgs = 0, len(image_urls)
            image_layout = {1: 1, 3: 2, 5: 2} if n_imgs >= 5 else ({1: 1, 3: 2} if n_imgs >= 3 else {1: 1})
            for para_idx, para_text in enumerate(paragraphs):
                content_parts.append(f"<p>{para_text}</p>")
                if (para_idx + 1) in image_layout:
                    for _ in range(image_layout[para_idx + 1]):
                        if img_idx < n_imgs and image_urls[img_idx]:
                            content_parts.append(f'<p><img src="{image_urls[img_idx]}" alt=""></p>')
                            img_idx += 1

            content_html = "\n".join(content_parts)
            word_count = sum(len(p) for p in paragraphs)

            # 获取 pgc_id
            pgc_id = pgc_id_captured[0] if pgc_id_captured else ""
            if not pgc_id:
                # 尝试从页面获取
                pgc_id = await page.evaluate("""
                    () => {
                        // 尝试从各种可能的位置获取 pgc_id
                        const url = new URL(window.location.href);
                        const fromUrl = url.searchParams.get('pgc_id') || '';
                        if (fromUrl) return fromUrl;
                        // 尝试从 window.__INITIAL_STATE__ 获取
                        const state = window.__INITIAL_STATE__;
                        if (state && state.article && state.article.pgc_id) return state.article.pgc_id;
                        return '';
                    }
                """)
            
            if not pgc_id:
                print(f"  [WARN] 未获取到pgc_id，尝试API获取")
                resp = session.get("https://mp.toutiao.com/mp/agw/article/new", params={
                    "article_type": 0, "format": "json", "compat": 1, "column_no": "",
                })
                try:
                    data = resp.json()
                    pgc_id = data.get("data", {}).get("pgc_id", "")
                except: pass

            if not pgc_id:
                print(f"  [ERROR] 无法获取pgc_id，跳过")
                continue

            print(f"  pgc_id: {pgc_id}")

            # 通过API保存
            csrf = session.cookies.get('passport_csrf_token', '')
            extra = json.dumps({"content_source": 100000000402, "content_word_cnt": word_count})
            
            form_data = {
                "article_type": "0", "pgc_id": pgc_id, "source": "29",
                "title": title, "content": content_html, "save": "0",
                "entrance": "main", "timer_status": "0", "timer_time": "",
                "extra": extra, "title_id": "", "ic_uri_list": "[]",
                "search_creation_info": "", "is_refute_rumor": "0",
                "appid_list": "[]", "stock_ids": "[]", "concern_list": "[]",
                "comic_attr": "", "is_app_preview": "", "externalLinkChecked": "false",
                "externalLink": "", "claimOrigin": "0", "copyRightChecked": "1",
                "subTitle": "", "subCoverList": "[]", "coverList": "[]",
                "coverType": "0", "articleAdType": "0", "isFansArticle": "0",
                "activityId": "", "communitySync": "0",
            }

            print(f"  API保存 ({word_count}字, {n_imgs}图)...")
            try:
                resp = session.post(
                    "https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231",
                    data=form_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrf},
                )
                result = resp.json()
                code = result.get('code', -1)
                msg = result.get('message', '')
                if code == 0 or msg == 'success':
                    print(f"  [SUCCESS] 保存成功!")
                    success += 1
                else:
                    print(f"  [FAIL] code={code}, msg={msg}")
                    print(f"  响应: {resp.text[:300]}")
            except Exception as e:
                print(f"  [ERROR] {e}")

            await asyncio.sleep(2)

        await browser.close()

    # 验证
    print(f"\n{'='*60}")
    print(f"验证草稿箱...")
    resp = session.get("https://mp.toutiao.com/profile_v4/manage/draft")
    draft_count = resp.text.count('编辑删除')
    print(f"  草稿箱文章数(估算): {draft_count}")
    print(f"上传完成: {success}/{len(articles)} 篇")

if __name__ == "__main__":
    asyncio.run(main())