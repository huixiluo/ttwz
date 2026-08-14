#!/usr/bin/env python3
"""头条草稿箱上传 v7 - 快速键盘输入 + 图片粘贴，触发自动保存

修复：
1. byte-drawer-mask 遮罩处理
2. 自动保存触发优化
"""
import os, re, json, time, base64, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"


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
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
        w, h = img.size
        if w > max_width: img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()
    except: return None


def calc_image_layout(total_paragraphs, num_images):
    if num_images <= 0: return {}
    if num_images == 1: return {1: 1}
    if num_images == 2: return {1: 1, total_paragraphs: 1} if total_paragraphs > 1 else {1: 2}
    if num_images == 3: return {1: 1, 3: 2} if total_paragraphs >= 4 else {1: 1, total_paragraphs: 2}
    if num_images == 4: return {1: 1, 3: 2, total_paragraphs: 1} if total_paragraphs >= 4 else {1: 1, 2: 2, total_paragraphs: 1}
    candidates = []
    for tail in [2, 3]:
        last = total_paragraphs - tail
        if last >= 5:
            gap = (last - 1) / 2
            pos = [1, int(round(1 + gap)), last]
            if pos[1] - pos[0] >= 2 and pos[2] - pos[1] >= 2:
                candidates.append((max(pos[1]-pos[0]-1, pos[2]-pos[1]-1), total_paragraphs - pos[2], pos))
    if not candidates: return {1: 1, 3: 2, 5: 2}
    candidates.sort(key=lambda x: (0 if x[0] <= 3 else 1, 0 if x[1] <= 2 else 1, x[0], x[1]))
    best = candidates[0][2]
    return {best[0]: 1, best[1]: 2, best[2]: 2}


async def remove_overlays(page):
    await page.evaluate("""
        () => {
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper').forEach(m => {
                if (m && m.parentNode) m.parentNode.removeChild(m);
            });
        }
    """)
    await asyncio.sleep(0.3)


async def safe_editor_focus(page):
    """安全聚焦编辑器"""
    await remove_overlays(page)
    await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
    await asyncio.sleep(0.2)


async def upload_images_get_urls(page, img_bytes_list):
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await safe_editor_focus(page)
        await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.innerHTML = ''; }")
        await asyncio.sleep(0.2)

        b64 = base64.b64encode(img_bytes).decode('ascii')
        await page.evaluate(f"""
            () => {{
                const ed = document.querySelector('.ProseMirror');
                if (!ed) return;
                ed.focus();
                const bs = atob("{b64}");
                const ab = new ArrayBuffer(bs.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < bs.length; i++) ia[i] = bs.charCodeAt(i);
                const blob = new Blob([ab], {{type: 'image/jpeg'}});
                const file = new File([blob], 'img.jpg', {{type: 'image/jpeg'}});
                const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
                Object.defineProperty(ev, 'clipboardData', {{
                    value: {{files: [file], items: [], types: ['Files'],
                        getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}}
                }});
                ed.dispatchEvent(ev);
            }}
        """)

        img_url = ""
        for _ in range(30):
            await asyncio.sleep(1)
            img_url = await page.evaluate("() => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }")
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'): break

        print("OK" if img_url and not img_url.startswith('blob:') else "FAIL")
        image_urls.append(img_url if img_url and not img_url.startswith('blob:') else "")
        await asyncio.sleep(0.3)
    return image_urls


async def paste_image_url(page, img_url):
    await page.evaluate(f"""
        () => {{
            const ed = document.querySelector('.ProseMirror');
            if (!ed) return;
            ed.focus();
            const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
            const cd = {{
                types: ['text/html'],
                getData: function(type) {{ return type === 'text/html' ? '<img src="{img_url}" />' : ''; }},
                setData: function() {{}}, clearData: function() {{}}, files: [], items: []
            }};
            Object.defineProperty(ev, 'clipboardData', {{value: cd}});
            ed.dispatchEvent(ev);
        }}
    """)


async def wait_for_save(page, timeout=60):
    for i in range(timeout):
        await asyncio.sleep(1)
        result = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return true;
                const btns = document.querySelectorAll('button, span');
                for (let j = 0; j < btns.length; j++) {
                    if ((btns[j].textContent || '').indexOf('草稿已保存') !== -1) return true;
                }
                return false;
            }
        """)
        if result:
            print(f"  [{i+1}s] 保存成功!")
            return True
    return False


async def process_article(page, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] 文件不存在: {html_path}")
        return False

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    print(f"  压缩: {len(img_bytes_list)}张")

    print(f"  导航到发布页面...")
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    await remove_overlays(page)
    try:
        for btn_text in ["关闭", "不恢复"]:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(0.5)
    except: pass

    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except:
        print("  [ERROR] 编辑器未就绪")
        return False

    # 上传图片
    image_urls = []
    if img_bytes_list:
        print(f"  上传图片...")
        image_urls = await upload_images_get_urls(page, img_bytes_list)
        valid = len([u for u in image_urls if u])
        print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

    valid_urls = [u for u in image_urls if u]
    image_layout = calc_image_layout(len(paragraphs), len(valid_urls))
    print(f"  图片布局: {image_layout}")

    # 输入内容
    print(f"  输入内容 ({len(paragraphs)}段文字, {len(valid_urls)}张图片)...")

    await safe_editor_focus(page)
    await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = ''; ed.focus(); } }")
    await asyncio.sleep(0.3)

    img_idx = 0
    t0 = time.time()
    for pi, para_text in enumerate(paragraphs):
        await safe_editor_focus(page)
        await page.keyboard.type(para_text, delay=0)
        await asyncio.sleep(0.1)
        await page.keyboard.press('Enter')
        await asyncio.sleep(0.1)

        target_para = pi + 1
        if target_para in image_layout:
            for _ in range(image_layout[target_para]):
                if img_idx < len(valid_urls):
                    await paste_image_url(page, valid_urls[img_idx])
                    await asyncio.sleep(0.3)
                    await page.keyboard.press('Enter')
                    await asyncio.sleep(0.1)
                    img_idx += 1

    print(f"  输入完成 ({time.time()-t0:.1f}s)")

    # 填写标题
    print(f"  填写标题...")
    await remove_overlays(page)
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    await title_el.click(timeout=5000)
    await asyncio.sleep(0.3)
    await title_el.fill(title)
    await asyncio.sleep(2)

    # 触发编辑器事件
    await page.evaluate("""
        () => {
            const ed = document.querySelector('.ProseMirror');
            if (ed) {
                ed.dispatchEvent(new Event('input', {bubbles: true}));
                ed.dispatchEvent(new Event('change', {bubbles: true}));
                ed.dispatchEvent(new Event('blur', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(2)

    # 等待自动保存
    print(f"  等待自动保存 (60秒)...")
    saved = await wait_for_save(page, 60)

    if not saved:
        print(f"  未检测到自动保存，手动触发...")
        await safe_editor_focus(page)
        await page.keyboard.press('Space')
        await asyncio.sleep(0.2)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(3)
        saved = await wait_for_save(page, 20)

    await page.screenshot(path=f"/workspace/editor_v7_art{index}.png")
    return saved


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=UA)
        await context.add_cookies([{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()])
        page = await context.new_page()

        print("验证登录...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                if await process_article(page, art, i, len(articles)):
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [ERROR] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)

        print(f"\n{'='*60}")
        print(f"验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
        for art in articles:
            found = art["title"][:6] in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:30]}")

        await page.screenshot(path="/workspace/draft_v7_final.png")
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())