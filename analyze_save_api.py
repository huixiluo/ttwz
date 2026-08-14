#!/usr/bin/env python3
"""拦截所有mp.toutiao.com API请求，分析保存流程"""
import os, json, asyncio
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

async def main():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, user_agent=UA
        )
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])

        print("验证登录...")
        test_page = await context.new_page()
        await test_page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        if "登录" in (await test_page.title()):
            print("[ERROR] Cookie已过期")
            await browser.close()
            return
        print("[OK] 登录有效\n")
        await test_page.close()

        page = await context.new_page()

        # 拦截所有API请求
        all_requests = []
        all_responses = []

        async def on_request(request):
            url = request.url
            if "mp.toutiao.com" in url and "/mp/agw/" in url:
                try:
                    post_data = request.post_data
                    all_requests.append({
                        "url": url[:250],
                        "method": request.method,
                        "body": (post_data or "")[:2000]
                    })
                except: pass

        async def on_response(response):
            url = response.url
            if "mp.toutiao.com" in url and "/mp/agw/" in url:
                try:
                    body = await response.text()
                    body = body[:600]
                except: body = "[err]"
                all_responses.append({
                    "url": url[:250],
                    "status": response.status,
                    "body": body
                })

        page.on("request", on_request)
        page.on("response", on_response)

        print("=== 阶段1: 打开发布页面 ===")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 关闭弹窗
        for btn_text in ["关闭", "不恢复", "知道了", "确定"]:
            try:
                btn = page.locator(f"text={btn_text}").first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await asyncio.sleep(0.3)
            except: pass

        # 等待编辑器
        for i in range(20):
            await asyncio.sleep(1)
            ready = await page.evaluate("""
                () => { const ed = document.querySelector('.ProseMirror'); return ed && ed.getBoundingClientRect().width > 0; }
            """)
            if ready: break

        print(f"\n页面加载阶段 API ({len(all_requests)}请求, {len(all_responses)}响应):")
        for i, (req, resp) in enumerate(zip(all_requests, all_responses)):
            print(f"  [{i}] {req['method']} {req['url'][:120]}")
            resp_body = resp.get('body', '')
            if '7050' in resp_body or 'save' in resp_body.lower() or 'draft' in resp_body.lower():
                print(f"       -> {resp_body[:250]}")

        # 清空记录
        all_requests.clear()
        all_responses.clear()

        print(f"\n=== 阶段2: 输入文字和标题 ===")
        await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
        await asyncio.sleep(0.3)
        await page.keyboard.type("测试文章内容，用于分析保存流程。", delay=0)
        await asyncio.sleep(1)

        await page.evaluate("""
            () => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, '测试标题-API分析');
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
            }
        """)
        await asyncio.sleep(5)

        print(f"输入阶段 API ({len(all_requests)}请求, {len(all_responses)}响应):")
        for i, (req, resp) in enumerate(zip(all_requests, all_responses)):
            print(f"  [{i}] {req['method']} {req['url'][:120]}")
            resp_body = resp.get('body', '')
            if resp_body and len(resp_body) > 10:
                print(f"       -> {resp_body[:250]}")
            if req.get('body'):
                print(f"       <- body: {req['body'][:250]}")

        # 清空
        all_requests.clear()
        all_responses.clear()

        print(f"\n=== 阶段3: 点击预览按钮 ===")
        try:
            preview_btn = page.locator("text=预览").first
            await preview_btn.click(timeout=5000)
            print("已点击预览")
        except:
            await page.evaluate("""
                () => { const btns = document.querySelectorAll('button'); for (const b of btns) { if ((b.textContent||'').indexOf('预览')!==-1) { b.click(); return; } } }
            """)
            print("JS点击预览")
        await asyncio.sleep(5)

        # 关闭预览窗口
        pages = context.pages
        for p in pages:
            if p != page:
                await p.close()
                await asyncio.sleep(1)

        print(f"预览阶段 API ({len(all_requests)}请求, {len(all_responses)}响应):")
        for i, (req, resp) in enumerate(zip(all_requests, all_responses)):
            print(f"  [{i}] {req['method']} {req['url'][:120]}")
            resp_body = resp.get('body', '')
            if resp_body and len(resp_body) > 10:
                print(f"       -> {resp_body[:250]}")
            if req.get('body'):
                print(f"       <- body: {req['body'][:250]}")

        # 等待保存提示
        print(f"\n=== 等待保存结果 ===")
        for i in range(15):
            await asyncio.sleep(1)
            saved = await page.evaluate("""
                () => { const body = document.body.innerText; return body.indexOf('草稿已保存') !== -1; }
            """)
            if saved:
                print(f"检测到保存成功！")
                break

        await page.screenshot(path="/workspace/api_analysis.png")
        await page.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())