#!/usr/bin/env python3
"""调试：检查草稿箱内容 + 编辑器页面截图"""
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

        # 1. 检查草稿箱
        print("=== 检查草稿箱 ===")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await page.screenshot(path="/workspace/draft_box.png", full_page=False)
        print("草稿箱截图: /workspace/draft_box.png")
        
        # 检查页面内容
        draft_text = await page.evaluate("""
            () => {
                const body = document.body.innerText;
                // 截取前2000字符
                return body.substring(0, 2000);
            }
        """)
        print(f"草稿箱页面内容:\n{draft_text[:1500]}")

        # 2. 打开编辑器，查看按钮
        print("\n=== 检查编辑器页面 ===")
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
        
        await page.screenshot(path="/workspace/editor_page.png", full_page=False)
        print("编辑器截图: /workspace/editor_page.png")

        # 检查所有按钮
        buttons = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                return Array.from(btns).slice(0, 30).map(b => ({
                    text: b.innerText?.trim()?.substring(0, 50),
                    class: b.className?.substring(0, 80),
                    visible: b.offsetParent !== null
                }));
            }
        """)
        print(f"页面按钮 ({len(buttons)}个):")
        for b in buttons:
            if b['text']:
                print(f"  [{b['class']}] '{b['text']}' visible={b['visible']}")

        # 检查ProseMirror
        has_editor = await page.evaluate("() => !!document.querySelector('.ProseMirror')")
        print(f"\nProseMirror存在: {has_editor}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())