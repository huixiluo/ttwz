#!/usr/bin/env python3
"""v21: 通过UI删除旧草稿 → 打开发布页 → 输入内容 → 保存

核心思路：
1. 打开草稿箱页面，通过UI逐个删除草稿
2. 删除后打开发布页面，此时应该创建新文章
3. article/edit 返回404 → 页面创建新文章
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


async def dismiss_notifications(page):
    await page.evaluate("""
        () => { document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper').forEach(m => { if (m && m.parentNode) m.parentNode.removeChild(m); }); }
    """)
    await asyncio.sleep(0.5)
    for btn_text in ["关闭", "不恢复", "知道了", "确定"]:
        try:
            btn = page.locator("text=" + btn_text).first
            if await btn.is_visible(timeout=1500):
                await btn.click()
                await asyncio.sleep(0.3)
        except: pass


async def paste_image(page, img_bytes):
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
    for _ in range(30):
        await asyncio.sleep(0.5)
        url = await page.evaluate("""
            () => { const imgs = document.querySelectorAll('.ProseMirror img'); return imgs.length ? imgs[imgs.length-1].src : ''; }
        """)
        if url and not url.startswith('blob:') and not url.startswith('data:'): return True
    return False


async def fill_title(page, title):
    return await page.evaluate("""
        (title) => {
            const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                     document.querySelector('textarea[placeholder*="请输入文章标题"]');
            if (!el) return 'not_found';
            el.focus();
            const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            ns.call(el, title);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.blur();
            return el.value;
        }
    """, title)


async def upload_cover(page, cover_paths):
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("    无封面图，跳过")
        return
    print(f"    上传{len(valid)}张封面...")
    await page.evaluate("window.scrollTo(0, 0);")
    await asyncio.sleep(1)
    await page.evaluate("""
        () => {
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const r of radios) {
                if (r.value === '3') { r.click(); r.dispatchEvent(new Event('change', {bubbles: true})); return; }
            }
        }
    """)
    await asyncio.sleep(2)
    for ci, cf in enumerate(valid):
        print(f"      封面{ci+1}: {os.path.basename(cf)}...", end=" ", flush=True)
        uploaded = False
        try:
            add_btn = page.locator('.article-cover-add').first
            if await add_btn.is_visible(timeout=3000):
                await add_btn.click()
                await asyncio.sleep(1)
        except:
            try:
                await page.evaluate("() => { const add = document.querySelector('.article-cover-add'); if (add) add.click(); }")
                await asyncio.sleep(1)
            except: pass
        try:
            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(cf, timeout=5000)
            await asyncio.sleep(2)
            uploaded = True
        except:
            try:
                async with page.expect_file_chooser(timeout=3000) as fc_info:
                    await page.evaluate("() => { const add = document.querySelector('.article-cover-add'); if (add) add.click(); }")
                file_chooser = await fc_info.value
                await file_chooser.set_files(cf)
                await asyncio.sleep(2)
                uploaded = True
            except: pass
        print("OK" if uploaded else "FAIL")


async def wait_for_save(page, timeout=30):
    for i in range(timeout):
        await asyncio.sleep(1)
        saved = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                return body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1;
            }
        """)
        if saved: return True
    return False


async def trigger_save(page):
    try:
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click(timeout=3000)
        await asyncio.sleep(0.3)
        await title_el.press('Space')
        await asyncio.sleep(0.3)
        await title_el.press('Backspace')
        await asyncio.sleep(0.5)
        await title_el.blur()
        return True
    except: return False


