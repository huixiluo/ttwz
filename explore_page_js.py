#!/usr/bin/env python3
"""尝试通过页面JS直接调用保存函数"""
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

        # 探索页面上的JS对象
        print("探索JS对象...")
        js_info = await page.evaluate("""
            () => {
                const result = {};
                
                // 检查window上的关键对象
                for (const key of Object.keys(window)) {
                    if (key.toLowerCase().includes('store') || 
                        key.toLowerCase().includes('redux') ||
                        key.toLowerCase().includes('state') ||
                        key.toLowerCase().includes('action') ||
                        key.toLowerCase().includes('dispatch') ||
                        key.toLowerCase().includes('save') ||
                        key.toLowerCase().includes('draft') ||
                        key.toLowerCase().includes('publish')) {
                        result[key] = typeof window[key];
                    }
                }
                
                // 检查是否有__INITIAL_STATE__
                if (window.__INITIAL_STATE__) {
                    result['__INITIAL_STATE___keys'] = Object.keys(window.__INITIAL_STATE__).slice(0, 10);
                }
                
                return JSON.stringify(result, null, 2);
            }
        """)
        print(f"JS对象: {js_info[:1000]}")

        # 检查ProseMirror视图
        pm_info = await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return 'no editor';
                
                const result = {};
                result['pmViewDesc'] = !!editor.pmViewDesc;
                
                // 尝试获取ProseMirror view
                let desc = editor.pmViewDesc;
                while (desc) {
                    if (desc.view && desc.view.state) {
                        result['hasView'] = true;
                        result['docSize'] = desc.view.state.doc.content.size;
                        result['docJSON'] = JSON.stringify(desc.view.state.doc.toJSON()).substring(0, 200);
                        break;
                    }
                    desc = desc.parent;
                }
                
                return JSON.stringify(result);
            }
        """)
        print(f"ProseMirror: {pm_info}")

        # 查找React fiber
        react_info = await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return 'no editor';
                
                const fiberKey = Object.keys(editor).find(k => k.startsWith('__reactFiber'));
                if (fiberKey) {
                    let fiber = editor[fiberKey];
                    let depth = 0;
                    while (fiber && depth < 20) {
                        if (fiber.memoizedState && fiber.memoizedState.queue) {
                            return 'found state at depth ' + depth;
                        }
                        fiber = fiber.return;
                        depth++;
                    }
                }
                return 'no react fiber found';
            }
        """)
        print(f"React: {react_info}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())