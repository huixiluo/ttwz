#!/usr/bin/env python3
"""头条草稿箱上传 v6 - 通过 HTML 粘贴到 ProseMirror 编辑器

策略：使用剪贴板API粘贴完整HTML内容到ProseMirror编辑器，让页面自动保存
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
    except Exception:
        return None


def calc_image_layout(total_paragraphs, num_images):
    if num_images <= 0 or total_paragraphs < 1:
        return {}
    if num_images == 1:
        return {1: 1}
    if num_images == 2:
        return {1: 1, total_paragraphs: 1} if total_paragraphs > 1 else {1: 2}
    if num_images == 3:
        return {1: 1, 3: 2} if total_paragraphs >= 4 else {1: 1, total_paragraphs: 2}
    if num_images == 4:
        return {1: 1, 3: 2, total_paragraphs: 1} if total_paragraphs >= 4 else {1: 1, 2: 2, total_paragraphs: 1}
    candidates = []
    for tail in [2, 3]:
        last = total_paragraphs - tail
        if last >= 5:
            gap = (last - 1) / 2
            pos = [1, int(round(1 + gap)), last]
            if pos[1] - pos[0] >= 2 and pos[2] - pos[1] >= 2:
                actual_tail = total_paragraphs - pos[2]
                candidates.append((max(pos[1]-pos[0]-1, pos[2]-pos[1]-1), actual_tail, pos))
    if not candidates:
        return {1: 1, 3: 2, 5: 2}
    candidates.sort(key=lambda x: (0 if x[0] <= 3 else 1, 0 if x[1] <= 2 else 1, x[0], x[1]))
    best = candidates[0][2]
    return {best[0]: 1, best[1]: 2, best[2]: 2}


async def upload_images_get_urls(page, img_bytes_list):
    """逐张上传图片，返回服务器URL列表"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = ''; ed.dispatchEvent(new Event('input', {bubbles: true})); }
            }
        """)
        await asyncio.sleep(0.3)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.2)

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
            img_url = await page.evaluate("""
                () => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break

        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            print(f"OK")
            image_urls.append(img_url)
        else:
            print(f"FAIL")
            image_urls.append("")
        await asyncio.sleep(0.3)
    return image_urls


async def paste_html_to_editor(page, html_content):
    """通过剪贴板粘贴HTML内容到ProseMirror编辑器"""
    # 先清空编辑器
    await page.evaluate("""
        () => {
            const ed = document.querySelector('.ProseMirror');
            if (ed) {
                ed.innerHTML = '';
                ed.dispatchEvent(new Event('input', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(0.5)
    await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
    await asyncio.sleep(0.3)

    # 通过剪贴板粘贴HTML
    html_escaped = json.dumps(html_content)
    await page.evaluate(f"""
        () => {{
            const ed = document.querySelector('.ProseMirror');
            if (!ed) return;
            ed.focus();
            const html = {html_escaped};
            const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
            const cd = {{
                types: ['text/html', 'text/plain'],
                getData: function(type) {{
                    if (type === 'text/html') return html;
                    return '';
                }},
                setData: function() {{}},
                clearData: function() {{}},
                files: [], items: []
            }};
            Object.defineProperty(ev, 'clipboardData', {{value: cd}});
            ed.dispatchEvent(ev);
        }}
    """)
    await asyncio.sleep(2)

    # 检查内容是否已粘贴
    content = await page.evaluate("""
        () => {
            const ed = document.querySelector('.ProseMirror');
            return ed ? ed.innerHTML.substring(0, 200) : 'no editor';
        }
    """)
    print(f"    编辑器内容预览: {content[:100]}")


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

    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f"  压缩: {len(img_bytes_list)}张")

    print(f"  导航到发布页面...")
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 移除遮罩
    await page.evaluate("""
        () => {
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => m.remove());
            document.querySelectorAll('.byte-drawer-wrapper').forEach(d => d.remove());
        }
    """)
    await asyncio.sleep(1)

    try:
        for btn_text in ["关闭", "不恢复"]:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await asyncio.sleep(1)
    except Exception:
        pass

    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except Exception:
        print("  [ERROR] 编辑器未就绪")
        return False

    # 步骤1: 上传图片获取URL
    image_urls = []
    if img_bytes_list:
        print(f"  上传图片...")
        image_urls = await upload_images_get_urls(page, img_bytes_list)
        valid = len([u for u in image_urls if u])
        print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

    # 步骤2: 构建HTML内容（用服务器URL替换base64）
    valid_urls = [u for u in image_urls if u]
    image_layout = calc_image_layout(len(paragraphs), len(valid_urls))
    print(f"  图片布局: {image_layout}")

    content_parts = []
    img_idx = 0
    track = 0
    for para_idx, para_text in enumerate(paragraphs):
        track += 1
        content_parts.append(f'<p data-track="{track}">{para_text}</p>')
        target_para = para_idx + 1
        if target_para in image_layout:
            for _ in range(image_layout[target_para]):
                if img_idx < len(valid_urls):
                    track += 1
                    content_parts.append(f'<p data-track="{track}"><img src="{valid_urls[img_idx]}" alt=""></p>')
                    img_idx += 1

    content_html = "".join(content_parts)
    word_count = sum(len(p) for p in paragraphs)
    print(f"  内容: {word_count}字, {len(content_html)}字符")

    # 步骤3: 填写标题
    print(f"  填写标题...")
    title_el = page.locator('textarea[placeholder*="文章标题"]').first
    await title_el.click()
    await asyncio.sleep(0.5)
    await title_el.fill(title)
    await asyncio.sleep(2)

    # 步骤4: 粘贴HTML内容到编辑器
    print(f"  粘贴内容到编辑器...")
    await paste_html_to_editor(page, content_html)

    # 步骤5: 等待自动保存
    print(f"  等待自动保存 (30秒)...")
    saved = False
    for i in range(30):
        await asyncio.sleep(1)
        result = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
                const btns = document.querySelectorAll('button, span');
                for (let j = 0; j < btns.length; j++) {
                    if ((btns[j].textContent || '').indexOf('草稿已保存') !== -1) return 'SAVED_BTN';
                }
                return 'idle';
            }
        """)
        if result and 'SAVED' in str(result):
            print(f"  [{i+1}s] 检测到保存提示!")
            saved = True
            break
        if i % 5 == 0:
            # 检查编辑器内容
            content_len = await page.evaluate("""
                () => {
                    const ed = document.querySelector('.ProseMirror');
                    return ed ? ed.innerHTML.length : 0;
                }
            """)
            print(f"  [{i+1}s] 编辑器内容长度: {content_len}")

    if not saved:
        # 尝试手动触发保存
        print(f"  未检测到自动保存，尝试手动触发...")
        editor_el = page.locator('.ProseMirror').first
        await editor_el.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('Enter')
        await asyncio.sleep(3)
        for i in range(10):
            await asyncio.sleep(1)
            result = await page.evaluate("""
                () => {
                    const body = document.body.innerText;
                    return body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1;
                }
            """)
            if result:
                print(f"  手动触发后检测到保存!")
                saved = True
                break

    await page.screenshot(path=f"/workspace/editor_v6_art{index}.png")
    print(f"  截图: /workspace/editor_v6_art{index}.png")

    return saved


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")

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
                ok = await process_article(page, art, i, len(articles))
                if ok:
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
            t = art["title"][:6]
            found = t in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:30]}")

        await page.screenshot(path="/workspace/draft_v6_final.png")
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())