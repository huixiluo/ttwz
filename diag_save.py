#!/usr/bin/env python3
"""捕获完整POST数据诊断保存失败原因"""
import os, re, json, time, base64, asyncio, io, urllib.parse
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = '/workspace'
COOKIE_FILE = os.path.join(BASE_DIR, 'toutiao_cookies.json')
CHROME_PATH = '/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome'

def extract_html_text(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    paragraphs = []
    for m in re.finditer(r'<p>([^<]+)</p>', html):
        text = m.group(1).strip()
        if text:
            paragraphs.append(text)
    return paragraphs

async def main():
    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    html_path = '/workspace/output/tt_hot_tt_娱乐_1_20260813_093751.html'
    title = '雷佳音自曝往事，演陈俊生不为戏，一句话扎心了'
    paragraphs = extract_html_text(html_path)
    print(f'段落: {len(paragraphs)}段')

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

        save_requests = []

        async def on_request(request):
            if 'publish' in request.url and request.method == 'POST':
                post_data = request.post_data or ''
                params = urllib.parse.parse_qs(post_data)
                pgc_id = params.get('pgc_id', ['N/A'])[0]
                save = params.get('save', ['N/A'])[0]
                content = params.get('content', [''])[0]
                title_val = params.get('title', [''])[0]
                word_cnt = params.get('extra', [''])[0]
                try:
                    extra = json.loads(word_cnt)
                    word_cnt = extra.get('content_word_cnt', 0)
                except:
                    word_cnt = 0

                save_requests.append({
                    'pgc_id': pgc_id,
                    'save': save,
                    'content_len': len(content),
                    'content_preview': content[:100],
                    'title': title_val[:30],
                    'word_cnt': word_cnt,
                })
                print(f'  [SAVE REQ] pgc_id={pgc_id} save={save} content_len={len(content)} word_cnt={word_cnt} title={title_val[:30]}')

        page.on('request', on_request)

        async def on_response(response):
            if 'publish' in response.url and response.request.method == 'POST':
                try:
                    body = await response.text()
                    print(f'  [SAVE RESP] {body[:200]}')
                except:
                    pass
        page.on('response', on_response)

        print('导航到发布页...')
        await page.goto('https://mp.toutiao.com/profile_v4/graphic/publish', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(8)

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

        # 键盘输入一段文字
        editor = page.locator('.ProseMirror').first
        await editor.click()
        await asyncio.sleep(0.5)
        # 只输入一段，观察保存请求
        await page.keyboard.type(paragraphs[0], delay=10)
        await asyncio.sleep(1)

        print('等待自动保存...')
        await asyncio.sleep(15)

        print(f'\n=== 捕获到 {len(save_requests)} 个保存请求 ===')
        for i, req in enumerate(save_requests):
            print(f'  [{i}] pgc_id={req["pgc_id"]} content_len={req["content_len"]} word_cnt={req["word_cnt"]}')

        await browser.close()

asyncio.run(main())