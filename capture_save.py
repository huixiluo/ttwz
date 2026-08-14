#!/usr/bin/env python3
"""捕获头条自动保存API - 拦截网络请求"""
import json, asyncio, time
from playwright.async_api import async_playwright

BASE_DIR = "/workspace"
COOKIE_FILE = f"{BASE_DIR}/toutiao_cookies.json"
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

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

        # 拦截所有请求和响应
        captured = []
        async def on_request(request):
            url = request.url
            if "mp.toutiao.com" in url and any(kw in url.lower() for kw in ["save", "draft", "ugc", "publish", "article"]):
                captured.append({
                    "type": "request",
                    "url": url[:300],
                    "method": request.method,
                    "post_data": (request.post_data or "")[:2000],
                    "headers": {k: v for k, v in request.headers.items() if k.lower() in ["content-type", "x-csrftoken"]},
                    "time": time.time()
                })

        async def on_response(response):
            url = response.url
            if "mp.toutiao.com" in url and any(kw in url.lower() for kw in ["save", "draft", "ugc", "publish", "article"]):
                try:
                    body = await response.text()
                    body = body[:1000]
                except:
                    body = "[cannot read]"
                captured.append({
                    "type": "response",
                    "url": url[:300],
                    "status": response.status,
                    "body": body,
                    "time": time.time()
                })

        page.on("request", on_request)
        page.on("response", on_response)

        print("导航到发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 移除遮罩
        await page.evaluate("""
            () => {
                document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay').forEach(m => {
                    if (m && m.parentNode) m.parentNode.removeChild(m);
                });
            }
        """)
        await asyncio.sleep(1)

        # 关闭弹窗
        try:
            for btn_text in ["关闭", "不恢复", "知道了", "确定"]:
                btn = page.locator(f"text={btn_text}").first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(0.5)
        except: pass

        # 等待编辑器
        await page.wait_for_selector(".ProseMirror", timeout=15000)
        await asyncio.sleep(2)

        # 用键盘输入一些内容
        print("键盘输入内容...")
        await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) { ed.innerHTML = ''; ed.focus(); } }")
        await asyncio.sleep(0.5)

        await page.keyboard.type("这是一段测试内容，用于触发自动保存。", delay=20)
        await asyncio.sleep(0.5)
        await page.keyboard.press('Enter')
        await asyncio.sleep(0.5)
        await page.keyboard.type("第二段测试内容，继续输入。", delay=20)
        await asyncio.sleep(3)

        # 填写标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click(timeout=5000)
        await asyncio.sleep(0.3)
        await title_el.fill("测试自动保存标题")
        await asyncio.sleep(5)

        # 等待保存
        print("等待自动保存 (30秒)...")
        for i in range(30):
            await asyncio.sleep(1)
            result = await page.evaluate("""
                () => { return document.body.innerText.indexOf('草稿已保存') !== -1; }
            """)
            if result:
                print(f"  [{i+1}s] 检测到保存!")
                break
        else:
            print("  未检测到保存")

        print("\n=== 捕获的请求 ===")
        for c in captured:
            if c['type'] == 'request':
                print(f"\n  REQ {c['method']} {c['url'][:200]}")
                if c['post_data']:
                    print(f"    POST: {c['post_data'][:500]}")
                if c['headers']:
                    print(f"    Headers: {c['headers']}")
            else:
                print(f"\n  RES {c['status']} {c['url'][:200]}")
                print(f"    Body: {c['body'][:500]}")

        await page.screenshot(path="/workspace/capture_save.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())