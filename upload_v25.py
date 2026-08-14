#!/usr/bin/env python3
"""v25: 测试 save_ugc_draft API 的不同参数格式"""
import os, re, json, time, base64, asyncio, io, sys
from playwright.async_api import async_playwright
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
MANIFEST_FILE = os.path.join(BASE_DIR, "output", "batch_manifest_tt.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

async def run():
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
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])

        page = await context.new_page()
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        print("[OK] 登录有效", flush=True)

        csrf = cookies.get('passport_csrf_token', '')

        tests = [
            # 不同字段名
            {"content": "<p>测试内容测试内容</p>", "title": "测试标题ABC"},
            {"text": "<p>测试内容测试内容</p>", "title": "测试标题ABC"},
            {"body": "<p>测试内容测试内容</p>", "title": "测试标题ABC"},
            {"description": "<p>测试内容测试内容</p>", "title": "测试标题ABC"},
            {"draft_content": "<p>测试内容测试内容</p>", "title": "测试标题ABC"},
            {"article_content": "<p>测试内容测试内容</p>", "title": "测试标题ABC"},
            # 带 draft_type
            {"content": "<p>测试内容测试内容</p>", "title": "测试标题ABC", "draft_type": 1},
            {"text": "<p>测试内容测试内容</p>", "title": "测试标题ABC", "draft_type": 1},
            # 带 article_type
            {"content": "<p>测试内容测试内容</p>", "title": "测试标题ABC", "article_type": 0},
            {"text": "<p>测试内容测试内容</p>", "title": "测试标题ABC", "article_type": 0},
            # 纯文本内容
            {"content": "测试内容测试内容", "title": "测试标题ABC"},
            {"text": "测试内容测试内容", "title": "测试标题ABC"},
            # 尝试 form-urlencoded
            "FORM:content=<p>测试</p>&title=测试标题",
        ]

        for i, test in enumerate(tests):
            print(f"\n--- 测试{i+1}: {str(test)[:100]} ---", flush=True)

            if isinstance(test, str) and test.startswith("FORM:"):
                # form-urlencoded
                form_body = test[5:]
                result = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('/mp/agw/draft/save_ugc_draft', {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/x-www-form-urlencoded',
                                    'X-CSRFToken': {json.dumps(csrf)}
                                }},
                                body: {json.dumps(form_body)}
                            }});
                            return JSON.stringify(await resp.json());
                        }} catch(e) {{ return 'error: ' + e.message; }}
                    }}
                """)
            else:
                body_json = json.dumps(test)
                result = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('/mp/agw/draft/save_ugc_draft', {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': {json.dumps(csrf)}
                                }},
                                body: {body_json}
                            }});
                            return JSON.stringify(await resp.json());
                        }} catch(e) {{ return 'error: ' + e.message; }}
                    }}
                """)

            print(f"  → {result[:200]}", flush=True)
            await asyncio.sleep(0.5)

        await page.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())