# -*- coding: utf-8 -*-
"""调试：找到新的编辑器元素"""
import os, json, time
from DrissionPage import ChromiumPage, ChromiumOptions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "toutiao_cookies.json")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"

co = ChromiumOptions()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
page = ChromiumPage(co)

# Login
cookies = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
page.get("https://mp.toutiao.com")
time.sleep(2)
for name, value in cookies.items():
    try:
        page.set.cookies({"name": name, "value": value, "domain": ".toutiao.com", "path": "/"})
    except:
        pass
page.get("https://mp.toutiao.com")
time.sleep(3)
print(f"Login: {page.url}")

# Go to publish page
page.get(PUBLISH_URL)
time.sleep(5)
print(f"Publish URL: {page.url}")

# Close any popup
try:
    close_btn = page.ele("text:关闭", timeout=2)
    if close_btn:
        close_btn.click()
        time.sleep(1)
except:
    pass

# Find all editor-related elements with details
print("\n=== 所有 editor 相关元素 ===")
editor_details = page.run_js("""
var els = document.querySelectorAll('[class*="editor"], [class*="Editor"]');
var result = [];
for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var rect = el.getBoundingClientRect();
    var isContentEditable = el.getAttribute('contenteditable');
    result.push('[' + i + '] tag=' + el.tagName + 
        ' class="' + (el.className || '').substring(0, 80) + '"' +
        ' contenteditable=' + isContentEditable +
        ' visible=' + (rect.width > 0 && rect.height > 0) +
        ' w=' + rect.width + ' h=' + rect.height +
        ' text="' + (el.textContent || '').trim().substring(0, 50) + '"');
}
return result.join('\\n');
""")
print(editor_details)

# Find contenteditable elements
print("\n=== contenteditable 元素 ===")
ce_details = page.run_js("""
var els = document.querySelectorAll('[contenteditable="true"]');
var result = [];
for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var rect = el.getBoundingClientRect();
    result.push('[' + i + '] tag=' + el.tagName + 
        ' class="' + (el.className || '').substring(0, 80) + '"' +
        ' visible=' + (rect.width > 0 && rect.height > 0) +
        ' w=' + rect.width + ' h=' + rect.height +
        ' text="' + (el.textContent || '').trim().substring(0, 50) + '"');
}
return result.join('\\n') || 'none';
""")
print(ce_details)

# Find all textareas
print("\n=== 所有 textarea ===")
ta_details = page.run_js("""
var els = document.querySelectorAll('textarea');
var result = [];
for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var rect = el.getBoundingClientRect();
    result.push('[' + i + '] placeholder="' + (el.placeholder || 'none') + '"' +
        ' visible=' + (rect.width > 0 && rect.height > 0) +
        ' w=' + rect.width + ' h=' + rect.height +
        ' value="' + (el.value || '').substring(0, 50) + '"');
}
return result.join('\\n');
""")
print(ta_details)

# Try to find the main content area by looking at the page structure
print("\n=== 主要内容区域（大块可见div） ===")
main_areas = page.run_js("""
var divs = document.querySelectorAll('div');
var result = [];
for (var i = 0; i < divs.length; i++) {
    var d = divs[i];
    var rect = d.getBoundingClientRect();
    if (rect.width > 400 && rect.height > 200) {
        var cls = (d.className || '').substring(0, 60);
        var role = d.getAttribute('role') || '';
        result.push('class="' + cls + '" role=' + role + 
            ' w=' + rect.width + ' h=' + rect.height +
            ' text="' + (d.textContent || '').trim().substring(0, 60) + '"');
    }
    if (result.length >= 10) break;
}
return result.join('\\n');
""")
print(main_areas)

page.quit()
print("\nDONE")