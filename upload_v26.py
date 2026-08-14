#!/usr/bin/env python3
"""v26: 测试 save_ugc_draft 的 draft_type=1 时的正确内容字段名"""
import os, json, asyncio
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
CHROME_PATH = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

async def run():
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path=CHROME_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=UA)
        await context.add_cookies([
            {"name": k, "value": v, "domain": ".toutiao.com", "path": "/"}
            for k, v in cookies.items()
        ])
        page = await context.new_page()
        await page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        print("[OK] 登录", flush=True)

        csrf = cookies.get('passport_csrf_token', '')

        # draft_type=1 + 各种内容字段
        content_fields = [
            "content", "text", "body", "html", "html_content",
            "description", "summary", "detail", "data",
            "article_content", "draft_content", "ugc_content",
            "rich_text", "editor_content", "raw_content",
        ]

        for field in content_fields:
            body = {"draft_type": 1, "title": "测试"+field, field: "<p>测试内容123</p>"}
            body_json = json.dumps(body)
            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch('/mp/agw/draft/save_ugc_draft', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json', 'X-CSRFToken': {json.dumps(csrf)}}},
                            body: {body_json}
                        }});
                        return JSON.stringify(await resp.json());
                    }} catch(e) {{ return 'error: ' + e.message; }}
                }}
            """)
            code = ""
            try:
                code = json.loads(result).get('code', '')
            except: pass
            print(f"  {field}: code={code} {result[:150]}", flush=True)
            if code == 0:
                print(f"  *** SUCCESS with field: {field} ***", flush=True)
            await asyncio.sleep(0.3)

        # 也试试 draft_type=0 和 draft_type=2
        for dt in [0, 2, 3, 4, 5]:
            body = {"draft_type": dt, "title": "测试dt"+str(dt), "content": "<p>测试内容</p>"}
            body_json = json.dumps(body)
            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch('/mp/agw/draft/save_ugc_draft', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json', 'X-CSRFToken': {json.dumps(csrf)}}},
                            body: {body_json}
                        }});
                        return JSON.stringify(await resp.json());
                    }} catch(e) {{ return 'error: ' + e.message; }}
                }}
            """)
            print(f"  draft_type={dt}: {result[:150]}", flush=True)
            await asyncio.sleep(0.3)

        await page.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())