#!/usr/bin/env python3
"""测试：上传一篇测试文章，观察成功时的自动保存请求"""
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

    # 使用第2篇文章（邹市明）的HTML，因为之前成功过
    html_path = '/workspace/output/tt_hot_tt_体育_2_20260813_093751.html'
    title = '测试保存test123'

    paragraphs, images = extract_html_text_and_images(html_path)
    print(f'段落: {len(paragraphs)}段, 图片: {len(images)}张')

    img_bytes_list = []
    for img in images[:2]:  # 只用2张图片加快速度
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
        cookie_list = [{'name': k, 'value': v, 'domain': '.toutiao.com', 'path': '/'} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 详细的请求/响应监听
        async def on_request(request):
            if 'publish' in request.url and request.method == 'POST':
                post_data = request.post_data or ''
                print(f'\n>>> AUTO-SAVE REQUEST <<<')
                print(f'URL: {request.url}')
                print(f'POST data (first 500): {post_data[:500]}')
                # 解析pgc_id
                if 'pgc_id=' in post_data:
                    import urllib.parse
                    params = urllib.parse.parse_qs(post_data)
                    print(f'pgc_id in POST: {params.get("pgc_id", ["N/A"])[0]}')
                    print(f'save in POST: {params.get("save", ["N/A"])[0]}')

        page.on('request', on_request)

        async def on_response(response):
            if 'publish' in response.url and response.request.method == 'POST':
                try:
                    body = await response.text()
                    print(f'>>> AUTO-SAVE RESPONSE <<<')
                    print(f'Status: {response.status}')
                    print(f'Body: {body[:500]}')
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

        # 编辑器输入文字
        editor = page.locator('.ProseMirror').first
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type('测试内容', delay=50)
        await asyncio.sleep(2)

        print('等待自动保存...')
        await asyncio.sleep(15)
        print('Done waiting')

        await browser.close()

asyncio.run(main())