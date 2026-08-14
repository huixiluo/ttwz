#!/usr/bin/env python3
"""头条草稿箱上传 v10 - 键盘输入 + 正确布局 + 延长等待

核心思路：
- v7 的第一篇文章成功上传了（虽然检测显示"未检测到保存"）
- 说明键盘输入方式确实能触发保存，只是检测不到"草稿已保存"提示
- v10: 使用正确的 calc_image_layout + 键盘输入 + 更长的等待时间
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


# ====== 来自 upload_visible.py 的正确 calc_image_layout ======
def calc_image_layout(total_paragraphs, num_images=5):
    if total_paragraphs < 1:
        return {}
    n_groups = (num_images - 1) // 2
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}
    first = 1

    def _build_positions(last):
        if last < 3:
            return [first]
        pos_list = [first]
        if n_groups == 1:
            pos_list.append(last)
        else:
            step = (last - first) / n_groups
            for k in range(1, n_groups + 1):
                if k == n_groups:
                    raw = last
                else:
                    raw = first + step * k
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
        if len(pos_list) < 2:
            return 0
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
    if not candidates:
        return {1: 1}

    def _score(c):
        gap, tail, pos = c
        return (0 if gap <= 3 else 1, 0 if tail <= 2 else 1, gap, tail)
    candidates.sort(key=_score)
    best_positions = candidates[0][2]
    layout = {}
    for i, p in enumerate(best_positions):
        layout[p] = 1 if i == 0 else 2
    return dict(sorted(layout.items()))


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


async def remove_all_overlays(page):
    await page.evaluate("""
        () => {
            const style = document.createElement('style');
            style.textContent = `
                .byte-drawer-mask, .byte-modal-mask, .byte-overlay,
                .byte-drawer-wrapper, .byte-modal-wrapper,
                [class*="drawer-mask"], [class*="modal-mask"] { display: none !important; pointer-events: none !important; }
            `;
            document.head.appendChild(style);
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper').forEach(m => {
                if (m && m.parentNode) m.parentNode.removeChild(m);
            });
        }
    """)
    await asyncio.sleep(0.3)


async def upload_images_get_urls(page, img_bytes_list):
    """逐张上传图片获取URL"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图片{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await remove_all_overlays(page)
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = ''; ed.focus(); } }
        """)
        await asyncio.sleep(0.3)

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
        for _ in range(45):
            await asyncio.sleep(0.5)
            img_url = await page.evaluate("""
                () => { const img = document.querySelector('.ProseMirror img'); return img ? img.src : ''; }
            """)
            if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                break

        ok = img_url and not img_url.startswith('blob:') and not img_url.startswith('data:')
        print("OK" if ok else "FAIL")
        image_urls.append(img_url if ok else "")
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


async def process_article(context, art, index, total):
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
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  图片布局: {image_layout}")

    page = await context.new_page()

    try:
        print(f"  导航到发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        await remove_all_overlays(page)
        try:
            for btn_text in ["关闭", "不恢复", "知道了", "确定"]:
                btn = page.locator(f"text={btn_text}").first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(0.5)
        except: pass
        await remove_all_overlays(page)

        for i in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); return ed && ed.getBoundingClientRect().width > 0; }
            """)
            if ready: break
        else:
            print("  [ERROR] 编辑器未就绪")
            return False
        print("  [OK] 编辑器就绪")

        # [1] 上传图片获取URL
        image_urls = []
        if img_bytes_list:
            print(f"  [1/3] 上传图片 ({len(img_bytes_list)}张)...")
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            valid = len([u for u in image_urls if u])
            print(f"  上传完成: {valid}/{len(img_bytes_list)}张成功")

        valid_urls = [u for u in image_urls if u]

        # [2] 键盘输入内容
        print(f"  [2/3] 输入内容 ({len(paragraphs)}段, {len(valid_urls)}张图)...")
        await remove_all_overlays(page)
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = ''; ed.focus(); } }
        """)
        await asyncio.sleep(0.3)

        img_idx = 0
        t0 = time.time()
        for pi, para_text in enumerate(paragraphs):
            await remove_all_overlays(page)
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
            await asyncio.sleep(0.1)
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

        # [3] 填写标题 - 使用原生setter确保React状态更新
        print(f"  [3/3] 填写标题...")
        await remove_all_overlays(page)
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, {json.dumps(title)});
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
            }}
        """)
        print(f"  标题已设置")
        await asyncio.sleep(3)

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

        # 在末尾做一个小编辑触发自动保存
        await remove_all_overlays(page)
        await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.focus(); ed.click(); } }")
        await asyncio.sleep(0.5)
        await page.keyboard.press('End')
        await asyncio.sleep(0.2)
        await page.keyboard.press('Space')
        await asyncio.sleep(0.2)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(3)

        # 等待自动保存 - 延长等待时间，因为v7的经验是检测不到但实际保存了
        print(f"  等待自动保存 (90秒 - 即使未检测到也可能已保存)...")
        saved = False
        for i in range(90):
            await asyncio.sleep(1)
            result = await page.evaluate("""
                () => { return document.body.innerText.indexOf('草稿已保存') !== -1 || document.body.innerText.indexOf('保存成功') !== -1; }
            """)
            if result:
                print(f"  [{i+1}s] 检测到保存!")
                saved = True
                break

        if not saved:
            print(f"  未检测到保存提示，但内容可能已通过自动保存（参考v7经验）")
            # 再做一次编辑触发
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.focus(); } }")
            await asyncio.sleep(0.3)
            await page.keyboard.press('Space')
            await asyncio.sleep(0.3)
            await page.keyboard.press('Backspace')
            await asyncio.sleep(10)
            saved = True  # 假设已保存，v7的经验

        await page.screenshot(path=f"/workspace/v10_art{index}.png")
        return True

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        await page.screenshot(path=f"/workspace/v10_art{index}_err.png")
        return False
    finally:
        await page.close()


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")
    for i, art in enumerate(articles, 1):
        html_path = art["html_file"]
        if os.path.exists(html_path):
            paragraphs, images = extract_html_text_and_images(html_path)
            layout = calc_image_layout(len(paragraphs), len(images))
            print(f"  [{i}] {art['title'][:30]}... {len(paragraphs)}段 {len(images)}图 布局={layout}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, user_agent=UA
        )
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])

        print("\n验证登录...")
        page = await context.new_page()
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        if "登录" in (await page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")
        await page.close()

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                if await process_article(context, art, i, len(articles)):
                    success += 1
            except Exception as e:
                import traceback
                print(f"  [FATAL] {e}")
                traceback.print_exc()
            await asyncio.sleep(2)

        print(f"\n{'='*60}")
        print(f"验证草稿箱...")
        page = await context.new_page()
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
        for art in articles:
            keyword = art["title"][:8]
            found = keyword in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:40]}")

        await page.screenshot(path="/workspace/draft_v10_final.png")
        await page.close()
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())