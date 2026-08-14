#!/usr/bin/env python3
"""上传 v6 - 通过"预览并发布"按钮触发保存，然后返回不发布"""
import os, re, json, time, base64, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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

async def upload_images_get_urls(page, img_bytes_list):
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.innerHTML = '<p></p>';
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }
        """)
        await asyncio.sleep(0.5)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.3)

        b64_str = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return;
                editor.focus();
                const b = "{b64_str}";
                const bs = atob(b);
                const ab = new ArrayBuffer(bs.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                const blob = new Blob([ab], {{type: 'image/jpeg'}});
                const file = new File([blob], 'img_{img_idx}.jpg', {{type: 'image/jpeg'}});
                const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                const fd = {{files: [file], items: [], types: ['Files'],
                    getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}};
                Object.defineProperty(ev, 'clipboardData', {{value: fd}});
                editor.dispatchEvent(ev);
            }}
        """)

        img_url = ""
        for _ in range(60):
            await asyncio.sleep(1)
            img_url = await page.evaluate("""
                () => {
                    const img = document.querySelector('.ProseMirror img');
                    return img ? img.src : '';
                }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break
        image_urls.append(img_url)
        print(f"      图片{img_idx+1}: {'OK' if img_url else 'FAIL'}")
        await asyncio.sleep(1)
    return image_urls

async def process_article(page, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n[{index}/{total}] {title}")

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

    if not paragraphs:
        print("  [ERROR] 未提取到文字内容")
        return False

    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"  压缩: {len(img_bytes_list)}张")

    # 导航到发布页面
    await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 关闭弹窗
    try:
        for btn_text in ["关闭", "不恢复"]:
            btn = page.locator("text=" + btn_text).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(1)
    except:
        pass

    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except:
        print("  [ERROR] 编辑器未就绪")
        return False

    # 上传图片获取URL
    image_urls = []
    if img_bytes_list:
        print(f"  上传{len(img_bytes_list)}张图片...")
        image_urls = await upload_images_get_urls(page, img_bytes_list)
        valid = len([u for u in image_urls if u])
        print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

    valid_urls = [u for u in image_urls if u]
    n_imgs = len(valid_urls)
    image_layout = {}
    if n_imgs >= 5:
        image_layout = {1: 1, 3: 2, 5: 2}
    elif n_imgs >= 3:
        image_layout = {1: 1, 3: 2}
    elif n_imgs >= 1:
        image_layout = {1: 1}

    # 清空编辑器
    await page.evaluate("""
        () => {
            const editor = document.querySelector('.ProseMirror');
            if (editor) {
                editor.innerHTML = '<p></p>';
                editor.dispatchEvent(new Event('input', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(0.5)

    editor_el = page.locator('.ProseMirror').first
    await editor_el.click()
    await asyncio.sleep(0.5)

    # 逐段输入 + 图片
    print(f"  逐段输入内容 ({len(paragraphs)}段)...")
    img_idx = 0
    for pi, para_text in enumerate(paragraphs):
        print(f"    段落{pi+1}/{len(paragraphs)} ({len(para_text)}字)...")
        await editor_el.click()
        await asyncio.sleep(0.2)
        await page.keyboard.type(para_text, delay=5)
        await asyncio.sleep(0.3)
        await page.keyboard.press('Enter')
        await asyncio.sleep(0.3)

        target_para = pi + 1
        if target_para in image_layout:
            num = image_layout[target_para]
            for _ in range(num):
                if img_idx < len(valid_urls):
                    img_url = valid_urls[img_idx]
                    print(f"      插入图片{img_idx+1}...")
                    await page.evaluate(f"""
                        () => {{
                            const editor = document.querySelector('.ProseMirror');
                            if (!editor) return;
                            editor.focus();
                            const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                            const cd = {{
                                types: ['text/html'],
                                getData: function(type) {{ return type === 'text/html' ? '<img src="{img_url}" />' : ''; }},
                                setData: function() {{}},
                                clearData: function() {{}},
                                files: [],
                                items: []
                            }};
                            Object.defineProperty(ev, 'clipboardData', {{value: cd}});
                            editor.dispatchEvent(ev);
                        }}
                    """)
                    await asyncio.sleep(0.5)
                    await page.keyboard.press('Enter')
                    await asyncio.sleep(0.3)
                    img_idx += 1

    # 填写标题
    print(f"  填写标题...")
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    await title_el.click()
    await asyncio.sleep(0.5)
    await title_el.fill(title)
    await asyncio.sleep(2)

    # 触发编辑器事件
    await page.evaluate("""
        () => {
            const editor = document.querySelector('.ProseMirror');
            if (editor) {
                editor.dispatchEvent(new Event('input', {bubbles: true}));
                editor.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(3)

    # 点击"预览并发布"
    print(f"  点击'预览并发布'...")
    try:
        publish_btn = page.locator("button:has-text('预览并发布')").first
        await publish_btn.click()
        print(f"    已点击")
        await asyncio.sleep(5)

        # 检查是否进入了预览页面
        current_url = page.url
        print(f"    当前URL: {current_url[:100]}")

        # 预览页面应该有"确认发布"按钮，我们不要点它
        # 直接导航回草稿箱
        print(f"  返回草稿箱...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        
        return True
    except Exception as e:
        print(f"    [ERROR] {e}")
        return False

async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传到草稿箱")
    print("=" * 60)

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
        cookie_list = [{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        print("验证登录状态...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录状态有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                ok = await process_article(page, art, i, len(articles))
                if ok:
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(3)

        # 验证草稿箱
        print(f"\n=== 验证草稿箱 ===")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_content = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        for art in articles:
            title = art["title"]
            found = title[:6] in draft_content
            print(f"  {'[OK]' if found else '[MISS]'} {title}")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")

if __name__ == "__main__":
    asyncio.run(main())