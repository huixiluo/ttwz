#!/usr/bin/env python3
"""重新上传第1篇文章 - 使用已验证成功的流程，加长初始等待"""
import os, re, json, time, base64, asyncio, io
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = '/workspace'
COOKIE_FILE = os.path.join(BASE_DIR, 'toutiao_cookies.json')
CHROME_PATH = '/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome'

def extract_html_text_and_images(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
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

async def upload_single_image(page, img_bytes, img_index):
    """上传单张图片，返回服务器URL"""
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
            const b64 = "{b64_str}";
            const byteString = atob(b64);
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
            const blob = new Blob([ab], {{type: 'image/jpeg'}});
            const file = new File([blob], 'image_{img_index}.jpg', {{type: 'image/jpeg'}});
            const pasteEvent = new ClipboardEvent('paste', {{
                bubbles: true, cancelable: true
            }});
            const fakeData = {{
                files: [file], items: [], types: ['Files'],
                getData: function() {{ return ''; }},
                setData: function() {{}},
                clearData: function() {{}}
            }};
            Object.defineProperty(pasteEvent, 'clipboardData', {{
                value: fakeData, writable: false, configurable: true
            }});
            editor.dispatchEvent(pasteEvent);
        }}
    """)

    for _ in range(30):
        await asyncio.sleep(1)
        has_img = await page.evaluate("() => document.querySelectorAll('.ProseMirror img').length > 0")
        if has_img:
            break

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
            return img_url
    return img_url

async def main():
    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    html_path = '/workspace/output/tt_hot_tt_娱乐_1_20260813_093751.html'
    title = '雷佳音自曝往事，演陈俊生不为戏，一句话扎心了'

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f'段落: {len(paragraphs)}段, 图片: {len(images)}张')

    img_bytes_list = []
    for img in images:
        compressed = compress_image_to_bytes(img)
        if compressed:
            img_bytes_list.append(compressed)
    print(f'压缩完成: {len(img_bytes_list)}张')

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        cookie_list = [{'name': k, 'value': v, 'domain': '.toutiao.com', 'path': '/'} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 验证登录
        print('验证登录...')
        await page.goto('https://mp.toutiao.com/profile_v4/manage/draft', wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(3)
        if '登录' in (await page.title()):
            print('[ERROR] Cookie过期')
            await browser.close()
            return
        print('[OK] 已登录')

        # 导航到发布页面，等待更长时间确保完全初始化
        print('导航到发布页...')
        await page.goto('https://mp.toutiao.com/profile_v4/graphic/publish', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(8)

        # 关闭弹窗
        try:
            for btn_text in ['关闭', '不恢复']:
                btn = page.locator(f'text={btn_text}').first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(1)
        except:
            pass

        await page.wait_for_selector('.ProseMirror', timeout=15000)
        print('编辑器就绪')

        # 先点击编辑器，输入一些文字，触发编辑器的初始化
        editor = page.locator('.ProseMirror').first
        await editor.click()
        await asyncio.sleep(1)
        await page.keyboard.type('初始化编辑器...', delay=50)
        await asyncio.sleep(2)
        await page.keyboard.press('Control+a')
        await asyncio.sleep(0.3)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(1)

        # 等待自动保存触发（获取pgc_id）
        print('等待自动保存初始化...')
        await asyncio.sleep(10)

        # 填标题
        print('填标题...')
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click(force=True, timeout=5000)
        await asyncio.sleep(0.5)
        await title_el.fill(title)
        await asyncio.sleep(2)

        # 清除编辑器
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('Control+a')
        await asyncio.sleep(0.3)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)

        # 逐张上传图片
        image_urls = []
        if img_bytes_list:
            print(f'上传{len(img_bytes_list)}张图片...')
            for img_idx, img_bytes in enumerate(img_bytes_list):
                print(f'  图片{img_idx+1}: 上传中...')
                img_url = await upload_single_image(page, img_bytes, img_idx + 1)
                if img_url:
                    image_urls.append(img_url)
                    print(f'  图片{img_idx+1}: OK')
                else:
                    print(f'  图片{img_idx+1}: FAIL')
                    image_urls.append('')
                await asyncio.sleep(1)
            print(f'上传完成: {len([u for u in image_urls if u])}/{len(img_bytes_list)}张成功')

        # 清除编辑器
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('Control+a')
        await asyncio.sleep(0.3)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)

        # 构建最终内容
        content_parts = []
        img_idx = 0
        n_imgs = len(image_urls)
        layout = {1: 1, 3: 2, 5: 2}

        for pi, pt in enumerate(paragraphs):
            content_parts.append(f'<p>{pt}</p>')
            if (pi + 1) in layout:
                for _ in range(layout[pi + 1]):
                    if img_idx < n_imgs and image_urls[img_idx]:
                        content_parts.append(f'<p><img src="{image_urls[img_idx]}" alt=""></p>')
                        img_idx += 1

        content_html = '\n'.join(content_parts)
        print(f'设置内容 ({len(content_html)}字符)...')

        # 设置内容
        await page.evaluate("""
            (content) => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.innerHTML = content;
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }
        """, content_html)
        await asyncio.sleep(2)

        # 触发编辑器变更
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('End')
        await asyncio.sleep(0.3)
        await page.keyboard.type(' ', delay=50)
        await asyncio.sleep(0.3)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)

        # 关闭弹窗
        try:
            for btn_text in ['不恢复', '关闭', '取消']:
                btn = page.locator(f'button:has-text("{btn_text}")').first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            mask = page.locator('.byte-drawer-mask').first
            if await mask.is_visible(timeout=2000):
                await page.evaluate('() => { const m = document.querySelector(".byte-drawer-mask"); if(m) m.remove(); }')
                await asyncio.sleep(0.5)
        except:
            pass

        # 点击标题触发blur
        try:
            await title_el.click(force=True, timeout=5000)
        except:
            await page.evaluate('() => { const t = document.querySelector(\'textarea[placeholder*="文章标题"]\'); if(t) t.focus(); }')
        await asyncio.sleep(0.5)
        await page.keyboard.type(' ', delay=50)
        await asyncio.sleep(0.3)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)

        # 等待自动保存
        print('等待自动保存...')
        await asyncio.sleep(15)

        # 验证
        await page.goto('https://mp.toutiao.com/profile_v4/manage/draft', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate('() => document.body.innerText || ""')

        if title[:8] in draft_text:
            print('[SUCCESS] 文章已在草稿箱!')
        else:
            print(f'首次验证失败 (页面{len(draft_text)}字符)，重试...')
            await asyncio.sleep(10)
            draft_text = await page.evaluate('() => document.body.innerText || ""')
            if title[:8] in draft_text:
                print('[SUCCESS] 文章已在草稿箱!')
            else:
                print(f'[FAIL] 未找到 (页面{len(draft_text)}字符)')

        await browser.close()

asyncio.run(main())