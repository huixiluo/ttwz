#!/usr/bin/env python3
"""测试：纯键盘输入是否能保存成功（无图片，无PM API）"""
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

        # 拦截请求
        save_reqs = []
        save_resps = []
        async def on_request(request):
            url = request.url
            if "mp.toutiao.com" in url and "publish" in url.lower():
                try:
                    post_data = request.post_data
                    if post_data: save_reqs.append({"url": url[:200], "body": post_data[:2000]})
                except: pass
        async def on_response(response):
            url = response.url
            if "mp.toutiao.com" in url and "publish" in url.lower():
                try:
                    body = await response.text()
                    body = body[:500]
                except: body = "[err]"
                save_resps.append({"url": url[:200], "status": response.status, "body": body})
        page.on("request", on_request)
        page.on("response", on_response)

        print("打开发布页面...")
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

        print("输入测试文字...")
        test_text = "这是一篇测试文章。用于验证头条草稿箱的自动保存功能是否正常工作。如果这段文字能够成功保存到草稿箱，说明保存机制本身没有问题，问题出在图片插入环节。"
        await page.evaluate("() => { const ed = document.querySelector('.ProseMirror'); if (ed) ed.focus(); }")
        await asyncio.sleep(0.3)
        await page.keyboard.type(test_text, delay=0)
        await asyncio.sleep(1)

        print("填写标题...")
        await page.evaluate("""
            () => {
                const el = document.querySelector('textarea[placeholder*="文章标题"]');
                if (!el) return;
                el.focus();
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(el, '测试文章-纯文字保存验证');
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
            }
        """)
        await asyncio.sleep(3)

        # 等待保存
        print("等待自动保存...")
        saved = False
        for i in range(30):
            await asyncio.sleep(1)
            s = await page.evaluate("""
                () => { const body = document.body.innerText; return body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1; }
            """)
            if s:
                print(f"  [OK] 检测到保存成功提示！(第{i+1}秒)")
                saved = True
                break

        if not saved:
            print("  未检测到保存提示，尝试触发保存...")
            # 修改标题触发保存
            await page.evaluate("""
                () => {
                    const el = document.querySelector('textarea[placeholder*="文章标题"]');
                    if (!el) return;
                    el.focus();
                    el.dispatchEvent(new KeyboardEvent('keydown', {key: ' ', bubbles: true}));
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                }
            """)
            await asyncio.sleep(0.3)
            await page.evaluate("""
                () => {
                    const el = document.querySelector('textarea[placeholder*="文章标题"]');
                    if (!el) return;
                    el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Backspace', bubbles: true}));
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.blur();
                }
            """)
            for i in range(15):
                await asyncio.sleep(1)
                s = await page.evaluate("""
                    () => { const body = document.body.innerText; return body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1; }
                """)
                if s:
                    print(f"  [OK] 检测到保存成功提示！")
                    saved = True
                    break

        # 打印请求和响应
        print(f"\n保存请求 ({len(save_reqs)}):")
        for req in save_reqs:
            body = req.get('body', '')
            # 解析content_word_cnt
            import re
            cnt_match = re.search(r'content_word_cnt%22%3A(\d+)', body)
            cnt = cnt_match.group(1) if cnt_match else '?'
            print(f"  word_cnt={cnt}")

        print(f"\n保存响应 ({len(save_resps)}):")
        for resp in save_resps:
            if '7050' in resp.get('body', '') or 'save' in resp.get('url', '').lower():
                print(f"  {resp['status']} {resp['url'][:80]}")
                print(f"    body: {resp['body'][:300]}")

        # 验证草稿箱
        print(f"\n验证草稿箱...")
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
        if "测试文章-纯文字保存验证" in draft_text:
            print("[OK] 文章已在草稿箱中！")
        else:
            print("[FAIL] 未在草稿箱中找到文章")
            print(f"草稿箱内容: {draft_text[:1000]}")

        await page.screenshot(path="/workspace/test_simple_save.png")
        await page.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())