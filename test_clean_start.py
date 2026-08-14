#!/usr/bin/env python3
"""测试：删除现有草稿，然后从干净状态开始保存"""
import os, json, asyncio, requests
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
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

        # 1. 先看草稿箱
        print("=== 草稿箱 ===")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        
        # 获取草稿列表
        drafts = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('[class*="draft"], [class*="card"], [class*="item"]');
                const result = [];
                items.forEach(item => {
                    const text = item.innerText?.substring(0, 100);
                    if (text && text.includes('删除')) {
                        result.push(text);
                    }
                });
                return result.slice(0, 5);
            }
        """)
        print(f"草稿项: {drafts}")
        
        # 尝试找第一个草稿的"删除"按钮
        try:
            # 先找"编辑"旁边的"删除"
            delete_btns = page.locator("text=删除")
            count = await delete_btns.count()
            print(f"删除按钮数量: {count}")
            
            if count > 0:
                # 点击第一个删除
                await delete_btns.first.click()
                await asyncio.sleep(2)
                
                # 确认删除弹窗
                confirm_btn = page.locator("button:has-text('确定')").first
                if await confirm_btn.is_visible(timeout=3000):
                    await confirm_btn.click()
                    print("已确认删除")
                    await asyncio.sleep(3)
        except Exception as e:
            print(f"删除失败: {e}")

        await page.screenshot(path="/workspace/draft_after_delete.png")
        
        # 2. 现在导航到编辑器，选择"不恢复"
        print("\n=== 打开编辑器（不恢复草稿）===")
        await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        
        # 关闭弹窗
        try:
            for btn_text in ["关闭", "不恢复"]:
                btn = page.locator("text=" + btn_text).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    print(f"点击了'{btn_text}'")
                    await asyncio.sleep(1)
        except:
            pass
        
        await page.wait_for_selector(".ProseMirror", timeout=15000)
        
        # 检查编辑器是否为空
        editor_html = await page.evaluate("() => document.querySelector('.ProseMirror')?.innerHTML || ''")
        print(f"编辑器内容长度: {len(editor_html)}")
        
        # 输入测试内容
        editor_el = page.locator('.ProseMirror').first
        await editor_el.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type("测试内容-新草稿", delay=10)
        await asyncio.sleep(1)
        
        # 填写标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        if await title_el.is_visible(timeout=3000):
            await title_el.click()
            await asyncio.sleep(0.5)
            await title_el.fill("测试标题-新草稿")
            await asyncio.sleep(2)
        
        # 触发保存
        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }
        """)
        await asyncio.sleep(10)
        
        # 检查草稿箱
        print("\n=== 验证草稿箱 ===")
        await page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        draft_content = await page.evaluate("() => document.body.innerText.substring(0, 2000)")
        print(draft_content[:1000])
        
        await page.screenshot(path="/workspace/draft_final_check.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())