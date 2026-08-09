# -*- coding: utf-8 -*-
"""检查草稿箱页面HTML结构"""
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
co.set_address("127.0.0.1:9232")
co.set_user_data_path(os.path.join(BASE_DIR, ".chrome_profile_inspect2"))

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

# 获取所有链接
html_structure = page.run_js("""
var results = [];

// 查找所有链接
var allLinks = document.querySelectorAll("a");
results.push("=== 所有链接 ===");
results.push("链接总数: " + allLinks.length);
for (var i = 0; i < Math.min(allLinks.length, 50); i++) {
    var a = allLinks[i];
    var href = a.href || a.getAttribute("href") || "";
    var text = a.textContent.trim().substring(0, 50);
    if (href && text) {
        results.push(i + ": [" + text + "] -> " + href.substring(0, 120));
    }
}

// 查找草稿项
var draftRows = document.querySelectorAll("tr, [class*=row], [class*=item], [class*=card]");
results.push("\\n=== 草稿行 ===");
results.push("数量: " + draftRows.length);
for (var i = 0; i < Math.min(draftRows.length, 20); i++) {
    var el = draftRows[i];
    results.push(i + ": class=" + el.className.substring(0, 60) + " text=" + el.textContent.trim().substring(0, 60));
}

return results.join("\\n");
""")
print(html_structure)

# 获取所有可点击元素
clickables = page.run_js("""
var results = [];
var els = document.querySelectorAll("a, button, [role=button], [onclick], span[class*=btn], div[class*=btn]");
for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var text = el.textContent.trim();
    if (text.length > 0 && text.length < 30) {
        var href = el.href || el.getAttribute("href") || "";
        results.push(i + ": tag=" + el.tagName + " text=[" + text + "] href=" + href.substring(0, 100) + " class=" + el.className.substring(0, 60));
    }
}
return results.join("\\n");
""")
print("\n=== 可点击元素 ===")
print(clickables[:3000])

page.quit()
print("\nDONE")
