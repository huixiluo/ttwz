#!/usr/bin/env python3
"""头条草稿箱上传 v12 - 键盘逐段输入 + 图片粘贴 + 正确图片布局

核心策略：
1. 逐张上传图片到服务器获取URL
2. 键盘逐段输入文字（ProseMirror自动同步状态）
3. 在正确位置粘贴图片（按calc_image_layout布局）
4. 填写标题后点击预览触发保存
5. 验证草稿箱
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
    """动态计算图片布局（5张图上限）——均匀分布，避免中间大片文字空档。"""
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
                if k == n_groups: raw = last
                else: raw = first + step * k
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
    """从HTML文件中提取段落文字和图片base64"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs, images = [], []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body = body_match.group(1) if body_match else html
    for m in re.finditer(r'<p>([^<]+)</p>', body):
        text = m.group(1).strip()
        if text:
            paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', body):
        images.append(m.group(1))
    return paragraphs, images


def compress_image_to_bytes(data_url, max_width=800):
    """压缩图片并返回JPEG bytes"""
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


async def remove_overlays(page):
    """移除所有遮罩层"""
    await page.evaluate("""
        () => {
            document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper, [class*="drawer-mask"], [class*="modal-mask"]').forEach(m => {
                if (m && m.parentNode) m.parentNode.removeChild(m);
            });
        }
    """)
    await asyncio.sleep(0.3)


async def dismiss_notifications(page):
    """关闭各种通知弹窗"""
    await remove_overlays(page)
    for btn_text in ["关闭", "不恢复", "知道了", "确定", "取消"]:
        try:
            btn = page.locator(f"text={btn_text}").first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                await asyncio.sleep(0.3)
        except: pass


async def upload_images_get_urls(page, img_bytes_list):
    """逐张上传图片到服务器，返回服务器URL列表"""
    image_urls = []
    for img_idx, img_bytes in enumerate(img_bytes_list):
        print(f"    图{img_idx+1}/{len(img_bytes_list)}: ", end="", flush=True)
        await remove_overlays(page)

        # 清空编辑器
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = '<p></p>'; ed.focus(); } }
        """)
        await asyncio.sleep(0.3)

        # 通过paste事件上传
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

        # 等待图片URL变为服务器URL
        img_url = ""
        for _ in range(60):
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
    """通过paste事件粘贴图片URL（ProseMirror会处理成image节点）"""
    await page.evaluate(f"""
        () => {{
            const ed = document.querySelector('.ProseMirror');
            if (!ed) return;
            ed.focus();
            const ev = new ClipboardEvent('paste', {{bubbles: true, cancelable: true}});
            const cd = {{
                types: ['text/html'],
                getData: function(type) {{ return type === 'text/html' ? '<img src="{img_url}" alt="图片来源于网络" />' : ''; }},
                setData: function() {{}}, clearData: function() {{}}, files: [], items: []
            }};
            Object.defineProperty(ev, 'clipboardData', {{value: cd}});
            ed.dispatchEvent(ev);
        }}
    """)


async def fill_title(page, title):
    """填写标题"""
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


async def wait_for_save_indicator(page, timeout=20):
    """等待保存成功提示"""
    for i in range(timeout):
        await asyncio.sleep(1)
        saved = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return true;
                return false;
            }
        """)
        if saved: return True
    return False


async def upload_cover(page, cover_paths):
    """上传封面图片"""
    valid = [cf for cf in cover_paths[:3] if os.path.exists(cf)]
    if not valid:
        print("    无有效封面图，跳过")
        return

    print(f"    上传{len(valid)}张封面...")
    await page.evaluate("window.scrollTo(0, 0);")
    await asyncio.sleep(1)

    # 选择3图模式
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
        await page.evaluate("""
            () => {
                const add = document.querySelector('.article-cover-add');
                if (add) { add.scrollIntoView({block: 'center'}); add.click(); }
            }
        """)
        await asyncio.sleep(1.5)

        uploaded = False
        try:
            file_input = page.locator('input[type="file"][accept*="image"]').first
            await file_input.set_input_files(cf, timeout=5000)
            await asyncio.sleep(2)
            uploaded = True
        except:
            try:
                all_inputs = page.locator('input[type="file"]')
                count = await all_inputs.count()
                for i in range(count):
                    inp = all_inputs.nth(i)
                    if await inp.is_visible():
                        await inp.set_input_files(cf, timeout=3000)
                        await asyncio.sleep(2)
                        uploaded = True
                        break
            except: pass
        print("OK" if uploaded else "FAIL")


