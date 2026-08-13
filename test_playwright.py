#!/usr/bin/env python
"""测试Playwright基本功能"""
import asyncio, json, time
from playwright.async_api import async_playwright

CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
COOKIE_FILE = "/workspace/toutiao_cookies.json"

async def main():
    with open(COOKIE_FILE) as f:
        cookies = json.load(f)

    print("Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        print("Browser launched")
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        cookie_list = []
        for name, value in cookies.items():
            cookie_list.append({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
        await context.add_cookies(cookie_list)
        
        page = await context.new_page()
        
        # 测试导航
        print("Navigating to draft page...")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        print(f"Title: {await page.title()}")
        print(f"URL: {page.url}")
        
        # 导航到发布页
        print("\nNavigating to publish page...")
        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        print(f"Title: {await page.title()}")
        print(f"URL: {page.url}")
        
        # 检查编辑器
        editor_exists = await page.evaluate("() => !!document.querySelector('.ProseMirror')")
        print(f"Editor exists: {editor_exists}")
        
        if editor_exists:
            # 测试填标题
            title_el = page.locator('textarea[placeholder*="文章标题"]').first
            print(f"Title input exists: {await title_el.is_visible()}")
            
            # 测试设内容
            await page.evaluate("""
                () => {
                    const editor = document.querySelector('.ProseMirror');
                    if (editor) {
                        editor.innerHTML = '<p>测试内容</p>';
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                }
            """)
            await asyncio.sleep(1)
            content = await page.evaluate("() => document.querySelector('.ProseMirror').innerText")
            print(f"Content: {content}")
        
        await browser.close()
        print("\nDone!")

asyncio.run(main())