#!/usr/bin/env python
"""测试：用html.escape转义段落文字"""
import os, re, json, base64, asyncio, io, html as html_mod
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

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    art = articles[0]  # 测试第1篇
    title = art["title"]
    html_path = art["html_file"]
    paragraphs, images = extract_html_text_and_images(html_path)
    img_bytes_list = [c for c in (compress_image_to_bytes(img) for img in images) if c]
    
    print(f"测试: {title}")
    print(f"  {len(paragraphs)}段, {len(img_bytes_list)}图")

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

        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        print("[OK] 登录有效\n")

        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        try:
            for txt in ["关闭", "不恢复", "取消"]:
                b = page.locator(f"button:has-text('{txt}')").first
                if await b.is_visible(timeout=2000): await b.click(); await asyncio.sleep(1)
            m = page.locator(".byte-drawer-mask").first
            if await m.is_visible(timeout=2000):
                await page.evaluate("() => { const x = document.querySelector('.byte-drawer-mask'); if(x) x.remove(); }")
        except: pass

        try:
            await page.wait_for_selector(".ProseMirror", timeout=15000)
        except:
            print("[ERROR] 编辑器未就绪"); await browser.close(); return

        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.fill(title)
        await asyncio.sleep(2)

        editor = page.locator(".ProseMirror").first
        image_urls = []
        for img_bytes in img_bytes_list:
            await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) { e.innerHTML = '<p></p>'; e.dispatchEvent(new Event('input', {bubbles: true})); } }")
            await asyncio.sleep(0.3)
            await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
            await asyncio.sleep(0.3)
            b64 = base64.b64encode(img_bytes).decode('ascii')
            await page.evaluate(f"""
                () => {{
                    const ed = document.querySelector('.ProseMirror');
                    if (!ed) return;
                    ed.focus();
                    const b = "{b64}";
                    const bs = atob(b);
                    const ab = new ArrayBuffer(bs.length);
                    const ia = new Uint8Array(ab);
                    for (let j = 0; j < bs.length; j++) ia[j] = bs.charCodeAt(j);
                    const blob = new Blob([ab], {{type: 'image/jpeg'}});
                    const file = new File([blob], 'img.jpg', {{type: 'image/jpeg'}});
                    const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                    const fd = {{files: [file], items: [], types: ['Files'], getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}};
                    Object.defineProperty(ev, 'clipboardData', {{value: fd}});
                    ed.dispatchEvent(ev);
                }}
            """)
            for _ in range(30):
                await asyncio.sleep(1)
                if await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length > 0"): break
            for _ in range(60):
                await asyncio.sleep(1)
                url = await page.evaluate("() => { const i = document.querySelector('.ProseMirror img'); return i ? i.src : ''; }")
                if url and not url.startswith('blob:') and not url.startswith('data:'):
                    image_urls.append(url)
                    break
            await asyncio.sleep(1)

        print(f"  图片URL: {len(image_urls)}个")

        await editor.click(); await asyncio.sleep(0.3)
        await page.keyboard.press("Control+a"); await asyncio.sleep(0.3)
        await page.keyboard.press("Backspace"); await asyncio.sleep(0.5)

        # 构建HTML - 使用html.escape转义段落文字
        content_parts = []
        img_idx, n_imgs = 0, len(image_urls)
        il = {1: 1, 3: 2, 5: 2} if n_imgs >= 5 else ({1: 1, 3: 2} if n_imgs >= 3 else {1: 1})
        for pi, pt in enumerate(paragraphs):
            content_parts.append(f"<p>{html_mod.escape(pt)}</p>")
            if (pi + 1) in il:
                for _ in range(il[pi + 1]):
                    if img_idx < n_imgs and image_urls[img_idx]:
                        content_parts.append(f'<p><img src="{html_mod.escape(image_urls[img_idx])}" alt=""></p>')
                        img_idx += 1
        content_html = "\n".join(content_parts)

        print(f"  设置内容 ({len(content_html)}字符)...")
        await page.evaluate("""
            (c) => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = c; ed.dispatchEvent(new Event('input', {bubbles: true})); }
            }
        """, content_html)
        await asyncio.sleep(3)

        await editor.click(); await asyncio.sleep(0.5)
        await page.keyboard.press("End"); await asyncio.sleep(0.3)
        await page.keyboard.type("X", delay=50); await asyncio.sleep(0.3)
        await page.keyboard.press("Backspace"); await asyncio.sleep(0.5)

        await page.evaluate("() => { const t = document.querySelector('textarea[placeholder*=\"文章标题\"]'); if(t) { t.focus(); t.dispatchEvent(new Event('input', {bubbles: true})); } }")
        await asyncio.sleep(1)

        print(f"  等待保存...")
        await asyncio.sleep(15)

        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        dt = await page.evaluate("() => document.body.innerText || ''")
        if title[:8] in dt:
            print(f"  [SUCCESS] 已在草稿箱!")
        else:
            await asyncio.sleep(10)
            dt = await page.evaluate("() => document.body.innerText || ''")
            if title[:8] in dt:
                print(f"  [SUCCESS] 已在草稿箱!")
            else:
                print(f"  [FAIL] (页面{len(dt)}字符)")
                print(f"  页面内容: {dt[:500]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())