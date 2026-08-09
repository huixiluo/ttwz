# -*- coding: utf-8 -*-
"""检查草稿箱网页是否显示测试文章"""
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
co.set_address("127.0.0.1:9241")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_check"))

page = ChromiumPage(co)
page.get("https://mp.toutiao.com")
time.sleep(2)

for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass

page.get("https://mp.toutiao.com/profile_v4/manage/draft")
time.sleep(8)

# 滚动
for i in range(3):
    page.run_js("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

draft_text = page.run_js("return document.body.innerText;") or ""
print(f"草稿箱文本长度: {len(draft_text)}")

# 搜索测试文章
if "测试" in draft_text:
    idx = draft_text.find("测试")
    print(f"找到'测试': {draft_text[max(0,idx-10):idx+50]}")
else:
    print("未找到'测试'")

# 搜索神仙姐姐
if "神仙姐姐" in draft_text:
    idx = draft_text.find("神仙姐姐")
    print(f"找到'神仙姐姐': {draft_text[max(0,idx-10):idx+50]}")
else:
    print("未找到'神仙姐姐'")

# 打印草稿列表
import re
count_match = re.search(r'共\s*(\d+)\s*条内容', draft_text)
if count_match:
    print(f"草稿数: {count_match.group(1)}")

# 打印前1500字
print("\n=== 草稿箱前1500字 ===")
print(draft_text[:1500])

page.quit()
print("\nDONE")
