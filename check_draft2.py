# -*- coding: utf-8 -*-
"""列出草稿箱所有标题（通过API）"""
import os, json, time
from datetime import datetime
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

result = page.run_js("""
return fetch('https://mp.toutiao.com/mp/agw/article/list?need_recall=0&status=0&from=all&offset=0&count=50&type=&source=0&_signature=', {
    method: 'GET', credentials: 'include'
}).then(r => r.json()).catch(e => ({err: e.message}));
""")
time.sleep(3)
arts = (result or {}).get("data", {}).get("articles", []) or []
print(f"共 {len(arts)} 条:")
for a in arts:
    ct = datetime.fromtimestamp(a.get("create_time", 0)).strftime("%m-%d %H:%M")
    title = a.get("title", "(无标题)")
    wc = a.get("content_word_cnt", "?")
    print(f"  [{ct}] {title}（{wc}字, draft={a.get('is_draft')}）")

page.quit()
