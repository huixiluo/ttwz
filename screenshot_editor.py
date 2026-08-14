#!/usr/bin/env python3
"""截图编辑器全貌，寻找保存草稿的方法"""
import json, asyncio
from playwright.async_api import async_playwright

BASE_DIR = "/workspace"
COOKIE_FILE = f"{BASE_DIR}/toutiao_cookies.json"
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

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

        print("打开编辑器...")
        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        try:
            for btn_text in ["关闭", "不恢复"]:
                btn = page.locator("text=" + btn_text).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(1)
        except:
            pass

        await page.wait_for_selector(".ProseMirror", timeout=15000)

        # 全页截图
        await page.screenshot(path="/workspace/editor_full.png", full_page=True)
        print("全页截图: /workspace/editor_full.png")

        # 查找所有可能的菜单/下拉按钮
        all_buttons = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('button, [role="button"], .byte-btn, [class*="btn"], [class*="dropdown"], [class*="menu"], [class*="more"]');
                return Array.from(all).map(el => ({
                    tag: el.tagName,
                    text: (el.innerText || '').trim().substring(0, 30),
                    class: (el.className || '').substring(0, 60),
                    title: el.getAttribute('title') || '',
                    aria_label: el.getAttribute('aria-label') || '',
                    visible: el.offsetParent !== null && el.offsetWidth > 0
                })).filter(b => b.text || b.title || b.aria_label);
            }
        """)
        
        print(f"\n所有可见按钮/交互元素:")
        for b in all_buttons:
            if b['visible']:
                print(f"  [{b['class'][:40]}] '{b['text']}' title='{b['title']}' aria='{b['aria_label']}'")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())