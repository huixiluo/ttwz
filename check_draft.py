# -*- coding: utf-8 -*-
"""检查草稿箱实际状态：UI页面 + API"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")

co = ChromiumOptions()
chrome_path = "/root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome"
if os.path.exists(chrome_path):
    co.set_browser_path(chrome_path)
co.auto_port()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.headless()
page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)
with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies = json.load(f)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except Exception:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)

# 1) 内容管理页（含草稿tab）
page.get("https://mp.toutiao.com/profile_v4/graphic/manage")
time.sleep(6)
print("URL:", page.url)
body = page.run_js("return document.body.innerText;") or ""
print("=== 管理页文本(前1500字) ===")
print(body[:1500])

# 2) 草稿API
api_result = page.run_js("""
return fetch('https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=20&type=&source=0&_signature=', {
    method: 'GET',
    credentials: 'include'
}).then(r => r.text()).catch(e => 'ERR:' + e.message);
""")
time.sleep(3)
print("=== 草稿API(status=0草稿) ===")
print(str(api_result)[:2000])

page.quit()
