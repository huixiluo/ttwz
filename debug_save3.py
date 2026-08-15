# -*- coding: utf-8 -*-
"""检查账号状态 + 直接API保存测试"""
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
page.get("https://mp.toutiao.com/profile_v4/graphic/publish")
time.sleep(8)

# 1) 账号信息
info = page.run_js("""
return fetch('https://mp.toutiao.com/mp/agw/user/info', {credentials: 'include'})
    .then(r => r.text()).catch(e => 'ERR:' + e.message);
""")
time.sleep(3)
print("=== 账号信息 ===")
try:
    d = json.loads(info)
    print(json.dumps({k: d.get(k) for k in ['code', 'message']}, ensure_ascii=False))
    data = d.get('data') or {}
    keep = {k: data.get(k) for k in ['auth_type', 'is_creator', 'is_verified', 'user_name', 'mobile', 'can_publish', 'publish_limit', 'wrong_msg'] if k in data}
    print(json.dumps(keep, ensure_ascii=False)[:500])
except Exception as e:
    print(str(info)[:500])

# 2) 创作者状态
info2 = page.run_js("""
return fetch('https://mp.toutiao.com/mp/agw/creator/status', {credentials: 'include'})
    .then(r => r.text()).catch(e => 'ERR:' + e.message);
""")
time.sleep(3)
print("\n=== 创作者状态 ===")
print(str(info2)[:600])

page.quit()
