#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""最简方案：Playwright上传图片 + 设置内容 + 等待自动保存"""
import os, re, json, base64, asyncio, io
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

async def paste_image(page, img_bytes):
    """粘贴图片到编辑器"""
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
            for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
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
        if url and not url.startswith('blob:') and not url.startswith('data:'): return url
    return ""

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章\n{'='*60}")

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

        # 验证登录
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期"); await browser.close(); return
        print("[OK] 登录有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            title = art["title"]
            html_path = art["html_file"]
            paragraphs, images = extract_html_text_and_images(html_path)
            img_bytes_list = [c for c in (compress_image_to_bytes(img) for img in images) if c]
            
            print(f"[{i}/{len(articles)}] {title}")
            print(f"  {len(paragraphs)}段, {len(img_bytes_list)}图")

            # 导航到发布页
            await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)  # 等待编辑器完全初始化

            # 关闭弹窗
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
                print("  [ERROR] 编辑器未就绪"); continue

            # 填标题
            title_el = page.locator('textarea[placeholder*="文章标题"]').first
            await title_el.fill(title)
            await asyncio.sleep(2)

            # 上传图片
            image_urls = []
            for img_bytes in img_bytes_list:
                url = await paste_image(page, img_bytes)
                if url: image_urls.append(url)
                await asyncio.sleep(1)
            print(f"  图片URL: {len(image_urls)}个")

            # 清除编辑器
            editor = page.locator(".ProseMirror").first
            await editor.click(); await asyncio.sleep(0.3)
            await page.keyboard.press("Control+a"); await asyncio.sleep(0.3)
            await page.keyboard.press("Backspace"); await asyncio.sleep(0.5)

            # 构建HTML
            content_parts = []
            img_idx, n_imgs = 0, len(image_urls)
            il = {1: 1, 3: 2, 5: 2} if n_imgs >= 5 else ({1: 1, 3: 2} if n_imgs >= 3 else {1: 1})
            for pi, pt in enumerate(paragraphs):
                content_parts.append(f"<p>{pt}</p>")
                if (pi + 1) in il:
                    for _ in range(il[pi + 1]):
                        if img_idx < n_imgs and image_urls[img_idx]:
                            content_parts.append(f'<p><img src="{image_urls[img_idx]}" alt=""></p>')
                            img_idx += 1
            content_html = "\n".join(content_parts)

            # 设置内容
            print(f"  设置内容 ({len(content_html)}字符)...")
            await page.evaluate("""
                (c) => {
                    const ed = document.querySelector('.ProseMirror');
                    if (ed) { ed.innerHTML = c; ed.dispatchEvent(new Event('input', {bubbles: true})); }
                }
            """, content_html)
            await asyncio.sleep(2)

            # 触发修改以启动自动保存
            await editor.click(); await asyncio.sleep(0.5)
            await page.keyboard.press("End"); await asyncio.sleep(0.3)
            await page.keyboard.type("X", delay=50); await asyncio.sleep(0.3)
            await page.keyboard.press("Backspace"); await asyncio.sleep(0.5)

            # 再次触发标题修改
            await page.evaluate("() => { const t = document.querySelector('textarea[placeholder*=\"文章标题\"]'); if(t) { t.focus(); t.dispatchEvent(new Event('input', {bubbles: true})); } }")
            await asyncio.sleep(1)

            # 等待自动保存
            print(f"  等待保存...")
            await asyncio.sleep(15)

            # 验证
            await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(5)
            dt = await page.evaluate("() => document.body.innerText || ''")
            if title[:8] in dt:
                print(f"  [SUCCESS] 已在草稿箱!")
                success += 1
            else:
                await asyncio.sleep(10)
                dt = await page.evaluate("() => document.body.innerText || ''")
                if title[:8] in dt:
                    print(f"  [SUCCESS] 已在草稿箱!")
                    success += 1
                else:
                    print(f"  [FAIL] 未找到 (页面{len(dt)}字符)")
            
            await asyncio.sleep(2)

        await browser.close()

    print(f"\n{'='*60}")
    print(f"完成: {success}/{len(articles)} 篇")

if __name__ == "__main__":
    asyncio.run(main())