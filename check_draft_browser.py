#!/usr/bin/env python3
"""检查草稿箱 - 浏览器版"""
import json, asyncio
from playwright.async_api import async_playwright

BASE_DIR = "/workspace"
COOKIE_FILE = f"{BASE_DIR}/toutiao_cookies.json"
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

async def main():
    with open(COOKIE_FILE) as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=UA)
        await context.add_cookies([{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()])
        page = await context.new_page()

        # 监听网络请求
        request_urls = []
        async def on_request(request):
            url = request.url
            if "agw" in url or "draft" in url or "save" in url:
                request_urls.append(f"{request.method} {url[:200]}")
        page.on("request", on_request)

        print("访问草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        title = await page.title()
        print(f"页面标题: {title}")

        # 截图
        await page.screenshot(path="/workspace/draft_check.png", full_page=True)

        # 获取草稿箱内容
        draft_text = await page.evaluate("() => document.body.innerText.substring(0, 8000)")
        print(f"\n=== 草稿箱页面内容（前8000字符）===")
        print(draft_text)

        print(f"\n=== 相关网络请求 ===")
        for url in request_urls:
            print(f"  {url}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())