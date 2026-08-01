# -*- coding: utf-8 -*-
"""调试草稿箱页面结构"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
DRAFT_URL = "https://mp.toutiao.com/profile_v4/manage/draft"

co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)

page.get("https://mp.toutiao.com")
time.sleep(2)
cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)
print(f"Login: {page.url}")

page.get(DRAFT_URL)
time.sleep(5)
print(f"Draft URL: {page.url}")

# Find all buttons and clickable elements
print("\n=== 所有按钮和可点击元素 ===")
btns = page.run_js("""
var all = document.querySelectorAll('button, a, span[class*="btn"], div[class*="btn"], [role="button"]');
var result = [];
for (var i = 0; i < Math.min(all.length, 50); i++) {
    var el = all[i];
    var rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
        result.push('[' + i + '] tag=' + el.tagName + 
            ' class="' + (el.className || '').substring(0, 60) + '"' +
            ' text="' + (el.textContent || '').trim().substring(0, 30) + '"' +
            ' w=' + rect.width + ' h=' + rect.height);
    }
}
return result.join('\\n');
""")
print(btns)

# Find draft list items
print("\n=== 草稿列表项 ===")
items = page.run_js("""
var all = document.querySelectorAll('[class*="draft"], [class*="list"], [class*="item"], li, tr');
var result = [];
for (var i = 0; i < Math.min(all.length, 30); i++) {
    var el = all[i];
    var rect = el.getBoundingClientRect();
    var text = (el.textContent || '').trim().substring(0, 80);
    if (rect.width > 200 && text.length > 10) {
        result.push('[' + i + '] tag=' + el.tagName + 
            ' class="' + (el.className || '').substring(0, 60) + '"' +
            ' text="' + text + '"');
    }
}
return result.join('\\n');
""")
print(items)

# Find all links
print("\n=== 所有链接 ===")
links = page.run_js("""
var all = document.querySelectorAll('a');
var result = [];
for (var i = 0; i < Math.min(all.length, 30); i++) {
    var el = all[i];
    var rect = el.getBoundingClientRect();
    var href = el.getAttribute('href') || '';
    if (rect.width > 0 && href) {
        result.push('[' + i + '] href="' + href.substring(0, 80) + '" text="' + (el.textContent || '').trim().substring(0, 30) + '"');
    }
}
return result.join('\\n');
""")
print(links)

# Check body text
body = page.run_js("return document.body.innerText.substring(0, 1000);")
print(f"\n=== Body text ===\n{body}")

page.quit()
print("\nDONE")