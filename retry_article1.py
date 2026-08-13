#!/usr/bin/env python3
"""通过Playwright获取pgc_id，然后用API保存第1篇文章"""
import os, re, json, time, asyncio, urllib.parse
from playwright.async_api import async_playwright
import requests

BASE_DIR = '/workspace'
COOKIE_FILE = os.path.join(BASE_DIR, 'toutiao_cookies.json')
CHROME_PATH = '/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

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

    # Step 1: 用Playwright获取pgc_id
    pgc_id = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent=UA)
        cookie_list = [{'name': k, 'value': v, 'domain': '.toutiao.com', 'path': '/'} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 监听所有请求，捕获pgc_id
        async def on_request(request):
            nonlocal pgc_id
            post_data = request.post_data
            if post_data and 'pgc_id' in post_data:
                try:
                    params = urllib.parse.parse_qs(post_data)
                    pid = params.get('pgc_id', ['0'])[0]
                    if pid and pid != '0' and pid.isdigit():
                        pgc_id = pid
                        print(f'  捕获到pgc_id: {pgc_id}')
                except:
                    pass

        page.on('request', on_request)

        print('导航到发布页...')
        await page.goto('https://mp.toutiao.com/profile_v4/graphic/publish', wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(5)

        # 关闭弹窗
        try:
            for btn_text in ['关闭', '不恢复']:
                btn = page.locator(f'text={btn_text}').first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1)
        except:
            pass

        await page.wait_for_selector('.ProseMirror', timeout=15000)
        print('编辑器就绪')

        # 填标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click()
        await asyncio.sleep(0.5)
        await title_el.fill(title)
        await asyncio.sleep(2)

        # 在编辑器输入内容触发pgc_id生成
        editor = page.locator('.ProseMirror').first
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type('开始写文章', delay=50)
        await asyncio.sleep(1)
        await page.keyboard.press('Control+a')
        await asyncio.sleep(0.3)
        await page.keyboard.press('Backspace')
        await asyncio.sleep(1)

        # 等待自动保存
        print('等待自动保存（获取pgc_id）...')
        await asyncio.sleep(10)

        if not pgc_id:
            # 从page的JS中获取
            pgc_id = await page.evaluate('''
                () => {
                    const allKeys = Object.keys(window).filter(k => 
                        k.toLowerCase().includes('pgc') || k.toLowerCase().includes('article')
                    );
                    for (const key of allKeys) {
                        const val = window[key];
                        if (typeof val === 'string' && /^\\d{15,}$/.test(val)) return val;
                        if (typeof val === 'object' && val) {
                            const s = JSON.stringify(val);
                            const m = s.match(/"pgc_id"\\s*:\\s*"(\\d+)"/);
                            if (m) return m[1];
                        }
                    }
                    return '';
                }
            ''')
            print(f'  JS获取pgc_id: {pgc_id}')

        await browser.close()

    if not pgc_id:
        print('[ERROR] 无法获取pgc_id')
        return

    # Step 2: 用API保存草稿
    print(f'\n用API保存草稿 (pgc_id={pgc_id})...')
    session = requests.Session()
    session.headers.update({
        'User-Agent': UA, 'Accept': 'application/json',
        'Referer': 'https://mp.toutiao.com/', 'Origin': 'https://mp.toutiao.com',
    })
    for n, v in cookies.items():
        session.cookies.set(n, v, domain='.toutiao.com', path='/')

    content_parts = [f'<p>{p}</p>' for p in paragraphs]
    content_html = '\n'.join(content_parts)
    word_count = sum(len(p) for p in paragraphs)

    extra = json.dumps({'content_source': 100000000402, 'content_word_cnt': word_count})
    csrf = session.cookies.get('passport_csrf_token', '')

    form_data = {
        'article_type': '0', 'pgc_id': pgc_id, 'source': '29',
        'title': title, 'content': content_html, 'save': '0',
        'entrance': 'main', 'timer_status': '0', 'timer_time': '',
        'extra': extra, 'title_id': '', 'ic_uri_list': '[]',
        'search_creation_info': '', 'is_refute_rumor': '0',
        'appid_list': '[]', 'stock_ids': '[]', 'concern_list': '[]',
        'comic_attr': '', 'is_app_preview': '', 'externalLinkChecked': 'false',
        'externalLink': '', 'claimOrigin': '0', 'copyRightChecked': '1',
        'subTitle': '', 'subCoverList': '[]', 'coverList': '[]',
        'coverType': '0', 'articleAdType': '0', 'isFansArticle': '0',
        'activityId': '', 'communitySync': '0',
    }

    resp = session.post(
        'https://mp.toutiao.com/mp/agw/article/publish?source=mp&type=article&aid=1231',
        data=form_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrf}
    )
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.text[:500]}')

    result = resp.json()
    if result.get('message') == 'success' or result.get('code') == 0:
        print('[SUCCESS] 草稿保存成功!')
    else:
        print(f'[FAIL] code={result.get("code")}, msg={result.get("message")}')

if __name__ == '__main__':
    asyncio.run(main())