async def delete_all_drafts_ui(context):
    """通过UI删除所有草稿"""
    print("  [0] 删除所有旧草稿...")
    page = await context.new_page()
    await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
    await asyncio.sleep(5)

    # 查找所有删除按钮
    for round_num in range(20):  # 最多20轮
        # 查找并点击"更多"或"..."按钮
        delete_btns = await page.evaluate("""
            () => {
                const btns = [];
                // 查找所有可能是删除按钮的元素
                const allEls = document.querySelectorAll('button, span, a, div[role="button"]');
                for (const el of allEls) {
                    const text = (el.textContent || '').trim();
                    if (text === '删除' || text.includes('删除')) {
                        btns.push({text: text, visible: el.offsetParent !== null});
                    }
                }
                // 也查找"更多"按钮
                const moreBtns = [];
                for (const el of allEls) {
                    const text = (el.textContent || '').trim();
                    if (text === '...' || text === '更多' || text === '⋮' || text === '︙') {
                        moreBtns.push({text: text, visible: el.offsetParent !== null});
                    }
                }
                return {deleteBtns: btns.length, moreBtns: moreBtns.length};
            }
        """)
        print(f"    轮{round_num+1}: 找到{delete_btns.get('deleteBtns', 0)}个删除按钮, {delete_btns.get('moreBtns', 0)}个更多按钮")

        if delete_btns.get('deleteBtns', 0) == 0:
            print("    没有更多可删除的草稿")
            break

        # 点击第一个删除按钮
        clicked = await page.evaluate("""
            () => {
                const allEls = document.querySelectorAll('button, span, a, div[role="button"]');
                for (const el of allEls) {
                    const text = (el.textContent || '').trim();
                    if (text === '删除' || text.includes('删除')) {
                        if (el.offsetParent !== null) {
                            el.click();
                            return 'clicked_delete';
                        }
                    }
                }
                // 没找到删除按钮，尝试点击"更多"按钮
                for (const el of allEls) {
                    const text = (el.textContent || '').trim();
                    if (text === '...' || text === '更多' || text === '⋮' || text === '︙') {
                        if (el.offsetParent !== null) {
                            el.click();
                            return 'clicked_more';
                        }
                    }
                }
                return 'nothing';
            }
        """)
        print(f"    点击: {clicked}")
        await asyncio.sleep(2)

        # 如果有确认对话框，点击确认
        try:
            confirm_btn = page.locator("text=确定").first
            if await confirm_btn.is_visible(timeout=2000):
                await confirm_btn.click()
                print("    确认删除")
                await asyncio.sleep(2)
        except: pass

        try:
            confirm_btn = page.locator("text=确认").first
            if await confirm_btn.is_visible(timeout=2000):
                await confirm_btn.click()
                print("    确认删除")
                await asyncio.sleep(2)
        except: pass

    await page.close()
    return True


