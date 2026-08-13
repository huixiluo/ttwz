#!/usr/bin/env python3
"""通过剪贴板粘贴方式设置内容，确保ProseMirror检测到变更"""
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
            headless=True, executable_path=CHROME_PATH,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        await context.grant_permissions(['clipboard-read', 'clipboard-write'])
        cookie_list = [{'name': k, 'value': v, 'domain': '.toutiao.com', 'path': '/'} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 监听保存请求
        async def on_request(request):
            if 'publish' in request.url and request.method == 'POST':
                post_data = request.post_data or ''
                import urllib.parse
                params = urllib.parse.parse_qs(post_data)
                pgc_id = params.get('pgc_id', ['N/A'])[0]
                save = params.get('save', ['N/A'])[0]
                content_len = len(params.get('content', [''])[0])
                title_val = params.get('title', [''])[0]
                print(f'  [SAVE] pgc_id={pgc_id} save={save} content_len={content_len} title={title_val[:30]}')

        page.on('request', on_request)

        async def on_response(response):
            if 'publish' in response.url and response.request.method == 'POST':
                try:
                    body = await response.text()
                    code = ''
                    try:
                        code = json.loads(body).get('code', '')
                    except: pass
                    print(f'  [SAVE RESP] {code}: {body[:150]}')
                except:
                    pass

        page.on('response', on_response)

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

        # 填标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click(force=True, timeout=5000)
        await asyncio.sleep(0.5)
        await title_el.fill(title)
        await asyncio.sleep(2)

        # 逐张上传图片
        editor = page.locator('.ProseMirror').first
        image_urls = []
        if img_bytes_list:
            print(f'上传{len(img_bytes_list)}张图片...')
            for img_idx, img_bytes in enumerate(img_bytes_list):
                await page.evaluate('() => { const e = document.querySelector(".ProseMirror"); if(e) { e.innerHTML = "<p></p>"; e.dispatchEvent(new Event("input", {bubbles: true})); } }')
                await asyncio.sleep(0.5)
                await page.evaluate('() => { const e = document.querySelector(".ProseMirror"); if(e) e.focus(); }')
                await asyncio.sleep(0.3)

                b64_str = base64.b64encode(img_bytes).decode('ascii')
                await page.evaluate(f'''
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
                        const fd = {{files: [file], items: [], types: ['Files'], getData: function() {{ return ''; }}, setData: function() {{}}, clearData: function() {{}}}};
                        Object.defineProperty(ev, 'clipboardData', {{value: fd}});
                        editor.dispatchEvent(ev);
                    }}
                ''')

                img_url = ''
                for _ in range(60):
                    await asyncio.sleep(1)
                    img_url = await page.evaluate('() => { const i = document.querySelector(".ProseMirror img"); return i ? i.src : ""; }')
                    if img_url and not img_url.startswith('blob:') and not img_url.startswith('data:'):
                        break
                image_urls.append(img_url)
                print(f'  图片{img_idx+1}: {"OK" if img_url else "FAIL"}')
                await asyncio.sleep(1)
            print(f'上传完成: {len([u for u in image_urls if u])}/{len(img_bytes_list)}张成功')

        # 清除编辑器
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('Control+a')
        await asyncio.sleep(0.3)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)

        # 构建纯文本内容（用于粘贴）
        text_content = '\n\n'.join(paragraphs)
        print(f'纯文本内容: {len(text_content)}字符')

        # 通过粘贴方式设置内容，确保ProseMirror检测到变更
        print('通过粘贴设置内容...')
        await editor.click()
        await asyncio.sleep(0.5)

        # 使用page.evaluate设置剪贴板内容然后粘贴
        await page.evaluate(f'''
            () => {{
                const text = {json.dumps(text_content)};
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return;
                editor.focus();
                
                const pasteEvent = new ClipboardEvent('paste', {{
                    bubbles: true, cancelable: true
                }});
                const fakeData = {{
                    items: [],
                    types: ['text/plain'],
                    getData: function(type) {{ return type === 'text/plain' ? text : ''; }},
                    setData: function() {{}},
                    clearData: function() {{}}
                }};
                Object.defineProperty(pasteEvent, 'clipboardData', {{
                    value: fakeData, writable: false, configurable: true
                }});
                editor.dispatchEvent(pasteEvent);
            }}
        ''')
        await asyncio.sleep(3)

        # 插入图片URL到内容中
        if image_urls:
            print('插入图片...')
            valid_urls = [u for u in image_urls if u]
            # 在第1、3、5段后插入图片
            insert_positions = [1, 3, 5]
            img_idx = 0
            for pos in insert_positions:
                if img_idx >= len(valid_urls):
                    break
                # 在编辑器中插入图片
                await page.evaluate(f'''
                    () => {{
                        const editor = document.querySelector('.ProseMirror');
                        if (!editor) return;
                        editor.focus();
                        const img = document.createElement('img');
                        img.src = "{valid_urls[img_idx]}";
                        const pasteEvent = new ClipboardEvent('paste', {{
                            bubbles: true, cancelable: true
                        }});
                        const fakeData = {{
                            files: [], items: [], types: ['text/html'],
                            getData: function(type) {{ return type === 'text/html' ? '<img src="{valid_urls[img_idx]}" />' : ''; }},
                            setData: function() {{}},
                            clearData: function() {{}}
                        }};
                        Object.defineProperty(pasteEvent, 'clipboardData', {{
                            value: fakeData, writable: false, configurable: true
                        }});
                        editor.dispatchEvent(pasteEvent);
                    }}
                ''')
                img_idx += 1
                await asyncio.sleep(1)

        # 触发编辑器变更
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press('End')
        await asyncio.sleep(0.3)
        await page.keyboard.press('Enter')
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
        except:
            pass

        # 点击标题触发blur
        try:
            await title_el.click(force=True, timeout=5000)
        except:
            pass
        await asyncio.sleep(0.5)

        print('等待自动保存...')
        await asyncio.sleep(15)

        # 验证
        await page.goto('https://mp.toutiao.com/profile_v4/manage/draft', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate('() => document.body.innerText || ""')

        if title[:8] in draft_text:
            print('[SUCCESS] 文章已在草稿箱!')
        else:
            print(f'[FAIL] 未找到 (页面{len(draft_text)}字符)')

        await browser.close()

asyncio.run(main())