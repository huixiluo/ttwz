#!/usr/bin/env python3
"""监听头条编辑器自动保存的网络请求"""
import os, json, asyncio
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def main():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

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
        cookie_list = [{"name": k, "value": v, "domain": ".toutiao.com", "path": "/"} for k, v in cookies.items()]
        await context.add_cookies(cookie_list)
        page = await context.new_page()

        # 拦截所有网络请求
        captured = []
        async def on_request(request):
            url = request.url
            if any(k in url for k in ['save', 'draft', 'publish', 'article', 'ugc', 'agw']):
                captured.append({
                    "url": url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "post_data": request.post_data
                })
        
        async def on_response(response):
            url = response.url
            if any(k in url for k in ['save', 'draft', 'publish', 'article', 'ugc', 'agw']):
                try:
                    body = await response.text()
                    body = body[:500]
                except:
                    body = "[error reading body]"
                captured.append({
                    "type": "response",
                    "url": url,
                    "status": response.status,
                    "body": body
                })

        page.on("request", on_request)
        page.on("response", on_response)

        print("导航到编辑器...")
        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 关闭弹窗
        try:
            for btn_text in ["关闭", "不恢复"]:
                btn = page.locator("text=" + btn_text).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(1)
        except:
            pass

        # 关闭继续编辑弹窗
        try:
            continue_btn = page.locator("button:has-text('继续编辑')").first
            if await continue_btn.is_visible(timeout=3000):
                await continue_btn.click()
                await asyncio.sleep(2)
        except:
            pass

        await page.wait_for_selector(".ProseMirror", timeout=15000)
        
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
        await asyncio.sleep(1)

        print("输入测试内容...")
        editor = page.locator('.ProseMirror').first
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type("这是一段测试文字，用于触发自动保存功能。", delay=10)
        await asyncio.sleep(0.5)

        # 填写标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click()
        await asyncio.sleep(0.5)
        await title_el.fill("测试标题-自动保存")
        await asyncio.sleep(0.5)

        # 触发input事件
        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                    editor.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }
        """)

        print("等待自动保存触发...")
        await asyncio.sleep(15)

        print(f"\n=== 捕获到的网络请求 ({len(captured)}个) ===")
        for c in captured:
            print(f"\n---")
            for k, v in c.items():
                if k == 'post_data' and v:
                    print(f"  {k}: {v[:500]}")
                elif k == 'headers' and v:
                    # 只显示关键headers
                    relevant = {hk: hv for hk, hv in v.items() if hk.lower() in ['content-type', 'x-csrftoken', 'x-requested-with']}
                    print(f"  headers: {relevant}")
                elif k == 'body':
                    print(f"  body: {v[:500]}")
                else:
                    print(f"  {k}: {v}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())