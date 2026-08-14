#!/usr/bin/env python3
"""尝试用不同方式打开编辑器 + 通过ProseMirror API直接保存"""
import json, asyncio, re
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

        # 拦截所有 publish 请求
        publish_requests = []
        async def on_request(request):
            if 'publish' in request.url and request.method == 'POST':
                publish_requests.append({
                    "url": request.url,
                    "post_data": request.post_data
                })
        page.on("request", on_request)

        # 尝试直接打开编辑器（不带任何参数）
        print("打开编辑器 (fresh)...")
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

        await page.wait_for_selector(".ProseMirror", timeout=15000)

        # 获取ProseMirror view
        print("获取ProseMirror view...")
        has_view = await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return 'no editor';
                let desc = editor.pmViewDesc;
                while (desc) {
                    if (desc.view && desc.view.state) {
                        // 保存到window供后续使用
                        window.__pm_view = desc.view;
                        return 'view found, doc size: ' + desc.view.state.doc.content.size;
                    }
                    desc = desc.parent;
                }
                return 'no view found';
            }
        """)
        print(f"  {has_view}")

        # 使用ProseMirror API设置内容
        print("通过ProseMirror API设置内容...")
        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (!editor) return 'no editor';
                let desc = editor.pmViewDesc;
                while (desc) {
                    if (desc.view && desc.view.state) {
                        const view = desc.view;
                        const schema = view.state.schema;
                        
                        // 创建新的文档内容
                        const nodes = [];
                        nodes.push(schema.nodes.paragraph.create(null, schema.text('这是通过ProseMirror API设置的测试内容。')));
                        nodes.push(schema.nodes.paragraph.create(null, schema.text('第二段内容，用于测试自动保存。')));
                        
                        const doc = schema.nodes.doc.create(null, nodes);
                        const tr = view.state.tr.replaceWith(0, view.state.doc.content.size, doc.content);
                        view.dispatch(tr);
                        
                        return 'content set';
                    }
                    desc = desc.parent;
                }
                return 'no view';
            }
        """)
        await asyncio.sleep(2)

        # 填写标题
        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click()
        await asyncio.sleep(0.5)
        await title_el.fill("ProseMirror API测试")
        await asyncio.sleep(2)

        # 截图
        await page.screenshot(path="/workspace/pm_api_content.png")

        # 触发input事件
        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                    editor.dispatchEvent(new Event('change', {bubbles: true}));
                    editor.dispatchEvent(new Event('blur', {bubbles: true}));
                }
            }
        """)
        await asyncio.sleep(10)

        # 打印捕获到的publish请求
        print(f"\n捕获到 {len(publish_requests)} 个publish请求:")
        for i, req in enumerate(publish_requests):
            print(f"\n  请求{i+1}:")
            print(f"    URL: {req['url'][:150]}")
            if req['post_data']:
                # 解析post_data
                pd = req['post_data']
                # 提取关键字段
                fields = {}
                for pair in pd.split('&'):
                    if '=' in pair:
                        k, v = pair.split('=', 1)
                        if k in ['content', 'title', 'pgc_id', 'article_type']:
                            from urllib.parse import unquote
                            decoded = unquote(v)
                            fields[k] = decoded[:100]
                print(f"    关键字段: {json.dumps(fields, ensure_ascii=False)}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())