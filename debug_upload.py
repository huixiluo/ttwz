#!/usr/bin/env python
"""Debug: check if content is properly set in editor"""
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
    paragraphs = []
    images = []
    for m in re.finditer(r'<p>([^<]+)</p>', html):
        text = m.group(1).strip()
        if text:
            paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', html):
        images.append(m.group(1))
    return paragraphs, images

def compress_image_to_bytes(data_url, max_width=800):
    try:
        header, b64 = data_url.split(',', 1)
        img_data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_data))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except:
        return None

async def debug_article(page, art, tag):
    title = art["title"]
    html_path = art["html_file"]
    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  {tag}: {len(paragraphs)}段, {len(images)}张图")

    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)

    await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except:
        print("  Editor not ready")
        return

    # Fill title
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    await title_el.fill(title)
    await asyncio.sleep(2)

    # Upload images
    editor = page.locator(".ProseMirror").first
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
                const pasteEvent = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                const fakeData = {{files: [file], items: [], types: ['Files'], getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}};
                Object.defineProperty(pasteEvent, 'clipboardData', {{value: fakeData, writable: false, configurable: true}});
                editor.dispatchEvent(pasteEvent);
            }}
        """)
        for _ in range(30):
            await asyncio.sleep(1)
            has_img = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length > 0")
            if has_img:
                break
        for _ in range(60):
            await asyncio.sleep(1)
            url = await page.evaluate("() => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }")
            if url and not url.startswith('blob:') and not url.startswith('data:'):
                image_urls.append(url)
                break
        await asyncio.sleep(1)

    print(f"  Got {len(image_urls)} image URLs")

    # Clear editor
    await editor.click()
    await asyncio.sleep(0.3)
    await page.keyboard.press("Control+a")
    await asyncio.sleep(0.3)
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.5)

    # Build content
    content_parts = []
    img_idx = 0
    n_imgs = len(image_urls)
    image_layout = {1: 1, 3: 2, 5: 2} if n_imgs >= 5 else ({1: 1, 3: 2} if n_imgs >= 3 else {1: 1})
    for para_idx, para_text in enumerate(paragraphs):
        content_parts.append(f"<p>{para_text}</p>")
        target_para = para_idx + 1
        if target_para in image_layout:
            for _ in range(image_layout[target_para]):
                if img_idx < n_imgs and image_urls[img_idx]:
                    content_parts.append(f'<p><img src="{image_urls[img_idx]}" alt=""></p>')
                    img_idx += 1

    content_html = "\n".join(content_parts)
    print(f"  Content HTML length: {len(content_html)}")

    # Method 1: innerHTML
    await page.evaluate("""
        (content) => {
            const editor = document.querySelector('.ProseMirror');
            if (editor) {
                editor.innerHTML = content;
                editor.dispatchEvent(new Event('input', {bubbles: true}));
            }
        }
    """, content_html)
    await asyncio.sleep(3)

    # Check what's in the editor
    editor_html = await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); return e ? e.innerHTML.substring(0, 500) : 'NO EDITOR'; }")
    editor_text = await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); return e ? e.innerText.substring(0, 500) : 'NO EDITOR'; }")
    print(f"  Editor innerHTML (first 500): {editor_html}")
    print(f"  Editor innerText (first 500): {editor_text}")

    await page.screenshot(path=f"/workspace/debug_{tag}_after_set.png", full_page=False)
    print(f"  Screenshot saved: debug_{tag}_after_set.png")

    # Trigger save
    await editor.click()
    await asyncio.sleep(0.5)
    await page.keyboard.press("End")
    await asyncio.sleep(0.3)
    await page.keyboard.type(" ", delay=50)
    await asyncio.sleep(0.3)
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.5)

    # Check if save button exists
    save_btns = await page.evaluate("""
        () => {
            const btns = document.querySelectorAll('button');
            return Array.from(btns).map(b => b.innerText).filter(t => t.includes('存') || t.includes('保存') || t.includes('草稿'));
        }
    """)
    print(f"  Save buttons found: {save_btns}")

    # Wait for save
    for _ in range(30):
        await asyncio.sleep(1)
        saved = await page.evaluate("() => { const b = document.body.innerText || ''; return b.includes('草稿已保存') || b.includes('保存成功') || b.includes('已保存'); }")
        if saved:
            print(f"  Save confirmed!")
            break
    else:
        print(f"  Save NOT confirmed")

    await page.screenshot(path=f"/workspace/debug_{tag}_after_save.png", full_page=False)
    print(f"  Screenshot saved: debug_{tag}_after_save.png")

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
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
        print("[OK] Logged in\n")

        # Debug article 1 (fails)
        print("=== DEBUG Article 1 ===")
        await debug_article(page, articles[0], "art1")

        # Debug article 2 (succeeds)
        print("\n=== DEBUG Article 2 ===")
        await debug_article(page, articles[1], "art2")

        await browser.close()

asyncio.run(main())