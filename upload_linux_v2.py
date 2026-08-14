#!/usr/bin/env python3
"""Linux版头条草稿箱上传 v2 - 键盘输入+图片粘贴+预览按钮触发保存"""
import os, re, json, time, base64, asyncio
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def extract_html_content(html_path):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    paragraphs = []
    images = []
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    body = body_match.group(1) if body_match else html
    for m in re.finditer(r'<p>([^<]+)</p>', body):
        text = m.group(1).strip()
        if text:
            paragraphs.append(text)
    for m in re.finditer(r'<img[^>]*src="(data:image/[^"]*)"', body):
        images.append(m.group(1))
    return paragraphs, images


def calc_image_layout(total_paragraphs, num_images=5):
    if total_paragraphs < 1:
        return {}
    n_groups = (num_images - 1) // 2
    if n_groups <= 0:
        return {1: 1} if num_images >= 1 else {}

    def _build_positions(last):
        if last < 3:
            return [1]
        pos_list = [1]
        if n_groups == 1:
            pos_list.append(last)
        else:
            step = (last - 1) / n_groups
            for k in range(1, n_groups + 1):
                raw = 1 + step * k if k < n_groups else last
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


async def upload_images_get_urls(page, images):
    """逐张上传图片获取服务器URL"""
    image_urls = []
    for img_idx, data_url in enumerate(images):
        print(f"    图片{img_idx+1}: 上传中...")
        try:
            header, b64 = data_url.split(',', 1)
            img_bytes = base64.b64decode(b64)
        except Exception as e:
            print(f"      解析失败: {e}")
            image_urls.append("")
            continue

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
        await asyncio.sleep(0.3)
        await page.evaluate("() => { const e = document.querySelector('.ProseMirror'); if(e) e.focus(); }")
        await asyncio.sleep(0.2)

        # 粘贴Blob上传
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
                const fd = {{
                    files: [file], items: [], types: ['Files'],
                    getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}
                }};
                Object.defineProperty(ev, 'clipboardData', {{value: fd}});
                editor.dispatchEvent(ev);
            }}
        """)

        # 等待服务器URL
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

        if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
            print(f"      OK: {img_url[:70]}...")
            image_urls.append(img_url)
        else:
            print(f"      FAIL")
            image_urls.append("")
        await asyncio.sleep(0.5)
    return image_urls


async def wait_for_auto_save(page, timeout=30):
    """等待自动保存完成"""
    for i in range(timeout):
        await asyncio.sleep(1)
        result = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return 'SAVED';
                const btns = document.querySelectorAll('button, span');
                for (let j = 0; j < btns.length; j++) {
                    const t = (btns[j].textContent || '').trim();
                    if (t.indexOf('草稿已保存') !== -1) return 'SAVED_BTN';
                }
                return 'idle';
            }
        """)
        if result and 'SAVED' in str(result):
            return True
    return False


