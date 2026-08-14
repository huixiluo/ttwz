#!/usr/bin/env python3
"""调试：获取article/new的完整响应和pgc_id"""
import json, asyncio
from playwright.async_api import async_playwright

CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def main():
    with open("toutiao_cookies.json") as f:
        cookies = json.load(f)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=UA)
        await context.add_cookies([{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()])
        
        page = await context.new_page()
        
        # 拦截article/new响应
        new_resp = []
        async def handle_response(response):
            if 'article/new' in response.url:
                try:
                    body = await response.text()
                    new_resp.append(body)
                except: pass
        page.on('response', handle_response)
        
        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        
        for resp in new_resp:
            print(f"article/new 完整响应:")
            print(resp[:2000])
        
        await browser.close()

asyncio.run(main())