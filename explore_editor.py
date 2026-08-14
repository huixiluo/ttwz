#!/usr/bin/env python3
"""探索编辑器页面结构 - 查找保存按钮和API"""
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
        
        # 拦截所有请求
        all_requests = []
        async def on_request(request):
            url = request.url
            if "mp.toutiao.com" in url and ("agw" in url or "draft" in url or "save" in url or "article" in url):
                all_requests.append({
                    "url": url[:200],
                    "method": request.method,
                    "post_data": (request.post_data or "")[:500],
                    "time": time.time()
                })
        page.on("request", on_request)
        
        print("导航到发布页面...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        
        # 移除遮罩
        await page.evaluate("""
            () => {
                document.querySelectorAll('.byte-drawer-mask, .byte-modal-mask, .byte-overlay, .byte-drawer-wrapper, .byte-modal-wrapper').forEach(m => {
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
        
        # 查找所有按钮
        print("\n=== 页面按钮 ===")
        buttons = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, [role="button"], .btn');
                return Array.from(btns).slice(0, 30).map(b => ({
                    text: (b.textContent || '').trim().substring(0, 50),
                    class: (b.className || '').substring(0, 80),
                    visible: b.offsetParent !== null
                }));
            }
        """)
        for b in buttons:
            if b['text']:
                print(f"  [{b['class'][:40]}] '{b['text']}' visible={b['visible']}")
        
        # 在编辑器输入一些内容
        await page.evaluate("""
            () => {
                const ed = document.querySelector('.ProseMirror');
                if (ed) { ed.innerHTML = ''; ed.focus(); }
            }
        """)
        await asyncio.sleep(0.5)
        
        await page.keyboard.type("测试文章内容 - 这是第一段测试文字。", delay=0)
        await asyncio.sleep(0.5)
        await page.keyboard.press('Enter')
        await asyncio.sleep(0.3)
        await page.keyboard.type("这是第二段测试文字，用于触发自动保存。", delay=0)
        await asyncio.sleep(2)
        
        # 填写标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        try:
            await title_el.click(timeout=5000)
        except:
            await page.evaluate("""
                () => {
                    const el = document.querySelector('textarea[placeholder*="文章标题"]');
                    if (el) { el.focus(); el.click(); }
                }
            """)
        await asyncio.sleep(0.5)
        await title_el.fill("测试标题-自动保存测试")
        await asyncio.sleep(3)
        
        # 再次查找按钮
        print("\n=== 输入内容后的按钮 ===")
        buttons2 = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, [role="button"], .btn');
                return Array.from(btns).slice(0, 30).map(b => ({
                    text: (b.textContent || '').trim().substring(0, 50),
                    class: (b.className || '').substring(0, 80),
                    visible: b.offsetParent !== null
                }));
            }
        """)
        for b in buttons2:
            if b['text']:
                print(f"  [{b['class'][:40]}] '{b['text']}' visible={b['visible']}")
        
        # 等待保存提示
        print("\n=== 等待保存 (30秒) ===")
        for i in range(30):
            await asyncio.sleep(1)
            result = await page.evaluate("""
                () => {
                    const body = document.body.innerText;
                    if (body.indexOf('草稿已保存') !== -1 || body.indexOf('保存成功') !== -1) return true;
                    const btns = document.querySelectorAll('button, span');
                    for (let j = 0; j < btns.length; j++) {
                        if ((btns[j].textContent || '').indexOf('草稿已保存') !== -1) return true;
                    }
                    return false;
                }
            """)
            if result:
                print(f"  [{i+1}s] 检测到保存!")
                break
        else:
            print("  未检测到保存")
        
        # 打印所有API请求
        print("\n=== 捕获的API请求 ===")
        for req in all_requests:
            print(f"  {req['method']} {req['url'][:150]}")
            if req['post_data']:
                print(f"    POST: {req['post_data'][:300]}")
        
        await page.screenshot(path="/workspace/explore_editor.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())