async def process_article(context, art, index, total):
    title = art["title"]
    html_path = art["html_file"]
    cover_files = art.get("cover_files", [])

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] 文件不存在: {html_path}")
        return False

    paragraphs, images = extract_html_text_and_images(html_path)
    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  内容: {len(paragraphs)}段, {len(img_bytes_list)}张图 | 布局: {image_layout}")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    new_pgc_id = [None]
    save_responses = []

    async def capture_response(response):
        url = response.url
        if any(kw in url for kw in ['save', 'draft', 'auto_save', 'article/new', 'article/edit', 'article/publish']):
            try:
                body = await response.text()
                short = body[:800]
                save_responses.append(f"{response.status} {response.request.method} {url[:150]}\n  {short}")
                if 'article/new' in url:
                    try:
                        data = json.loads(body)
                        pid = data.get('data', {}).get('pgc_id')
                        if pid and pid != '0':
                            new_pgc_id[0] = pid
                            print(f"  [NEW] pgc_id={pid}")
                    except: pass
                if response.request.method == 'POST' and 'article/publish' in url:
                    try:
                        req_body = response.request.post_data
                        if req_body:
                            save_responses.append(f"  REQ_BODY: {req_body[:2000]}")
                    except: pass
            except: pass

    # 拦截 article/edit 请求 - 返回404强制创建新文章
    async def block_edit_route(route):
        if 'article/edit' in route.request.url:
            print(f"  [BLOCK] 拦截 article/edit，返回404强制新文章")
            await route.fulfill(status=404, body='{"code":-1,"err_no":-1,"message":"not found"}')
        else:
            await route.continue_()

    page = await context.new_page()
    page.on('response', capture_response)
    await page.route("**/article/edit**", block_edit_route)

    try:
        ts = int(time.time() * 1000)
        print(f"  [1] 打开发布页面...")
        await page.goto(f"{PUBLISH_URL}?_t={ts}", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_notifications(page)

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

        for i in range(10):
            if new_pgc_id[0]: break
            await asyncio.sleep(1)
        if new_pgc_id[0]:
            print(f"  [OK] 新pgc_id={new_pgc_id[0]}")
        else:
            print(f"  [INFO] 未获取到pgc_id（可能由article/new POST提供）")

        init_content = await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); return ed ? ed.innerText.substring(0, 200) : 'no_editor'; }
        """)
        print(f"  编辑器初始: {init_content[:100]}")

        # 按布局输入文字和图片
        print(f"  [2] 输入内容...")
        img_idx = 0
        for para_idx, para_text in enumerate(paragraphs):
            para_num = para_idx + 1
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
            await asyncio.sleep(0.1)
            await page.keyboard.type(para_text, delay=0)
            await asyncio.sleep(0.1)
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.15)

            if para_num in image_layout:
                num_imgs = image_layout[para_num]
                for _ in range(num_imgs):
                    if img_idx < len(img_bytes_list):
                        print(f"    图{img_idx+1}@段{para_num}: ", end="", flush=True)
                        ok = await paste_image(page, img_bytes_list[img_idx])
                        print("OK" if ok else "FAIL")
                        if ok:
                            await page.keyboard.press('Enter')
                            await asyncio.sleep(0.3)
                        img_idx += 1
            if para_num % 3 == 0:
                print(f"    已输入 {para_num}/{len(paragraphs)} 段")

        print(f"  内容输入完成: {len(paragraphs)}段, {img_idx}张图")

        dom_imgs = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length")
        dom_chars = await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); return ed ? ed.innerText.length : 0; }")
        print(f"  DOM: {dom_chars}字, {dom_imgs}张图")

        print(f"  [3] 填写标题...")
        title_result = await fill_title(page, title)
        print(f"  标题: {title_result}")
        await asyncio.sleep(3)

        print(f"  [4] 触发保存...")
        await trigger_save(page)
        saved = await wait_for_save(page, timeout=30)
        if saved:
            print(f"  [OK] 检测到保存成功")
        else:
            print(f"  [WARN] 未检测到保存信号")

        print(f"  [5] 上传封面...")
        await upload_cover(page, cover_files)
        await trigger_save(page)
        await wait_for_save(page, timeout=15)

        await page.screenshot(path=f"/workspace/v21_art{index}.png")

        if save_responses:
            print(f"  [NET] 关键请求:")
            for r in save_responses:
                for line in r.split('\n'):
                    if line.strip():
                        print(f"    {line.strip()[:200]}")

        await page.close()
        return True

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        try:
            await page.screenshot(path=f"/workspace/v21_art{index}_err.png")
        except: pass
        try:
            await page.close()
        except: pass
        return False


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章\n")
    for i, art in enumerate(articles, 1):
        html_path = art["html_file"]
        if os.path.exists(html_path):
            paragraphs, images = extract_html_text_and_images(html_path)
            layout = calc_image_layout(len(paragraphs), len(images))
            print(f"  [{i}] {art['title'][:35]}... | {len(paragraphs)}段 {len(images)}图 | 布局={layout}")

    print(f"\n启动浏览器...")
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

        print("验证登录...")
        test_page = await context.new_page()
        await test_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        if "登录" in (await test_page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")
        await test_page.close()

        # 先通过UI删除旧草稿
        await delete_all_drafts_ui(context)

        success = 0
        for i, art in enumerate(articles, 1):
            try:
                art_context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=UA
                )
                await art_context.add_cookies([
                    {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
                    for k, v in cookies.items()
                ])
                if await process_article(art_context, art, i, len(articles)):
                    success += 1
                await art_context.close()
            except Exception as e:
                import traceback
                print(f"  [FATAL] {e}")
                traceback.print_exc()
            await asyncio.sleep(3)

        print(f"\n{'='*60}")
        print("验证草稿箱...")
        verify_context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=UA
        )
        await verify_context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])
        verify_page = await verify_context.new_page()
        await verify_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await verify_page.evaluate("() => document.body.innerText.substring(0, 8000)")

        for art in articles:
            keyword = art["title"][:8]
            found = keyword in draft_text
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:45]}")

        print(f"\n草稿箱内容:")
        for line in draft_text.split('\n')[:30]:
            line = line.strip()
            if line and len(line) > 5:
                print(f"    {line[:120]}")

        await verify_page.screenshot(path="/workspace/v21_draft_final.png")
        await verify_page.close()
        await verify_context.close()
        await browser.close()

    print(f"\n上传完成: {success}/{len(articles)} 篇成功")


if __name__ == "__main__":
    asyncio.run(main())