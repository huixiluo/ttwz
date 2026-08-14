#!/usr/bin/env python3
"""从浏览器获取最新的CSRF token和msToken，然后尝试保存"""
import json, asyncio, requests, urllib.parse
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

        # 拦截网络请求，捕获msToken
        captured_ms_token = [None]
        captured_a_bogus = [None]
        
        async def on_request(request):
            url = request.url
            if 'msToken=' in url:
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                if 'msToken' in params:
                    captured_ms_token[0] = params['msToken'][0]
                if 'a_bogus' in params:
                    captured_a_bogus[0] = params['a_bogus'][0]

        page.on("request", on_request)

        print("打开编辑器...")
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

        # 输入内容触发自动保存
        editor = page.locator('.ProseMirror').first
        await editor.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type("测试", delay=10)
        await asyncio.sleep(0.5)

        title_el = page.locator('textarea[placeholder*="文章标题"]').first
        await title_el.click()
        await asyncio.sleep(0.5)
        await title_el.fill("测试")
        await asyncio.sleep(1)

        await page.evaluate("""
            () => {
                const editor = document.querySelector('.ProseMirror');
                if (editor) {
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                }
            }
        """)
        await asyncio.sleep(5)

        # 获取msToken和a_bogus
        ms_token = captured_ms_token[0]
        a_bogus = captured_a_bogus[0]
        print(f"msToken: {ms_token}")
        print(f"a_bogus: {a_bogus}")

        # 获取最新的cookie
        page_cookies = await context.cookies()
        csrf_token = ""
        for c in page_cookies:
            if c['name'] == 'passport_csrf_token':
                csrf_token = c['value']
        print(f"csrf_token (from browser): {csrf_token}")

        # 获取当前页面的pgc_id
        pgc_id = await page.evaluate("""
            () => {
                const url = window.location.href;
                const m = url.match(/pgc_id=(\\d+)/);
                if (m) return m[1];
                return '';
            }
        """)
        print(f"pgc_id: {pgc_id}")

        await browser.close()

        # 用浏览器获取的token尝试API保存
        print("\n=== 用浏览器token尝试API保存 ===")
        session = requests.Session()
        session.headers.update({
            "User-Agent": UA, "Origin": "https://mp.toutiao.com", "Referer": "https://mp.toutiao.com/",
            "Accept": "application/json, text/plain, */*",
        })
        for name, value in cookies.items():
            session.cookies.set(name, value, domain=".toutiao.com", path="/")

        extra = json.dumps({
            "content_source": 100000000402,
            "content_word_cnt": 2,
            "is_multi_title": 0, "sub_titles": [],
            "gd_ext": {"entrance": "", "from_page": "publisher_mp", "enter_from": "PC", "device_platform": "mp", "is_message": 0},
            "tuwen_wtt_transfer_switch": "1"
        })

        form_data = {
            "article_type": "0", "pgc_id": pgc_id or "0", "source": "29",
            "title": "测试", "content": "<p>测试</p>", "extra": extra,
            "save": "0", "entrance": "main", "timer_status": "0", "timer_time": "",
            "title_id": "", "ic_uri_list": "[]", "search_creation_info": "",
            "is_refute_rumor": "0", "appid_list": "[]", "stock_ids": "[]", "concern_list": "[]",
            "comic_attr": "", "is_app_preview": "", "externalLinkChecked": "false",
            "externalLink": "", "claimOrigin": "0", "copyRightChecked": "1",
            "subTitle": "", "subCoverList": "[]", "coverList": "[]", "coverType": "0",
            "articleAdType": "0", "isFansArticle": "0", "activityId": "", "communitySync": "0",
        }

        params = {"source": "mp", "type": "article", "aid": "1231"}
        if ms_token:
            params["msToken"] = ms_token

        resp = session.post(
            "https://mp.toutiao.com/mp/agw/article/publish",
            params=params,
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": csrf_token or cookies.get('passport_csrf_token', '')
            }
        )
        print(f"  result: {resp.json()}")

if __name__ == "__main__":
    asyncio.run(main())