async def process_article(page, art, index, total):
    title = art["title"]
    html_path = art["html_file"]

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {title}")
    print(f"{'='*60}")

    if not os.path.exists(html_path):
        print(f"  [ERROR] HTML文件不存在: {html_path}")
        return False

    paragraphs, images = extract_html_content(html_path)
    print(f"  段落: {len(paragraphs)}段, 图片: {len(images)}张")

    if not paragraphs:
        print("  [ERROR] 无文字内容")
        return False

    # 导航到发布页面
    await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # 关闭弹窗
    try:
        for btn_text in ["关闭", "不恢复"]:
            btns = page.locator(f"text={btn_text}")
            count = await btns.count()
            if count > 0:
                await btns.first.click()
                await asyncio.sleep(1)
    except:
        pass

    # 等待编辑器
    try:
        await page.wait_for_selector(".ProseMirror", timeout=15000)
    except:
        print("  [ERROR] 编辑器未就绪")
        return False
    print("  [OK] 编辑器就绪")

    # 步骤1: 上传图片获取URL
    image_urls = []
    if images:
        print("  [1] 上传图片...")
        image_urls = await upload_images_get_urls(page, images)
        valid = len([u for u in image_urls if u])
        print(f"  图片上传: {valid}/{len(images)}张成功")

    valid_urls = [u for u in image_urls if u]
    image_layout = calc_image_layout(len(paragraphs), len(images))
    print(f"  图片布局: {image_layout}")

    # 步骤2: 清空编辑器并逐段输入内容
    print("  [2] 逐段输入内容...")
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
                    print(f"      插入图片{img_idx+1}/{len(valid_urls)}...")
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
                                files: [], items: []
                            }};
                            Object.defineProperty(ev, 'clipboardData', {{value: cd}});
                            editor.dispatchEvent(ev);
                        }}
                    """)
                    await asyncio.sleep(0.5)
                    await page.keyboard.press('Enter')
                    await asyncio.sleep(0.3)
                    img_idx += 1

    print(f"  内容输入完成: {len(paragraphs)}段文字, {img_idx}张图片")

    # 步骤3: 填写标题
    print("  [3] 填写标题...")
    title_json = json.dumps(title)
    await page.evaluate(f"""
        () => {{
            const el = document.querySelector('textarea[placeholder*="文章标题"]') ||
                      document.querySelector('textarea[placeholder*="请输入文章标题"]');
            if (!el) return 'not_found';
            el.focus();
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            nativeSetter.call(el, {title_json});
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.blur();
            return el.value;
        }}
    """)
    await asyncio.sleep(3)
    print(f"  标题: {title}")

    # 步骤4: 触发编辑器事件
    await page.evaluate("""
        () => {
            const editor = document.querySelector('.ProseMirror');
            if (editor) {
                editor.dispatchEvent(new Event('input', {bubbles: true}));
                editor.dispatchEvent(new Event('change', {bubbles: true}));
                editor.dispatchEvent(new Event('blur', {bubbles: true}));
            }
        }
    """)
    await asyncio.sleep(3)

    # 等待自动保存
    print("  [4] 等待自动保存...")
    saved = await wait_for_auto_save(page, timeout=15)
    if saved:
        print("  [OK] 自动保存完成")
    else:
        print("  [WARN] 自动保存未确认，尝试手动触发...")
        # 手动触发：点击标题再点击正文
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('Space')
        await asyncio.sleep(0.5)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)
        await editor_el.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('ArrowRight')
        await asyncio.sleep(3)

        saved = await wait_for_auto_save(page, timeout=15)
        if saved:
            print("  [OK] 手动触发保存成功")
        else:
            print("  [WARN] 保存仍未确认")

    # 截图
    await page.screenshot(path=f"/workspace/editor_v2_art{index}.png")
    print(f"  截图: /workspace/editor_v2_art{index}.png")

    # 步骤5: 点击"预览"按钮（触发保存）
    print("  [5] 点击预览按钮...")
    try:
        preview_btn = page.locator("button:has-text('预览'):not(:has-text('发布'))").first
        if await preview_btn.is_visible(timeout=5000):
            await preview_btn.click()
            print(f"    已点击预览")
            await asyncio.sleep(5)

            current_url = page.url
            print(f"    当前URL: {current_url[:120]}")

            if "preview" in current_url.lower():
                print(f"    在预览页，返回发布页...")
                await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)
        else:
            print(f"    预览按钮不可见")
    except Exception as e:
        print(f"    [ERROR] {e}")

    # 步骤6: 验证草稿箱
    print("  [6] 验证草稿箱...")
    await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
    await asyncio.sleep(5)

    draft_text = await page.evaluate("() => document.body.innerText")
    title_short = title[:6]
    if title_short in draft_text:
        idx = draft_text.find(title_short)
        print(f"  [SUCCESS] 文章在草稿箱中!")
        print(f"    {draft_text[idx:idx+80]}")
        return True
    else:
        print(f"  [FAIL] 未在草稿箱中找到文章")
        print(f"  草稿箱前500字: {draft_text[:500]}")
        return False


async def main():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    print(f"共 {len(articles)} 篇文章待上传")
    print(f"Chrome: {CHROME_PATH}")

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
        cookie_list = [
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        print("验证登录...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
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
            await asyncio.sleep(3)

        # 最终验证
        print(f"\n{'='*60}")
        print(f"最终验证草稿箱...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_content = await page.evaluate("() => document.body.innerText.substring(0, 3000)")
        for art in articles:
            t = art["title"][:6]
            found = t in draft_content
            print(f"  {'[OK]' if found else '[MISS]'} {art['title'][:30]}")

        await page.screenshot(path="/workspace/draft_box_final_v2.png")
        await browser.close()

    print(f"\n{'='*60}")
    print(f"上传完成: {success}/{len(articles)} 篇")


if __name__ == "__main__":
    asyncio.run(main())