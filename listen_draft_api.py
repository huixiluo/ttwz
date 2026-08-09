# -*- coding: utf-8 -*-
"""用DrissionPage监听功能捕获草稿列表API"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROME_PATH = "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

with open(os.path.join(BASE_DIR, "toutiao_cookies.json"), "r", encoding="utf-8") as f:
    cookies = json.load(f)

co = ChromiumOptions()
co.set_browser_path(CHROME_PATH)
co.headless(True)
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.set_argument("--window-size=1920,1080")
co.set_address("127.0.0.1:9238")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_listen"))

page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)

for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass

page.get("https://mp.toutiao.com")
time.sleep(3)

# 使用DrissionPage的listen功能
page.listen.start("mp/agw")

# 导航到草稿箱
page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(10)

# 滚动
for i in range(3):
    page.run_js("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

# 获取监听到的数据包
packets = list(page.listen.steps(count=20, timeout=15))
print(f"监听到 {len(packets)} 个数据包")

for i, packet in enumerate(packets):
    url = packet.url
    method = packet.method
    body = ""

    # 获取响应体
    try:
        response = packet.response
        if response:
            body = response.body if isinstance(response.body, str) else str(response.body)
    except:
        pass

    # 过滤掉monitoring请求
    if "monitor" in url or "collect" in url:
        continue

    print(f"\n[{i}] {method} {url[:150]}")
    if body:
        # 检查是否有草稿数据
        if any(kw in body for kw in ["pgc_id", "group_id", "draft", "title", "article"]):
            print(f"  *** 含草稿数据 ***")
            print(f"  Body: {body[:1000]}")
        else:
            print(f"  Body: {body[:200]}")

page.listen.stop()
page.quit()
print("\nDONE")
