#!/usr/bin/env python3
"""通过直接操作页面Redux store来设置内容并保存"""
import os, re, json, time, base64, asyncio, io
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
    content_text = '\n'.join(paragraphs)
    print(f'段落: {len(paragraphs)}段, 总字数: {len(content_text)}')

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

        async def on_response(response):
            if 'publish' in response.url and response.request.method == 'POST':
                try:
                    body = await response.text()
                    print(f'  [SAVE] {body[:200]}')
                except:
                    pass
        page.on('response', on_response)

        print('导航到发布页...')
        await page.goto('https://mp.toutiao.com/profile_v4/graphic/publish', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(10)  # 等待完全初始化

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

        # 查找Redux store
        print('查找Redux store...')
        store_info = await page.evaluate('''
            () => {
                const info = {};
                
                // 查找所有可能的store key
                const rootDiv = document.getElementById('root') || document.getElementById('app');
                if (rootDiv) {
                    const keys = Object.keys(rootDiv);
                    info.rootKeys = keys.filter(k => k.startsWith('__react'));
                }
                
                // 查找window上的store
                for (const key of Object.keys(window)) {
                    const val = window[key];
                    if (val && typeof val === 'object' && val.getState && val.dispatch) {
                        info.storeKey = key;
                        info.stateKeys = Object.keys(val.getState());
                        break;
                    }
                }
                
                return info;
            }
        ''')
        print(f'  Store info: {json.dumps(store_info, ensure_ascii=False)}')

        # 填标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click(force=True, timeout=5000)
        await asyncio.sleep(0.5)
        await title_el.fill(title)
        await asyncio.sleep(2)

        # 使用page.evaluate通过ProseMirror的API设置内容
        print('设置内容（通过ProseMirror API）...')
        result = await page.evaluate(f'''
            () => {{
                const text = {json.dumps(content_text)};
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return 'no editor';
                
                // 尝试找到ProseMirror的view
                const pm = editor.pmViewDesc || editor.__pmViewDesc;
                
                // 尝试通过React fiber找到store
                const fiberKey = Object.keys(editor).find(k => k.startsWith('__reactFiber'));
                if (fiberKey) {{
                    let fiber = editor[fiberKey];
                    let depth = 0;
                    while (fiber && depth < 50) {{
                        // 查找store
                        if (fiber.memoizedState) {{
                            let state = fiber.memoizedState;
                            while (state) {{
                                if (state.queue && state.queue.dispatch) {{
                                    // 找到了dispatch
                                    return 'found dispatch at depth ' + depth;
                                }}
                                state = state.next;
                            }}
                        }}
                        fiber = fiber.return;
                        depth++;
                    }}
                }}
                
                return 'no dispatch found, fiberKey=' + (fiberKey || 'none');
            }}
        ''')
        print(f'  Result: {result}')

        # 尝试通过键盘输入方式设置内容
        print('通过键盘输入设置内容...')
        editor = page.locator('.ProseMirror').first
        await editor.click()
        await asyncio.sleep(0.5)

        # 使用page.evaluate通过execCommand插入HTML
        await page.evaluate(f'''
            () => {{
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return;
                editor.focus();
                const text = {json.dumps(content_text)};
                const paragraphs = text.split('\\n').filter(p => p.trim());
                const html = paragraphs.map(p => '<p>' + p + '</p>').join('');
                
                // 方法1: 使用execCommand
                document.execCommand('selectAll', false, null);
                document.execCommand('insertHTML', false, html);
            }}
        ''')
        await asyncio.sleep(3)

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
            for btn_text in ['不恢复', '关闭']:
                btn = page.locator(f'button:has-text("{btn_text}")').first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
        except:
            pass

        # 点击标题
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