async def process_article(context, art, index, total):
    """处理单篇文章上传"""
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
    print(f"  内容: {len(paragraphs)}段文字, {len(images)}张图片")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    # 压缩图片
    img_bytes_list = [c for img in images if (c := compress_image_to_bytes(img))]
    print(f"  压缩: {len(img_bytes_list)}/{len(images)}张有效")

    # 计算图片布局
    image_layout = calc_image_layout(len(paragraphs), len(img_bytes_list))
    print(f"  布局: {image_layout}")
    # 打印布局详情
    total_imgs_in_layout = sum(image_layout.values())
    print(f"  布局图片数: {total_imgs_in_layout}, 实际图片数: {len(img_bytes_list)}")

    page = await context.new_page()

    try:
        # [1] 导航到发布页面
        print(f"  [1/5] 打开发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dismiss_notifications(page)

        # 等待编辑器就绪
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

        # [2] 上传图片到服务器获取URL
        image_urls = []
        if img_bytes_list:
            print(f"  [2/5] 上传{len(img_bytes_list)}张图片...")
            image_urls = await upload_images_get_urls(page, img_bytes_list)
            valid_count = len([u for u in image_urls if u])
            print(f"  上传完成: {valid_count}/{len(img_bytes_list)}张成功")
        else:
            print(f"  [2/5] 无图片，跳过")

        valid_urls = [u for u in image_urls if u]

        # [3] 键盘逐段输入文字 + 在正确位置粘贴图片
        print(f"  [3/5] 输入内容 ({len(paragraphs)}段, {len(valid_urls)}张图)...")
        await remove_overlays(page)

        # 清空编辑器
        await page.evaluate("""
            () => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = ''; ed.focus(); } }
        """)
        await asyncio.sleep(0.3)

        img_idx = 0
        for pi, para_text in enumerate(paragraphs):
            # 输入文字段落
            await remove_overlays(page)
            await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
            await asyncio.sleep(0.1)
            await page.keyboard.type(para_text, delay=0)
            await asyncio.sleep(0.1)
            await page.keyboard.press('Enter')
            await asyncio.sleep(0.1)

            # 检查是否需要在此段落后插入图片
            target_para = pi + 1
            if target_para in image_layout:
                num_imgs = image_layout[target_para]
                for _ in range(num_imgs):
                    if img_idx < len(valid_urls):
                        await paste_image_url(page, valid_urls[img_idx])
                        await asyncio.sleep(0.5)
                        await page.keyboard.press('Enter')
                        await asyncio.sleep(0.1)
                        img_idx += 1

            if (pi + 1) % 3 == 0:
                print(f"    已输入 {pi+1}/{len(paragraphs)} 段...")

        print(f"  输入完成 ({len(paragraphs)}段, {img_idx}张图)")

        # 验证DOM中的图片数量
        dom_imgs = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length")
        print(f"  DOM图片数: {dom_imgs}")

        # [4] 填写标题
        print(f"  [4/5] 填写标题...")
        await fill_title(page, title)
        await asyncio.sleep(3)

        # 点击预览触发保存
        print(f"  [5/5] 点击预览触发保存...")
        await remove_overlays(page)

        try:
            preview_btn = page.locator("text=预览").first
            await preview_btn.click(timeout=5000)
            print(f"  已点击预览按钮")
        except:
            await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if ((b.textContent || '').indexOf('预览') !== -1) { b.click(); return; }
                    }
                }
            """)
            print(f"  已通过JS点击预览")

        await asyncio.sleep(5)

        # 关闭预览窗口
        pages = context.pages
        print(f"  当前页面数: {len(pages)}")
        if len(pages) > 1:
            for p in pages:
                if p != page:
                    await p.close()
                    print(f"  已关闭预览页面")
                    await asyncio.sleep(1)

        # 等待保存
        if await wait_for_save_indicator(page, timeout=10):
            print(f"  [OK] 保存成功")

        # 上传封面
        await upload_cover(page, cover_files)

        # 等待封面保存
        await asyncio.sleep(3)
        if await wait_for_save_indicator(page, timeout=10):
            print(f"  [OK] 封面保存成功")

        await page.screenshot(path=f"/workspace/v12_art{index}.png")
        return True

    except Exception as e:
        import traceback
        print(f"  [ERROR] {e}")
        traceback.print_exc()
        try:
            await page.screenshot(path=f"/workspace/v12_art{index}_err.png")
        except: pass
        return False
    finally:
        await page.close()


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传\n")
    for i, art in enumerate(articles, 1):
        html_path = art["html_file"]
        if os.path.exists(html_path):
            paragraphs, images = extract_html_text_and_images(html_path)
            layout = calc_image_layout(len(paragraphs), len(images))
            print(f"  [{i}] {art['title'][:35]}... | {len(paragraphs)}段 {len(images)}图 | 布局={layout}")
        else:
            print(f"  [{i}] {art['title'][:35]}... | 文件不存在: {html_path}")

    print(f"\n启动浏览器...")
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

        # 验证登录
        print("验证登录状态...")
        test_page = await context.new_page()
        await test_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        if "登录" in (await test_page.title()):
            print("[ERROR] Cookie已过期，请更新 toutiao_cookies.json")
            await browser.close()
            return
        print("[OK] 登录有效\n")
        await test_page.close()

        # 处理每篇文章
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

        # 验证草稿箱
        print(f"\n{'='*60}")
        print("验证草稿箱...")
        verify_page = await context.new_page()
        await verify_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await verify_page.evaluate("() => document.body.innerText.substring(0, 5000)")

        for art in articles:
            keyword = art["title"][:8]
            found = keyword in draft_text
            status = "[OK]" if found else "[MISS]"
            print(f"  {status} {art['title'][:45]}")

        await verify_page.screenshot(path="/workspace/draft_v12_final.png")
        await verify_page.close()
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇成功")
    print(f"请打开 https://mp.toutiao.com/profile_v4/manage/draft 检查草稿箱")


if __name__ == "__main__":
    asyncio.run(main())